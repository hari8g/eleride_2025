import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db, require_rider
from app.core.security import Principal
from app.domains.matchmaking.schemas import AuditRecentOut, AuditRow, AvailabilityOut, RecommendIn, RecommendOut
from app.domains.matchmaking.service import availability, recommend
from app.domains.supply.models import SupplyRequest


router = APIRouter(prefix="/matchmaking")


@router.get("/availability", response_model=AvailabilityOut)
def availability_route(
    lane_id: str,
    rider_lat: float | None = Query(default=None),
    rider_lon: float | None = Query(default=None),
    max_km: float = Query(default=8.0),
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> AvailabilityOut:
    # Rider-auth for now (portal can use rider OTP in MVP).
    out = availability(db, lane_id=lane_id, rider_lat=rider_lat, rider_lon=rider_lon, max_km=float(max_km))
    return AvailabilityOut(**out)  # type: ignore[arg-type]


@router.post("/recommend", response_model=RecommendOut)
def recommend_route(
    payload: RecommendIn,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RecommendOut:
    out = recommend(
        db,
        lane_id=payload.lane_id,
        rider_lat=payload.rider_lat,
        rider_lon=payload.rider_lon,
        max_km=float(payload.max_km),
        min_battery_pct=float(payload.min_battery_pct),
        max_telemetry_age_min=float(payload.max_telemetry_age_min),
        limit=int(payload.limit),
    )
    return RecommendOut(**out)  # type: ignore[arg-type]


@router.get("/audit/recent", response_model=AuditRecentOut)
def audit_recent(
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> AuditRecentOut:
    """
    Internal console endpoint: recent auto-assign decisions.
    MVP guardrail:
    - In dev env, allows viewing global recent assignments.
    - In non-dev, restricts to the caller's rider_id.
    """
    q = db.query(SupplyRequest)
    if settings.env != "dev":
        q = q.filter(SupplyRequest.rider_id == principal.sub)
    rows = q.order_by(desc(SupplyRequest.created_at)).limit(int(limit)).all()

    items: list[AuditRow] = []
    for r in rows:
        reasons = None
        if r.matched_reasons:
            try:
                reasons = json.loads(r.matched_reasons)
            except Exception:
                reasons = None
        items.append(
            AuditRow(
                request_id=r.id,
                created_at=r.created_at.isoformat(),
                rider_id=r.rider_id,
                lane_id=r.lane_id,
                supply_status=(r.status.value if hasattr(r.status, "value") else str(r.status)),
                operator_id=r.operator_id,
                pickup_location=r.pickup_location,
                matched_vehicle_id=r.matched_vehicle_id,
                matched_score=r.matched_score,
                matched_reasons=reasons,
            )
        )

    return AuditRecentOut(items=items)


