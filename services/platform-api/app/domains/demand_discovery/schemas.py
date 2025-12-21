from pydantic import BaseModel


class DemandCard(BaseModel):
    lane_id: str
    qc_name: str
    lat: float | None = None
    lon: float | None = None
    distance_km: float
    shift_start: str
    earning_range: str
    minimum_guarantee: str
    expected_trips_per_day: int | None = None
    expected_orders_per_day: float | None = None
    contract_type: str
    slots_available: str
    rank_reasons: list[str] | None = None


class DemandNearbyOut(BaseModel):
    policy: dict
    cards: list[DemandCard]


