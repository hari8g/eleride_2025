import math
import hashlib
from datetime import datetime, timezone, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.demand_discovery.service import CITY_CENTROIDS
from app.domains.operator_portal.models import (
    MaintenanceRecord,
    MaintenanceStatus,
    Operator,
    OperatorInboxState,
    OperatorRequestInbox,
    Vehicle,
    VehicleStatus,
)
from app.domains.supply.models import SupplyRequest


def _stable_unit_interval(seed: str) -> float:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    return (n % 10_000_000) / 10_000_000.0


def _offset_point_km(lat: float, lon: float, *, r_km: float, angle_turns: float) -> tuple[float, float]:
    ang = 2.0 * math.pi * angle_turns
    dlat = (r_km * math.cos(ang)) / 111.0
    dlon = (r_km * math.sin(ang)) / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def lane_anchor(*, lane_id: str, rider_lat: float | None, rider_lon: float | None) -> tuple[float, float, str]:
    """
    Deterministic lane anchor for matching.
    For store lanes, mirror demand_discovery's "stable pin near city centroid" behavior.
    """
    if lane_id.startswith("store:"):
        parts = lane_id.split(":")
        city = (parts[1] if len(parts) > 1 else "").strip().upper()
        base_lat, base_lon = CITY_CENTROIDS.get(city, (rider_lat or 18.5204, rider_lon or 73.8567))
        # If rider is far away from the city, anchor around rider so UI/demo doesn't look broken.
        if rider_lat is not None and rider_lon is not None:
            if haversine_km(rider_lat, rider_lon, base_lat, base_lon) > 200.0:
                base_lat, base_lon = rider_lat, rider_lon
        u1 = _stable_unit_interval(lane_id + ":r")
        u2 = _stable_unit_interval(lane_id + ":a")
        r_km = 1.0 + 7.0 * u1
        lat, lon = _offset_point_km(base_lat, base_lon, r_km=r_km, angle_turns=u2)
        return float(lat), float(lon), "store:stable_offset"
    # fallback: rider location or Pune center
    return float(rider_lat or 18.5204), float(rider_lon or 73.8567), "fallback:rider_or_city"


def _operator_load(db: Session, *, operator_id: str) -> tuple[int, int]:
    """
    Load proxy from inbox states for the operator.
    Returns: (inbox_new, inbox_contacted)
    """
    # supply_requests for operator
    req_ids = [r[0] for r in db.query(SupplyRequest.id).filter(SupplyRequest.operator_id == operator_id).all()]
    if not req_ids:
        return 0, 0
    rows = (
        db.query(OperatorRequestInbox.state, func.count(OperatorRequestInbox.id))
        .filter(OperatorRequestInbox.operator_id == operator_id, OperatorRequestInbox.supply_request_id.in_(req_ids))
        .group_by(OperatorRequestInbox.state)
        .all()
    )
    counts = { (st.value if hasattr(st, "value") else str(st)): int(c or 0) for st, c in rows }
    # missing rows are implicitly NEW, but we can't count missing without joining; keep it conservative.
    return int(counts.get(OperatorInboxState.NEW.value, 0)), int(counts.get(OperatorInboxState.CONTACTED.value, 0))


def _maintenance_open_vehicle_count(db: Session, *, operator_id: str) -> int:
    return int(
        db.query(func.count(func.distinct(MaintenanceRecord.vehicle_id)))
        .filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.status == MaintenanceStatus.OPEN)
        .scalar()
        or 0
    )


