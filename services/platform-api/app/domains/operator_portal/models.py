import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OperatorMembershipRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    OPS = "OPS"
    MAINT = "MAINT"
    VIEWER = "VIEWER"


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, index=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OperatorUser(Base):
    __tablename__ = "operator_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OperatorMembership(Base):
    __tablename__ = "operator_memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    operator_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[OperatorMembershipRole] = mapped_column(Enum(OperatorMembershipRole), default=OperatorMembershipRole.VIEWER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OperatorOtpChallengeMode(str, enum.Enum):
    SIGNUP = "SIGNUP"
    LOGIN = "LOGIN"


class OperatorOtpChallenge(Base):
    __tablename__ = "operator_otp_challenges"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone: Mapped[str] = mapped_column(String, index=True)
    otp_hash: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified: Mapped[bool] = mapped_column(default=False)  # type: ignore[arg-type]

    mode: Mapped[OperatorOtpChallengeMode] = mapped_column(Enum(OperatorOtpChallengeMode))
    operator_name: Mapped[str | None] = mapped_column(String, nullable=True)
    operator_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OperatorInboxState(str, enum.Enum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    ONBOARDED = "ONBOARDED"
    REJECTED = "REJECTED"


class OperatorRequestInbox(Base):
    __tablename__ = "operator_request_inbox"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    operator_id: Mapped[str] = mapped_column(String, index=True)
    supply_request_id: Mapped[str] = mapped_column(String, index=True)
    state: Mapped[OperatorInboxState] = mapped_column(Enum(OperatorInboxState), default=OperatorInboxState.NEW)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class VehicleStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    IN_MAINTENANCE = "IN_MAINTENANCE"
    INACTIVE = "INACTIVE"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    operator_id: Mapped[str] = mapped_column(String, index=True)
    registration_number: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[VehicleStatus] = mapped_column(Enum(VehicleStatus), default=VehicleStatus.ACTIVE)

    model: Mapped[str | None] = mapped_column(String, nullable=True)
    meta: Mapped[str | None] = mapped_column(String, nullable=True)  # MVP: json string

    last_lat: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    last_lon: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    last_telemetry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    odometer_km: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    battery_pct: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TelematicsDevice(Base):
    __tablename__ = "telematics_devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    operator_id: Mapped[str] = mapped_column(String, index=True)
    device_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    vehicle_id: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class VehicleTelemetryEvent(Base):
    __tablename__ = "vehicle_telemetry_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    operator_id: Mapped[str] = mapped_column(String, index=True)
    vehicle_id: Mapped[str] = mapped_column(String, index=True)
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    lat: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    lon: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    speed_kph: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    odometer_km: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]
    battery_pct: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]


class MaintenanceStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    operator_id: Mapped[str] = mapped_column(String, index=True)
    vehicle_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[MaintenanceStatus] = mapped_column(Enum(MaintenanceStatus), default=MaintenanceStatus.OPEN)

    category: Mapped[str] = mapped_column(String, default="GENERAL")
    description: Mapped[str] = mapped_column(String)
    cost_inr: Mapped[float | None] = mapped_column(nullable=True)  # type: ignore[arg-type]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_takt_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Technician assignment (MVP): a maint user can "claim" a ticket.
    assigned_to_user_id: Mapped[str | None] = mapped_column(String, nullable=True)


