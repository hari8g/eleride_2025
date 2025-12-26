from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.domains.identity.schemas import OTPRequestIn, OTPRequestOut, OTPVerifyIn, OTPVerifyOut
from app.domains.identity.service import request_otp, verify_otp


router = APIRouter(prefix="/auth")


@router.post("/otp/request", response_model=OTPRequestOut)
def otp_request(payload: OTPRequestIn, db: Session = Depends(get_db)) -> OTPRequestOut:
    challenge, otp = request_otp(db, payload.phone)
    dev_otp = otp if (settings.env == "dev" or settings.otp_dev_mode) else None
    return OTPRequestOut(
        request_id=challenge.id,
        expires_in_seconds=settings.otp_ttl_seconds,
        dev_otp=dev_otp,
    )


@router.post("/otp/verify", response_model=OTPVerifyOut)
def otp_verify(payload: OTPVerifyIn, db: Session = Depends(get_db)) -> OTPVerifyOut:
    token = verify_otp(db, payload.request_id, payload.otp)
    return OTPVerifyOut(access_token=token)


