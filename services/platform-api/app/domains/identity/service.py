from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, generate_otp, hash_otp, verify_otp_hash
from app.domains.identity.models import OTPChallenge
from app.domains.rider.models import Rider, RiderStatus
from app.utils.sms import msg91_missing_fields, msg91_channels_available, send_otp_best_effort


def request_otp(db: Session, phone: str) -> tuple[OTPChallenge, str]:
    # In dev OR otp_dev_mode, we allow OTP issuance even if messaging isn't configured
    # (dev_otp will be returned by the router).
    if settings.env != "dev" and not settings.otp_dev_mode:
        missing = msg91_missing_fields()
        if missing:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "OTP_SMS_NOT_CONFIGURED", "missing": missing},
            )

        channels = msg91_channels_available()
        if not channels.get("whatsapp") and not channels.get("sms"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "OTP_CHANNELS_NOT_CONFIGURED",
                    "message": "Configure WhatsApp Flow or SMS template for OTP delivery.",
                    "channels": channels,
                },
            )

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

    # In dev mode, don't attempt to send; just return dev_otp to the client.
    if settings.env == "dev" or settings.otp_dev_mode:
        return challenge, otp

    ok, channel, debug = send_otp_best_effort(phone, otp)
    if not ok and settings.env != "dev" and not settings.otp_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OTP_SEND_FAILED", "message": "Could not deliver OTP via configured channels.", "debug": debug},
        )

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


