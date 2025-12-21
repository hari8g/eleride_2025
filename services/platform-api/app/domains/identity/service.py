from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, generate_otp, hash_otp, verify_otp_hash
from app.domains.identity.models import OTPChallenge
from app.domains.rider.models import Rider, RiderStatus
from app.utils.sms import send_otp_msg91


def request_otp(db: Session, phone: str) -> tuple[OTPChallenge, str]:
    otp = generate_otp()
    challenge = OTPChallenge(
        phone=phone,
        otp_hash=hash_otp(phone, otp),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.otp_ttl_seconds),
        verified=False,
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    # Send SMS via MSG91 (best effort)
    try:
        send_otp_msg91(phone, otp)
    except Exception:
        pass

    return challenge, otp


def verify_otp(db: Session, request_id: str, otp: str) -> str:
    challenge = db.get(OTPChallenge, request_id)
    if not challenge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request_id")
    if challenge.verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP already used")
    if datetime.now(timezone.utc) > challenge.expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")
    if not verify_otp_hash(challenge.phone, otp, challenge.otp_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    challenge.verified = True

    # Bootstrap rider record (principal "sub" is phone for MVP)
    rider = db.query(Rider).filter(Rider.phone == challenge.phone).one_or_none()
    if rider is None:
        rider = Rider(phone=challenge.phone, status=RiderStatus.NEW)
        db.add(rider)

    db.commit()

    return create_access_token(sub=challenge.phone, role="rider")