def score_vehicle(
    *,
    v: Vehicle,
    lane_lat: float,
    lane_lon: float,
    max_km: float,
    min_batt: float,
    max_age_min: float,
) -> tuple[float, float | None, list[str], bool]:
    """
    Returns: (score_0_100, distance_km, reasons, eligible)
    """
    reasons: list[str] = []
    eligible = True

    if v.status != VehicleStatus.ACTIVE:
        eligible = False
        reasons.append(f"blocked:vehicle_status={v.status.value}")

    dist = None
    if v.last_lat is not None and v.last_lon is not None:
        dist = haversine_km(float(v.last_lat), float(v.last_lon), lane_lat, lane_lon)
        if dist > max_km:
            eligible = False
            reasons.append(f"blocked:distance>{max_km:.1f}km (≈{dist:.1f}km)")
    else:
        # Without geo, we can still consider it but penalize heavily.
        reasons.append("penalty:no_location")

    if v.battery_pct is not None:
        batt = float(v.battery_pct)
        if batt < min_batt:
            eligible = False
            reasons.append(f"blocked:battery<{min_batt:.0f}% ({batt:.0f}%)")
    else:
        reasons.append("penalty:no_battery")

    if v.last_telemetry_at is not None:
        age_min = (datetime.now(timezone.utc) - v.last_telemetry_at).total_seconds() / 60.0
        if age_min > max_age_min:
            eligible = False
            reasons.append(f"blocked:telemetry_stale>{max_age_min:.0f}m (≈{age_min:.0f}m)")
    else:
        eligible = False
        reasons.append("blocked:no_telemetry")

    # Score (multi-objective, bounded, explainable)
    score = 100.0

    # distance: up to -55 points
    if dist is None:
        score -= 35.0
    else:
        score -= min(55.0, (dist / max(0.5, max_km)) * 55.0)
        reasons.append(f"distance≈{dist:.1f}km")

    # battery: reward high battery, penalize low; bounded +-20
    if v.battery_pct is None:
        score -= 8.0
    else:
        batt = float(v.battery_pct)
        # 20% -> 0 bonus, 100% -> +18 bonus
        bonus = max(0.0, min(18.0, (batt - min_batt) / max(1.0, (100.0 - min_batt)) * 18.0))
        score += bonus
        reasons.append(f"battery≈{batt:.0f}% (bonus +{bonus:.1f})")

    # telemetry freshness: up to -18
    if v.last_telemetry_at is None:
        score -= 18.0
    else:
        age_min = (datetime.now(timezone.utc) - v.last_telemetry_at).total_seconds() / 60.0
        penalty = min(18.0, max(0.0, age_min / max(1.0, max_age_min) * 18.0))
        score -= penalty
        reasons.append(f"telemetry_age≈{age_min:.0f}m (penalty -{penalty:.1f})")

    score = max(0.0, min(100.0, score))
    return score, dist, reasons, eligible


