from pydantic import BaseModel, Field

from app.domains.leasing_portal.models import LessorMembershipRole, VehicleLeaseStatus


class LessorOtpRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    mode: str = Field(pattern="^(signup|login)$")
    lessor_name: str | None = Field(default=None, max_length=128)
    lessor_slug: str | None = Field(default=None, max_length=64)


class LessorOtpRequestOut(BaseModel):
    request_id: str
    expires_in_seconds: int
    dev_otp: str | None = None


class LessorOtpVerifyIn(BaseModel):
    request_id: str
    otp: str = Field(min_length=4, max_length=10)


class LessorSessionOut(BaseModel):
    access_token: str
    lessor_id: str
    lessor_name: str
    lessor_slug: str
    user_id: str
    user_phone: str
    role: LessorMembershipRole


class LessorMeOut(BaseModel):
    lessor_id: str
    lessor_name: str
    lessor_slug: str
    user_id: str
    user_phone: str
    role: LessorMembershipRole


class PartnerSummary(BaseModel):
    operator_id: str
    vehicles_leased: int
    vehicles_valued: int
    # Fleet-level signals (match operator portal)
    fleet_vehicles_active: int
    fleet_open_tickets: int
    fleet_low_battery: int
    fleet_avg_battery_pct: float | None = None

    # Covered/leased signals (subset of fleet)
    leased_vehicles_active: int
    leased_open_tickets: int
    leased_vehicles_in_maintenance: int
    leased_low_battery: int
    est_buyback_value_inr: float


class LessorDashboardOut(BaseModel):
    vehicles_leased_total: int
    vehicles_valued_total: int
    active_leases: int
    partners: list[PartnerSummary]
    est_buyback_value_total_inr: float


class LeasedVehicleRow(BaseModel):
    vehicle_id: str
    registration_number: str
    operator_id: str
    status: str
    last_lat: float | None = None
    last_lon: float | None = None
    odometer_km: float | None = None
    battery_pct: float | None = None
    lease_status: VehicleLeaseStatus
    purchase_price_inr: float | None = None
    monthly_rent_inr: float | None = None
    start_date: str


class LeasedVehiclesOut(BaseModel):
    items: list[LeasedVehicleRow]


class BuybackEstimateOut(BaseModel):
    vehicle_id: str
    registration_number: str
    operator_id: str
    estimated_value_inr: float
    floor_inr: float | None = None
    reasons: list[str]


