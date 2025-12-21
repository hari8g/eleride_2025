import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StoreWeekSignalV2(Base):
    """
    Aggregated historical signals per store/week derived from rider payout sheets.
    This is used for heuristic ranking (not time-series forecasting).
    """

    __tablename__ = "store_week_signals_v2"
    __table_args__ = (UniqueConstraint("year", "month", "week", "city", "store", name="uq_store_week_v2"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)  # week-of-month in the source sheet

    city: Mapped[str] = mapped_column(String, index=True)
    store: Mapped[str] = mapped_column(String, index=True)

    delivered_orders: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_orders: Mapped[int] = mapped_column(Integer, default=0)
    pickup_orders: Mapped[int] = mapped_column(Integer, default=0)
    weekday_orders: Mapped[int] = mapped_column(Integer, default=0)
    weekend_orders: Mapped[int] = mapped_column(Integer, default=0)
    incentivised_orders: Mapped[int] = mapped_column(Integer, default=0)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    attendance_days: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class StoreDemandRankingV2(Base):
    """
    Materialized heuristic ranking per store (lane) used by demand discovery.
    """

    __tablename__ = "store_demand_rankings_v2"
    __table_args__ = (UniqueConstraint("store", "city", name="uq_store_ranking_v2"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    city: Mapped[str] = mapped_column(String, index=True)
    store: Mapped[str] = mapped_column(String, index=True)

    # Primary rider-facing signals
    orders_per_day: Mapped[float] = mapped_column(Float)
    cancel_rate: Mapped[float] = mapped_column(Float)
    incentive_share: Mapped[float] = mapped_column(Float)
    weekend_share: Mapped[float] = mapped_column(Float)

    # Final rank score
    demand_score: Mapped[float] = mapped_column(Float, index=True)

    shift_start: Mapped[str] = mapped_column(String, default="06:00")
    contract_type: Mapped[str] = mapped_column(String, default="WEEKLY")

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


