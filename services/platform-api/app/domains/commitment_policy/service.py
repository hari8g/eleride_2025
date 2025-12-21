from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.commitment_policy.models import (
    Commitment,
    CommitmentLockMode,
    CommitmentStatus,
)


class PolicyDecision:
    def __init__(
        self,
        *,
        allowed: bool,
        reason: str | None = None,
        unlock_at: datetime | None = None,
        allowed_lane_id: str | None = None,
    ) -> None:
        self.allowed = allowed
        self.reason = reason
        self.unlock_at = unlock_at
        self.allowed_lane_id = allowed_lane_id

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "unlock_at": self.unlock_at.isoformat() if self.unlock_at else None,
            "allowed_lane_id": self.allowed_lane_id,
        }


def get_active_commitment(db: Session, *, rider_id: str) -> Commitment | None:
    now = datetime.now(timezone.utc)
    commitment = (
        db.query(Commitment)
        .filter(
            Commitment.rider_id == rider_id,
            Commitment.status == CommitmentStatus.ACTIVE,
        )
        .order_by(Commitment.created_at.desc())
        .first()
    )
    if commitment and commitment.is_active_at(now):
        return commitment
    return None


def check_access(db: Session, *, rider_id: str, action: str) -> PolicyDecision:
    # MVP actions:
    # - VIEW_DEMAND: gate demand discovery
    active = get_active_commitment(db, rider_id=rider_id)
    if not active:
        return PolicyDecision(allowed=True)

    if action == "VIEW_DEMAND":
        if active.lock_mode == CommitmentLockMode.HIDE_ALL_DEMAND:
            return PolicyDecision(
                allowed=False,
                reason="COMMITMENT_LOCKED",
                unlock_at=active.ends_at,
            )
        return PolicyDecision(
            allowed=True,
            reason="COMMITMENT_RESTRICTED_TO_LANE",
            unlock_at=active.ends_at,
            allowed_lane_id=active.lane_id,
        )

    return PolicyDecision(allowed=True)


def create_commitment(
    db: Session,
    *,
    rider_id: str,
    operator_id: str,
    lane_id: str,
    min_days: int,
    lock_mode: CommitmentLockMode,
) -> Commitment:
    now = datetime.now(timezone.utc)
    commitment = Commitment(
        rider_id=rider_id,
        operator_id=operator_id,
        lane_id=lane_id,
        lock_mode=lock_mode,
        status=CommitmentStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=min_days),
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)
    return commitment


def cancel_commitment_admin(db: Session, *, commitment_id: str, reason: str = "ADMIN_CANCEL") -> Commitment:
    commitment = db.get(Commitment, commitment_id)
    if not commitment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commitment not found")
    if commitment.status != CommitmentStatus.ACTIVE:
        return commitment
    commitment.status = CommitmentStatus.CANCELLED
    commitment.cancel_reason = reason
    commitment.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(commitment)
    return commitment


