import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SupplyRequestStatus(str, enum.Enum):
    CREATED = "CREATED"
    MATCHED = "MATCHED"
    REJECTED = "REJECTED"


class SupplyRequest(Base):
    __tablename__ = "supply_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rider_id: Mapped[str] = mapped_column(String, index=True)
    lane_id: Mapped[str] = mapped_column(String)
    time_window: Mapped[str | None] = mapped_column(String, nullable=True)
    requirements: Mapped[str | None] = mapped_column(String, nullable=True)

    operator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pickup_location: Mapped[str | None] = mapped_column(String, nullable=True)

    # Matchmaking audit (MVP): store which vehicle was used for auto-assign and the rationale.
    matched_vehicle_id: Mapped[str | None] = mapped_column(String, nullable=True)
    matched_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_reasons: Mapped[str | None] = mapped_column(String, nullable=True)  # MVP: JSON string

    # Pickup flow:
    # - When ONBOARDED, rider receives pickup QR.
    # - Workflow is considered "closed" only after the pickup QR is verified by the fleet portal.
    pickup_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pickup_verified_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[SupplyRequestStatus] = mapped_column(Enum(SupplyRequestStatus), default=SupplyRequestStatus.CREATED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


