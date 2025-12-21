from pydantic import BaseModel, Field

from app.domains.commitment_policy.models import CommitmentLockMode


class CommitmentCreateIn(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    lane_id: str = Field(min_length=1, max_length=128)
    min_days: int = Field(default=7, ge=1, le=30)
    lock_mode: CommitmentLockMode = CommitmentLockMode.RESTRICT_TO_LANE


class CommitmentOut(BaseModel):
    id: str
    operator_id: str
    lane_id: str
    lock_mode: str
    status: str
    starts_at: str
    ends_at: str


class CommitmentCancelOut(BaseModel):
    id: str
    status: str