def recommend(
    db: Session,
    *,
    lane_id: str,
    rider_lat: float | None,
    rider_lon: float | None,
    max_km: float,
    min_battery_pct: float,
    max_telemetry_age_min: float,
    limit: int,
) -> dict:
    lane_lat, lane_lon, lane_source = lane_anchor(lane_id=lane_id, rider_lat=rider_lat, rider_lon=rider_lon)

    ops: list[Operator] = db.query(Operator).all()
    op_name = {o.slug: o.name for o in ops}
    op_slugs = [o.slug for o in ops]
    if not op_slugs:
        return {
            "lane": {"lane_id": lane_id, "lat": lane_lat, "lon": lane_lon, "source": lane_source},
            "recommended": None,
            "alternatives": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Pull active vehicles across operators. Keep it bounded for UI perf.
    # (This is MVP; production would page by geo index.)
    vs: list[Vehicle] = (
        db.query(Vehicle)
        .filter(Vehicle.operator_id.in_(op_slugs))
        .order_by(Vehicle.created_at.desc())
        .limit(1200)
        .all()
    )

    candidates: list[dict] = []
    for v in vs:
        score, dist, reasons, eligible = score_vehicle(
            v=v,
            lane_lat=lane_lat,
            lane_lon=lane_lon,
            max_km=max_km,
            min_batt=min_battery_pct,
            max_age_min=max_telemetry_age_min,
        )
        if not eligible:
            continue

        # operator load penalty: avoid sending all riders to the same operator
        inbox_new, inbox_contacted = _operator_load(db, operator_id=v.operator_id)
        load_penalty = min(12.0, inbox_new * 1.6 + inbox_contacted * 0.6)
        score2 = max(0.0, score - load_penalty)
        reasons2 = reasons + [f"op_load:new={inbox_new},contacted={inbox_contacted} (penalty -{load_penalty:.1f})"]

        candidates.append(
            {
                "vehicle_id": v.id,
                "registration_number": v.registration_number,
                "operator_id": v.operator_id,
                "status": (v.status.value if hasattr(v.status, "value") else str(v.status)),
                "last_telemetry_at": v.last_telemetry_at.isoformat() if v.last_telemetry_at else None,
                "battery_pct": float(v.battery_pct) if v.battery_pct is not None else None,
                "distance_km": float(dist) if dist is not None else None,
                "score": round(score2, 2),
                "reasons": reasons2,
                "_op_name": op_name.get(v.operator_id),
            }
        )

    candidates.sort(key=lambda x: (-x["score"], x["distance_km"] if x["distance_km"] is not None else 1e9))
    top = candidates[: max(1, limit)]
    recommended = top[0] if top else None

    # strip internal field
    for c in top:
        c.pop("_op_name", None)

    return {
        "lane": {"lane_id": lane_id, "lat": lane_lat, "lon": lane_lon, "source": lane_source},
        "recommended": recommended,
        "alternatives": top[1:] if len(top) > 1 else [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def availability(db: Session, *, lane_id: str, rider_lat: float | None, rider_lon: float | None, max_km: float) -> dict:
    lane_lat, lane_lon, lane_source = lane_anchor(lane_id=lane_id, rider_lat=rider_lat, rider_lon=rider_lon)
    ops: list[Operator] = db.query(Operator).all()
    op_slugs = [o.slug for o in ops]
    op_name = {o.slug: o.name for o in ops}

    # basic counts
    vehicles_by_op = {op: [] for op in op_slugs}
    for v in db.query(Vehicle).filter(Vehicle.operator_id.in_(op_slugs)).all():
        vehicles_by_op.setdefault(v.operator_id, []).append(v)

    operators_out: list[dict] = []
    for op in op_slugs:
        vs = vehicles_by_op.get(op, [])
        active = sum(1 for v in vs if v.status == VehicleStatus.ACTIVE)
        # available ~= active with fresh telemetry & battery >= 20
        now = datetime.now(timezone.utc)
        available = 0
        top: list[dict] = []
        for v in vs:
            if v.status != VehicleStatus.ACTIVE:
                continue
            if v.last_telemetry_at is None or (now - v.last_telemetry_at) > timedelta(hours=4):
                continue
            if v.battery_pct is not None and float(v.battery_pct) < 20.0:
                continue
            available += 1

            # show a few nearby examples
            dist = None
            if v.last_lat is not None and v.last_lon is not None:
                dist = haversine_km(float(v.last_lat), float(v.last_lon), lane_lat, lane_lon)
                if dist > max_km:
                    continue
            top.append(
                {
                    "vehicle_id": v.id,
                    "registration_number": v.registration_number,
                    "operator_id": v.operator_id,
                    "status": v.status.value,
                    "last_telemetry_at": v.last_telemetry_at.isoformat() if v.last_telemetry_at else None,
                    "battery_pct": float(v.battery_pct) if v.battery_pct is not None else None,
                    "distance_km": float(dist) if dist is not None else None,
                    "score": 0.0,
                    "reasons": [],
                }
            )
        top.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 1e9)
        top = top[:6]

        inbox_new, inbox_contacted = _operator_load(db, operator_id=op)
        open_maint = _maintenance_open_vehicle_count(db, operator_id=op)
        operators_out.append(
            {
                "operator_id": op,
                "operator_name": op_name.get(op),
                "active_vehicles": int(active),
                "available_vehicles": int(available),
                "inbox_new": int(inbox_new),
                "inbox_contacted": int(inbox_contacted),
                "open_maintenance_vehicles": int(open_maint),
                "top_vehicles": top,
            }
        )

    return {
        "lane": {"lane_id": lane_id, "lat": lane_lat, "lon": lane_lon, "source": lane_source},
        "operators": operators_out,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


