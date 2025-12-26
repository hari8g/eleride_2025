from pydantic import BaseModel, Field

from app.domains.operator_portal.models import (
    MaintenanceStatus,
    OperatorInboxState,
    OperatorMembershipRole,
    VehicleStatus,
)


class OperatorOtpRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    mode: str = Field(pattern="^(signup|login)$")
    operator_name: str | None = Field(default=None, max_length=128)
    operator_slug: str | None = Field(default=None, max_length=64)


class OperatorOtpRequestOut(BaseModel):
    request_id: str
    expires_in_seconds: int
    dev_otp: str | None = None


class OperatorOtpVerifyIn(BaseModel):
    request_id: str
    otp: str = Field(min_length=4, max_length=10)


class OperatorSessionOut(BaseModel):
    access_token: str
    operator_id: str
    operator_name: str
    operator_slug: str
    user_id: str
    user_phone: str
    role: OperatorMembershipRole


class OperatorMeOut(BaseModel):
    operator_id: str
    operator_name: str
    operator_slug: str
    user_id: str
    user_phone: str
    role: OperatorMembershipRole


class InboxRiderSnapshot(BaseModel):
    rider_id: str
    phone: str
    name: str | None = None
    preferred_zones: list[str] | None = None
    status: str


class InboxRequestItem(BaseModel):
    supply_request_id: str
    lane_id: str
    created_at: str
    inbox_updated_at: str | None = None
    pickup_location: str | None = None
    matched_vehicle_id: str | None = None
    state: OperatorInboxState
    note: str | None = None
    rider: InboxRiderSnapshot


class InboxListOut(BaseModel):
    items: list[InboxRequestItem]


class InboxRiderDetail(BaseModel):
    rider_id: str
    phone: str
    name: str | None = None
    dob: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    preferred_zones: list[str] | None = None
    status: str


class InboxRequestDetailOut(BaseModel):
    supply_request_id: str
    lane_id: str
    created_at: str
    inbox_updated_at: str | None = None
    pickup_location: str | None = None
    time_window: str | None = None
    requirements: str | None = None
    matched_vehicle_id: str | None = None
    state: OperatorInboxState
    note: str | None = None
    rider: InboxRiderDetail


class InboxAcceptOut(BaseModel):
    ok: bool = True
    state: OperatorInboxState
    matched_vehicle_id: str
    matched_vehicle_registration_number: str
    matched_score: float | None = None
    matched_reasons: list[str] | None = None


class PickupVerifyIn(BaseModel):
    pickup_code: str = Field(min_length=4, max_length=16)


class PickupVerifyOut(BaseModel):
    ok: bool = True
    pickup_verified_at: str


class InboxUpdateIn(BaseModel):
    state: OperatorInboxState
    note: str | None = Field(default=None, max_length=256)


class VehicleCreateIn(BaseModel):
    registration_number: str = Field(min_length=3, max_length=32)
    model: str | None = Field(default=None, max_length=64)
    meta: str | None = Field(default=None, max_length=1024)


class VehicleOut(BaseModel):
    id: str
    registration_number: str
    status: VehicleStatus
    model: str | None = None
    meta: str | None = None
    last_lat: float | None = None
    last_lon: float | None = None
    last_telemetry_at: str | None = None
    odometer_km: float | None = None
    battery_pct: float | None = None


class VehicleListOut(BaseModel):
    items: list[VehicleOut]


class TelematicsBindIn(BaseModel):
    device_id: str = Field(min_length=3, max_length=64)
    provider: str | None = Field(default=None, max_length=64)


class TelemetryIn(BaseModel):
    device_id: str | None = Field(default=None, max_length=64)
    lat: float | None = None
    lon: float | None = None
    speed_kph: float | None = None
    odometer_km: float | None = None
    battery_pct: float | None = None


class MaintenanceCreateIn(BaseModel):
    category: str = Field(default="GENERAL", max_length=32)
    description: str = Field(min_length=3, max_length=512)
    cost_inr: float | None = None
    expected_takt_hours: float | None = Field(default=24.0, ge=1.0, le=24.0 * 30.0)


class MaintenanceOut(BaseModel):
    id: str
    vehicle_id: str
    status: MaintenanceStatus
    category: str
    description: str
    cost_inr: float | None = None
    created_at: str
    updated_at: str | None = None
    completed_at: str | None = None
    expected_ready_at: str | None = None
    expected_takt_hours: float | None = None
    assigned_to_user_id: str | None = None


class MaintenanceListOut(BaseModel):
    items: list[MaintenanceOut]


class MaintenanceTaktUpdateIn(BaseModel):
    expected_takt_hours: float = Field(default=24.0, ge=1.0, le=24.0 * 30.0)


class OpenMaintenanceItemOut(BaseModel):
    record_id: str
    vehicle_id: str
    registration_number: str
    vehicle_status: VehicleStatus
    model: str | None = None

    category: str
    description: str
    status: MaintenanceStatus
    created_at: str
    updated_at: str | None = None
    expected_ready_at: str | None = None
    expected_takt_hours: float | None = None
    assigned_to_user_id: str | None = None

    last_lat: float | None = None
    last_lon: float | None = None
    last_telemetry_at: str | None = None
    odometer_km: float | None = None
    battery_pct: float | None = None


class OpenMaintenanceListOut(BaseModel):
    total_open: int
    items: list[OpenMaintenanceItemOut]


class DashboardArenaOut(BaseModel):
    name: str
    vehicles_total: int
    vehicles_active: int
    vehicles_in_maintenance: int
    avg_battery_pct: float | None = None


class DashboardSummaryOut(BaseModel):
    vehicles_total: int
    vehicles_active: int
    vehicles_in_maintenance: int
    vehicles_inactive: int
    low_battery_count: int
    avg_battery_pct: float | None = None
    open_maintenance_count: int
    open_maintenance_ticket_count: int
    open_maintenance_assigned_ticket_count: int
    open_maintenance_unassigned_ticket_count: int
    open_maintenance_overdue_count: int
    inbox_new: int
    inbox_contacted: int
    inbox_onboarded: int
    inbox_rejected: int
    arenas: list[DashboardArenaOut]


class MaintenanceAssignIn(BaseModel):
    assigned: bool = True



