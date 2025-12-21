import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LessorMembershipRole(str, enum.Enum):
    OWNER = "OWNER"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class Lessor(Base):
    __tablename__ = "lessors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, index=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LessorUser(Base):
    __tablename__ = "lessor_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LessorMembership(Base):
    __tablename__ = "lessor_memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    lessor_id: Mapped[str] = mapped_column(String, index=True)  # slug as tenant key
    user_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[LessorMembershipRole] = mapped_column(Enum(LessorMembershipRole), default=LessorMembershipRole.VIEWER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LessorOtpChallengeMode(str, enum.Enum):
    SIGNUP = "SIGNUP"
    LOGIN = "LOGIN"


class LessorOtpChallenge(Base):
    __tablename__ = "lessor_otp_challenges"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone: Mapped[str] = mapped_column(String, index=True)
    otp_hash: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified: Mapped[bool] = mapped_column(default=False)  # type: ignore[arg-type]

    mode: Mapped[LessorOtpChallengeMode] = mapped_column(Enum(LessorOtpChallengeMode))
    lessor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    lessor_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class VehicleLeaseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class VehicleLease(Base):
    __tablename__ = "vehicle_leases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    lessor_id: Mapped[str] = mapped_column(String, index=True)  # slug as tenant key
    operator_id: Mapped[str] = mapped_column(String, index=True)  # operator slug
    vehicle_id: Mapped[str] = mapped_column(String, index=True)

    status: Mapped[VehicleLeaseStatus] = mapped_column(Enum(VehicleLeaseStatus), default=VehicleLeaseStatus.ACTIVE)

    start_date: Mapped[str] = mapped_column(String, default="2025-01-01")
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)

    purchase_price_inr: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    monthly_rent_inr: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    buyback_floor_inr: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


