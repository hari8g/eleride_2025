from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_rider
from app.core.security import Principal
from app.domains.rider.schemas import RiderProfileIn, RiderProfileOut, RiderStatusOut
from app.domains.rider.service import get_rider_by_phone, get_status_payload, upsert_profile


router = APIRouter(prefix="/riders")


@router.post("/profile", response_model=RiderProfileOut)
def create_or_update_profile(
    payload: RiderProfileIn,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderProfileOut:
    rider = upsert_profile(
        db,
        phone=principal.sub,
        name=payload.name,
        dob=payload.dob,
        address=payload.address,
        emergency_contact=payload.emergency_contact,
        preferred_zones=payload.preferred_zones,
    )
    zones = [z for z in (rider.preferred_zones or "").split(",") if z]
    return RiderProfileOut(
        rider_id=rider.id,
        phone=rider.phone,
        status=rider.status,
        name=rider.name,
        dob=rider.dob,
        address=rider.address,
        emergency_contact=rider.emergency_contact,
        preferred_zones=zones or None,
    )


@router.get("/status", response_model=RiderStatusOut)
def rider_status(
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderStatusOut:
    payload = get_status_payload(db, phone=principal.sub)
    return RiderStatusOut(**payload)


@router.get("/me", response_model=RiderProfileOut)
def me(principal: Principal = Depends(require_rider), db: Session = Depends(get_db)) -> RiderProfileOut:
    rider = get_rider_by_phone(db, principal.sub)
    zones = [z for z in (rider.preferred_zones or "").split(",") if z]
    return RiderProfileOut(
        rider_id=rider.id,
        phone=rider.phone,
        status=rider.status,
        name=rider.name,
        dob=rider.dob,
        address=rider.address,
        emergency_contact=rider.emergency_contact,
        preferred_zones=zones or None,
    )


