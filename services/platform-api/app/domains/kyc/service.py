from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.rider.models import Rider, RiderStatus


def _get_rider(db: Session, phone: str) -> Rider:
    rider = db.query(Rider).filter(Rider.phone == phone).one_or_none()
    if rider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rider not found")
    return rider


def start_kyc(db: Session, *, phone: str) -> Rider:
    rider = _get_rider(db, phone)
    rider.status = RiderStatus.KYC_IN_PROGRESS
    rider.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rider)
    return rider


def complete_kyc_pass(db: Session, *, phone: str) -> Rider:
    rider = _get_rider(db, phone)
    rider.status = RiderStatus.VERIFIED_PENDING_SUPPLY_MATCH
    rider.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rider)
    return rider


