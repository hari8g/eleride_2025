from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_rider
from app.core.security import Principal
from app.domains.kyc.schemas import KYCStartIn, KYCStatusOut
from app.domains.kyc.service import complete_kyc_pass, start_kyc


router = APIRouter(prefix="/riders/kyc")


@router.post("/start", response_model=KYCStatusOut)
def kyc_start(
    _payload: KYCStartIn,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> KYCStatusOut:
    rider = start_kyc(db, phone=principal.sub)
    return KYCStatusOut(rider_id=rider.id, status=rider.status.value)


@router.post("/complete-pass", response_model=KYCStatusOut)
def kyc_complete_pass(
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> KYCStatusOut:
    rider = complete_kyc_pass(db, phone=principal.sub)
    return KYCStatusOut(rider_id=rider.id, status=rider.status.value)


