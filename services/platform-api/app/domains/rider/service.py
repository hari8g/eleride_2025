from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.commitment_policy.service import get_active_commitment
from app.domains.rider.models import Rider, RiderStatus


def get_rider_by_phone(db: Session, phone: str) -> Rider:
    rider = db.query(Rider).filter(Rider.phone == phone).one_or_none()
    if rider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rider not found")
    return rider


def upsert_profile(
    db: Session,
    *,
    phone: str,
    name: str,
    dob: str,
    address: str,
    emergency_contact: str,
    preferred_zones: list[str] | None,
) -> Rider:
    rider = db.query(Rider).filter(Rider.phone == phone).one_or_none()
    if rider is None:
        rider = Rider(phone=phone, status=RiderStatus.NEW)
        db.add(rider)

    rider.name = name
    rider.dob = dob
    rider.address = address
    rider.emergency_contact = emergency_contact
    rider.preferred_zones = ",".join(preferred_zones or [])
    rider.status = RiderStatus.PROFILE_COMPLETED
    rider.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(rider)
    return rider


def get_status_payload(db: Session, *, phone: str) -> dict:
    rider = get_rider_by_phone(db, phone)
    commitment = get_active_commitment(db, rider_id=rider.id)
    return {
        "rider_id": rider.id,
        "phone": rider.phone,
        "status": rider.status,
        "active_commitment": commitment.to_public_dict() if commitment else None,
    }


