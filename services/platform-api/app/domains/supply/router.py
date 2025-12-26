import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_rider
from app.core.security import Principal
from app.domains.operator_portal.models import Operator, OperatorInboxState, OperatorRequestInbox
from app.domains.operator_portal.models import Vehicle
from app.domains.supply.models import SupplyRequest, SupplyRequestStatus
from app.domains.supply.schemas import RiderSupplyStatusOut, SupplyRequestCreateIn, SupplyRequestCreateOut
from app.domains.supply.service import create_supply_request
from app.domains.supply_match.service import pick_operator_for_lane
from app.domains.rider.service import get_rider_by_phone
from app.domains.rider.models import RiderStatus
from app.utils.qr import build_pickup_qr_payload, pickup_qr_code, qr_png_base64


router = APIRouter(prefix="/supply")


@router.post("/requests", response_model=SupplyRequestCreateOut)
def create_request(
    payload: SupplyRequestCreateIn,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> SupplyRequestCreateOut:
    rider = get_rider_by_phone(db, principal.sub)
    if rider.status != RiderStatus.VERIFIED_PENDING_SUPPLY_MATCH:
        return SupplyRequestCreateOut(
            request_id="",
            status="REJECTED",
            next_step="Complete verification to connect to a vehicle",
            operator={"code": "RIDER_NOT_VERIFIED", "required_status": RiderStatus.VERIFIED_PENDING_SUPPLY_MATCH.value},
        )
    # lane_id format for this MVP can be:
    # - legacy demo lanes, or
    # - "store:{CITY}:{STORE}" from demand ML forecasts
    lane_id = payload.lane_id
    if lane_id.startswith("store:"):
        lane_id = lane_id  # keep as-is; supply_match is a placeholder anyway

    req = create_supply_request(
        db,
        rider_id=rider.id,
        lane_id=lane_id,
        time_window=payload.time_window,
        requirements=payload.requirements,
        rider_lat=payload.rider_lat,
        rider_lon=payload.rider_lon,
        operator_id=payload.operator_id,
    )
    operator = pick_operator_for_lane(lane_id=lane_id, operator_id=req.operator_id)
    return SupplyRequestCreateOut(
        request_id=req.id,
        status=req.status.value,
        next_step=f"Proceed to onboarding with {operator.name}",
        operator={
            "operator_id": operator.operator_id,
            "name": operator.name,
            "pickup_location": operator.pickup_location,
            "required_docs": operator.required_docs,
        },
    )


@router.get("/status", response_model=RiderSupplyStatusOut)
def rider_supply_status(
    request_id: str | None = Query(default=None),
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderSupplyStatusOut:
    """
    Rider status view after "Connect me":
    - shows the rider's latest supply request (or a specific request_id)
    - maps operator inbox state to a rider-friendly stage
    """
    rider = get_rider_by_phone(db, principal.sub)
    q = db.query(SupplyRequest).filter(SupplyRequest.rider_id == rider.id)
    if request_id:
        q = q.filter(SupplyRequest.id == request_id)
    req: SupplyRequest | None = q.order_by(desc(SupplyRequest.created_at)).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No connect request found")

    op_name = None
    if req.operator_id:
        op = db.query(Operator).filter(Operator.slug == req.operator_id).one_or_none()
        op_name = op.name if op else None

    st_row = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == (req.operator_id or ""), OperatorRequestInbox.supply_request_id == req.id)
        .one_or_none()
        if req.operator_id
        else None
    )
    inbox_state = (st_row.state.value if st_row else OperatorInboxState.NEW.value)
    inbox_note = st_row.note if st_row else None
    inbox_updated_at = st_row.updated_at.isoformat() if (st_row and st_row.updated_at) else None

    # Map to a product-style stage for the rider.
    if req.status == SupplyRequestStatus.REJECTED or inbox_state == OperatorInboxState.REJECTED.value:
        stage = {"code": "rejected", "label": "Rejected", "detail": inbox_note or "The operator couldn’t accept your request."}
    elif req.pickup_verified_at is not None:
        stage = {"code": "completed", "label": "Pickup verified", "detail": "Pickup verified at the hub. You’re good to go."}
    elif inbox_state == OperatorInboxState.ONBOARDED.value:
        stage = {"code": "approved", "label": "Approved", "detail": inbox_note or "Approved. Please proceed to pickup/onboarding."}
    elif inbox_state == OperatorInboxState.CONTACTED.value:
        stage = {"code": "verification", "label": "Verification in progress", "detail": inbox_note or "The operator is verifying your details."}
    else:
        stage = {"code": "sent", "label": "Request sent", "detail": "Your request has been sent to the operator."}

    # Enrich with pickup hub coordinates (demo mapping) and vehicle registration (if assigned).
    pickup_lat = None
    pickup_lon = None
    if req.operator_id:
        try:
            rec = pick_operator_for_lane(lane_id=req.lane_id, operator_id=req.operator_id)
            pickup_lat = rec.pickup_lat
            pickup_lon = rec.pickup_lon
        except Exception:
            pickup_lat = None
            pickup_lon = None

    vehicle_reg = None
    if req.matched_vehicle_id:
        v = db.get(Vehicle, req.matched_vehicle_id)
        if v and getattr(v, "operator_id", None) == (req.operator_id or ""):
            vehicle_reg = v.registration_number

    pickup_qr_png = None
    pickup_code = None
    if stage.get("code") == "approved":
        payload = build_pickup_qr_payload(
            supply_request_id=req.id,
            operator_id=req.operator_id,
            vehicle_reg=vehicle_reg,
        )
        pickup_qr_png = qr_png_base64(payload)
        pickup_code = pickup_qr_code(supply_request_id=req.id, operator_id=req.operator_id, vehicle_reg=vehicle_reg)

    return RiderSupplyStatusOut(
        request_id=req.id,
        created_at=req.created_at.isoformat(),
        supply_status=req.status.value,
        operator_id=req.operator_id,
        operator_name=op_name,
        pickup_location=req.pickup_location,
        pickup_lat=pickup_lat,
        pickup_lon=pickup_lon,
        matched_vehicle_id=req.matched_vehicle_id,
        matched_vehicle_registration_number=vehicle_reg,
        matched_score=req.matched_score,
        matched_reasons=json.loads(req.matched_reasons) if req.matched_reasons else None,
        pickup_qr_png_base64=pickup_qr_png,
        pickup_qr_code=pickup_code,
        pickup_verified_at=(req.pickup_verified_at.isoformat() if req.pickup_verified_at else None),
        inbox_state=inbox_state,
        inbox_note=inbox_note,
        inbox_updated_at=inbox_updated_at,
        stage=stage,  # type: ignore[arg-type]
    )


