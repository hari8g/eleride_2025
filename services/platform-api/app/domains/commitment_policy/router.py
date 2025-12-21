from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin, require_rider
from app.core.security import Principal
from app.domains.commitment_policy.schemas import CommitmentCancelOut, CommitmentCreateIn, CommitmentOut
from app.domains.commitment_policy.service import cancel_commitment_admin, create_commitment, get_active_commitment
from app.domains.rider.service import get_rider_by_phone


router = APIRouter(prefix="/commitments")


@router.post("", response_model=CommitmentOut)
def create(
    payload: CommitmentCreateIn,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> CommitmentOut:
    rider = get_rider_by_phone(db, principal.sub)
    commitment = create_commitment(
        db,
        rider_id=rider.id,
        operator_id=payload.operator_id,
        lane_id=payload.lane_id,
        min_days=payload.min_days,
        lock_mode=payload.lock_mode,
    )
    return CommitmentOut(**commitment.to_public_dict())


@router.get("/active", response_model=CommitmentOut | None)
def active(
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> CommitmentOut | None:
    rider = get_rider_by_phone(db, principal.sub)
    commitment = get_active_commitment(db, rider_id=rider.id)
    return CommitmentOut(**commitment.to_public_dict()) if commitment else None


@router.post("/{commitment_id}/cancel", response_model=CommitmentCancelOut)
def cancel(
    commitment_id: str,
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CommitmentCancelOut:
    commitment = cancel_commitment_admin(db, commitment_id=commitment_id)
    return CommitmentCancelOut(id=commitment.id, status=commitment.status.value)


