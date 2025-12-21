import json

from sqlalchemy.orm import Session

from app.domains.supply.models import SupplyRequest, SupplyRequestStatus
from app.domains.supply_match.service import pick_operator_for_lane
from app.domains.matchmaking.service import recommend


def create_supply_request(
    db: Session,
    *,
    rider_id: str,
    lane_id: str,
    time_window: str | None,
    requirements: str | None,
    rider_lat: float | None = None,
    rider_lon: float | None = None,
    operator_id: str | None = None,
) -> SupplyRequest:
    req = SupplyRequest(
        rider_id=rider_id,
        lane_id=lane_id,
        time_window=time_window,
        requirements=requirements,
        status=SupplyRequestStatus.CREATED,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Multi-operator matchmaking:
    chosen_op = operator_id
    if not chosen_op:
        rec = recommend(
            db,
            lane_id=lane_id,
            rider_lat=rider_lat,
            rider_lon=rider_lon,
            max_km=8.0,
            min_battery_pct=20.0,
            max_telemetry_age_min=120.0,
            limit=6,
        )
        top = (rec.get("recommended") or {}) if isinstance(rec, dict) else {}
        chosen_op = top.get("operator_id")
        # persist audit fields (moat: transparent, explainable auto-assign)
        req.matched_vehicle_id = top.get("vehicle_id")
        req.matched_score = float(top.get("score")) if top.get("score") is not None else None
        try:
            req.matched_reasons = json.dumps(top.get("reasons") or [])
        except Exception:
            req.matched_reasons = None
    operator = pick_operator_for_lane(lane_id=lane_id, operator_id=chosen_op)
    req.operator_id = operator.operator_id
    req.pickup_location = operator.pickup_location
    req.status = SupplyRequestStatus.MATCHED
    db.commit()
    db.refresh(req)
    return req


