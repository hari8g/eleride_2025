from pydantic import BaseModel, Field


class VehicleCandidate(BaseModel):
    vehicle_id: str
    registration_number: str
    operator_id: str
    status: str
    last_telemetry_at: str | None = None
    battery_pct: float | None = None
    distance_km: float | None = None
    score: float
    reasons: list[str]


class OperatorAvailability(BaseModel):
    operator_id: str
    operator_name: str | None = None
    active_vehicles: int
    available_vehicles: int
    inbox_new: int
    inbox_contacted: int
    open_maintenance_vehicles: int
    top_vehicles: list[VehicleCandidate]


class LaneAnchor(BaseModel):
    lane_id: str
    lat: float
    lon: float
    source: str


class AvailabilityOut(BaseModel):
    lane: LaneAnchor
    operators: list[OperatorAvailability]
    generated_at: str


class RecommendIn(BaseModel):
    lane_id: str = Field(min_length=1, max_length=128)
    rider_lat: float | None = None
    rider_lon: float | None = None
    max_km: float = Field(default=8.0, ge=0.5, le=50.0)
    min_battery_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    max_telemetry_age_min: float = Field(default=120.0, ge=1.0, le=24 * 60.0)
    limit: int = Field(default=8, ge=1, le=30)


class RecommendOut(BaseModel):
    lane: LaneAnchor
    recommended: VehicleCandidate | None = None
    alternatives: list[VehicleCandidate]
    generated_at: str


class AuditRow(BaseModel):
    request_id: str
    created_at: str
    rider_id: str
    lane_id: str
    supply_status: str
    operator_id: str | None = None
    pickup_location: str | None = None
    matched_vehicle_id: str | None = None
    matched_score: float | None = None
    matched_reasons: list[str] | None = None


class AuditRecentOut(BaseModel):
    items: list[AuditRow]


