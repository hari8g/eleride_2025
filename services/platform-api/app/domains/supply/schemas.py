from pydantic import BaseModel, Field


class SupplyRequestCreateIn(BaseModel):
    lane_id: str = Field(min_length=1, max_length=128)
    time_window: str | None = Field(default=None, max_length=128)
    requirements: str | None = Field(default=None, max_length=512)
    # Optional: rider location to improve matchmaking quality.
    rider_lat: float | None = None
    rider_lon: float | None = None
    # Optional: rider-selected operator (if offering choices).
    operator_id: str | None = Field(default=None, max_length=64)


class SupplyRequestCreateOut(BaseModel):
    request_id: str
    status: str
    next_step: str
    operator: dict


class RiderSupplyStageOut(BaseModel):
    code: str
    label: str
    detail: str | None = None


class RiderSupplyStatusOut(BaseModel):
    request_id: str
    created_at: str
    supply_status: str

    operator_id: str | None = None
    operator_name: str | None = None
    pickup_location: str | None = None
    pickup_lat: float | None = None
    pickup_lon: float | None = None

    matched_vehicle_id: str | None = None
    matched_vehicle_registration_number: str | None = None
    matched_score: float | None = None
    matched_reasons: list[str] | None = None

    # Present only when approved (ONBOARDED): QR to be scanned at pickup for handover.
    pickup_qr_png_base64: str | None = None
    pickup_qr_code: str | None = None
    pickup_verified_at: str | None = None

    inbox_state: str
    inbox_note: str | None = None
    inbox_updated_at: str | None = None

    stage: RiderSupplyStageOut


