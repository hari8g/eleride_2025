import math
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class DemandLaneCard:
    lane_id: str
    qc_name: str
    lat: float
    lon: float
    shift_start: str
    earning_range: str
    minimum_guarantee: str
    contract_type: str
    slots_available: str
    demand_score: float


CITY_CENTROIDS: dict[str, tuple[float, float]] = {
    "BENGALURU": (12.9716, 77.5946),
    "BANGALORE": (12.9716, 77.5946),
    "PUNE": (18.5204, 73.8567),
    "DELHI": (28.6139, 77.2090),
    "HYDERABAD": (17.3850, 78.4867),
}

def _stable_unit_interval(seed: str) -> float:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    # use 8 hex chars -> 32-bit int
    n = int(h[:8], 16)
    return (n % 10_000_000) / 10_000_000.0


def _offset_point_km(lat: float, lon: float, *, r_km: float, angle_turns: float) -> tuple[float, float]:
    """
    Offset a point by r_km at an angle (turns where 1.0 = 360deg).
    Approximate conversion for small distances.
    """
    ang = 2.0 * math.pi * angle_turns
    dlat = (r_km * math.cos(ang)) / 111.0
    dlon = (r_km * math.sin(ang)) / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def build_cards_from_forecasts(
    *,
    lat: float,
    lon: float,
    radius_km: float,
    forecasts: list[dict],
    force_lane_id: str | None = None,
) -> list[dict]:
    """
    Transform store-level forecasts into rider-facing demand cards.
    If a store doesn't have lat/lon, use a city centroid (coarse fallback).
    """
    cards: list[dict] = []
    for f in forecasts:
        city = (f.get("city") or "").strip().upper()
        store = (f.get("store") or "").strip()
        if not store:
            continue

        store_lat = f.get("lat")
        store_lon = f.get("lon")
        if store_lat is None or store_lon is None:
            # We don't have precise store geo yet. Use a city centroid plus a deterministic small offset
            # so riders see distinct pins and realistic distances.
            base_lat, base_lon = CITY_CENTROIDS.get(city, (lat, lon))
            # If the rider is far away from this city, anchor the demo pins around the rider instead.
            # This prevents a confusing "No lanes returned" when your dataset is for a different city.
            if _haversine_km(lat, lon, base_lat, base_lon) > 200.0:
                base_lat, base_lon = lat, lon
            lane_seed = f"store:{city}:{store}"
            u1 = _stable_unit_interval(lane_seed + ":r")
            u2 = _stable_unit_interval(lane_seed + ":a")
            # place within ~1–8 km of the centroid
            r_km = 1.0 + 7.0 * u1
            store_lat, store_lon = _offset_point_km(base_lat, base_lon, r_km=r_km, angle_turns=u2)

        d = _haversine_km(lat, lon, float(store_lat), float(store_lon))
        lane_id = f"store:{city}:{store}"
        if d > radius_km and lane_id != force_lane_id:
            continue

        # With heuristic ranking, these are store-level signals (already aggregated).
        orders_per_day = float(f.get("orders_per_day") or 0.0)
        cancel_rate = float(f.get("cancel_rate") or 0.0)
        incentive_share = float(f.get("incentive_share") or 0.0)
        weekend_share = float(f.get("weekend_share") or 0.0)
        demand_score = float(f.get("demand_score") or orders_per_day)

        # Very rough earnings heuristic for demo purposes:
        # - assume per-order payout = 25
        # - show a range +-15%
        per_order = 25.0
        base = orders_per_day * per_order
        low = int(base * 0.85)
        high = int(base * 1.15)

        # min guarantee: 70% of base (capped min of 300)
        mg = max(300, int(base * 0.7))

        # slots: assume one rider can do ~80 orders/day
        slots = max(1, int(round(orders_per_day / 80.0)))
        trips_per_day = max(1, int(round(orders_per_day / 2.2)))  # rough demo proxy

        reasons: list[str] = []
        reasons.append(f"orders/day≈{orders_per_day:.1f}")
        reasons.append(f"cancel≈{cancel_rate*100:.1f}%")
        reasons.append(f"incentive≈{incentive_share*100:.1f}%")
        reasons.append(f"weekend≈{weekend_share*100:.1f}%")

        cards.append(
            {
                "lane_id": lane_id,
                "qc_name": f"{city if city in CITY_CENTROIDS else 'NEAR YOU'} • {store}",
                "lat": float(store_lat),
                "lon": float(store_lon),
                "distance_km": round(d, 2),
                "shift_start": f.get("shift_start") or "06:00",
                "earning_range": f"₹{low}–₹{high}/day",
                "minimum_guarantee": f"₹{mg}/day",
                "expected_trips_per_day": trips_per_day,
                "expected_orders_per_day": round(orders_per_day, 1),
                "contract_type": f.get("contract_type") or "WEEKLY",
                "slots_available": f"~{slots}",
                "rank_reasons": reasons,
                "_demand_score": demand_score,
            }
        )

    cards.sort(key=lambda x: (-x.get("_demand_score", 0.0), x.get("distance_km", 1e9)))
    for c in cards:
        c.pop("_demand_score", None)
    return cards


