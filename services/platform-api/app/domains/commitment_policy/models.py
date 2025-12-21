import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CommitmentLockMode(str, enum.Enum):
    RESTRICT_TO_LANE = "RESTRICT_TO_LANE"
    HIDE_ALL_DEMAND = "HIDE_ALL_DEMAND"


class CommitmentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class Commitment(Base):
    __tablename__ = "commitments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rider_id: Mapped[str] = mapped_column(String, index=True)

    operator_id: Mapped[str] = mapped_column(String)
    lane_id: Mapped[str] = mapped_column(String)

    lock_mode: Mapped[CommitmentLockMode] = mapped_column(Enum(CommitmentLockMode))
    status: Mapped[CommitmentStatus] = mapped_column(Enum(CommitmentStatus), default=CommitmentStatus.ACTIVE)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    def is_active_at(self, now: datetime) -> bool:
        if self.status != CommitmentStatus.ACTIVE:
            return False
        return self.starts_at <= now < self.ends_at

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "operator_id": self.operator_id,
            "lane_id": self.lane_id,
            "lock_mode": self.lock_mode.value,
            "status": self.status.value,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
        }


