import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RiderStatus(str, enum.Enum):
    NEW = "NEW"
    PROFILE_COMPLETED = "PROFILE_COMPLETED"
    KYC_IN_PROGRESS = "KYC_IN_PROGRESS"
    VERIFIED_PENDING_SUPPLY_MATCH = "VERIFIED_PENDING_SUPPLY_MATCH"


class Rider(Base):
    __tablename__ = "riders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone: Mapped[str] = mapped_column(String, unique=True, index=True)

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    dob: Mapped[str | None] = mapped_column(String, nullable=True)  # MVP: keep as string
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_zones: Mapped[str | None] = mapped_column(String, nullable=True)  # MVP: comma-separated

    status: Mapped[RiderStatus] = mapped_column(Enum(RiderStatus), default=RiderStatus.NEW)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


