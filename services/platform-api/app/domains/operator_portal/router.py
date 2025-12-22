from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_operator, require_operator_roles
from app.core.security import Principal
from app.domains.operator_portal.models import OperatorMembershipRole, OperatorOtpChallengeMode
from app.domains.operator_portal.schemas import (
    DashboardSummaryOut,
    InboxListOut,
    InboxRequestDetailOut,
    InboxUpdateIn,
    MaintenanceCreateIn,
    MaintenanceAssignIn,
    MaintenanceListOut,
    MaintenanceOut,
    MaintenanceTaktUpdateIn,
    OpenMaintenanceListOut,
    OperatorMeOut,
    OperatorOtpRequestIn,
    OperatorOtpRequestOut,
    OperatorOtpVerifyIn,
    OperatorSessionOut,
    TelematicsBindIn,
    TelemetryIn,
    VehicleCreateIn,
    VehicleListOut,
    VehicleOut,
)
from app.domains.operator_portal.service import (
    dashboard_summary,
    seed_demo_fleet,
    reset_and_seed_demo_fleet,
    bind_device,
    create_maintenance,
    close_maintenance_ticket,
    assign_maintenance_ticket,
    create_vehicle,
    list_open_maintenance,
    update_maintenance_takt_time,
    reset_operator_inbox,
    get_inbox_request_detail,
    get_operator_me,
    ingest_telemetry,
    list_inbox,
    list_maintenance,
    list_vehicles,
    request_operator_otp,
    upsert_inbox_state,
    verify_operator_otp,
)


router = APIRouter(prefix="/operator")


@router.post("/auth/otp/request", response_model=OperatorOtpRequestOut)
def operator_otp_request(payload: OperatorOtpRequestIn, db: Session = Depends(get_db)) -> OperatorOtpRequestOut:
    mode = OperatorOtpChallengeMode.SIGNUP if payload.mode == "signup" else OperatorOtpChallengeMode.LOGIN
    ch = request_operator_otp(
        db,
        phone=payload.phone,
        mode=mode,
        operator_name=payload.operator_name,
        operator_slug=payload.operator_slug,
    )
    dev_otp = getattr(ch, "_dev_otp", None) if settings.env == "dev" else None
    return OperatorOtpRequestOut(request_id=ch.id, expires_in_seconds=settings.otp_ttl_seconds, dev_otp=dev_otp)


@router.post("/auth/otp/verify", response_model=OperatorSessionOut)
def operator_otp_verify(payload: OperatorOtpVerifyIn, db: Session = Depends(get_db)) -> OperatorSessionOut:
    s = verify_operator_otp(db, request_id=payload.request_id, otp=payload.otp)
    return OperatorSessionOut(**s)


@router.get("/me", response_model=OperatorMeOut)
def me(principal: Principal = Depends(require_operator), db: Session = Depends(get_db)) -> OperatorMeOut:
    data = get_operator_me(db, operator_id=principal.operator_id, user_id=principal.sub)  # type: ignore[arg-type]
    return OperatorMeOut(**data)


@router.get("/dashboard/summary", response_model=DashboardSummaryOut)
def dashboard(principal: Principal = Depends(require_operator), db: Session = Depends(get_db)) -> DashboardSummaryOut:
    s = dashboard_summary(db, operator_id=principal.operator_id)  # type: ignore[arg-type]
    return DashboardSummaryOut(**s)


@router.get(
    "/maintenance/open",
    response_model=OpenMaintenanceListOut,
)
def open_maintenance_feed(
    principal: Principal = Depends(
        require_operator_roles(
            {
                OperatorMembershipRole.OWNER.value,
                OperatorMembershipRole.ADMIN.value,
                OperatorMembershipRole.MAINT.value,
                OperatorMembershipRole.OPS.value,
            }
        )
    ),
    db: Session = Depends(get_db),
) -> OpenMaintenanceListOut:
    payload = list_open_maintenance(db, operator_id=principal.operator_id)  # type: ignore[arg-type]
    return OpenMaintenanceListOut(**payload)  # type: ignore[arg-type]


@router.post("/admin/seed-demo", response_model=dict)
def seed_demo(
    vehicles: int = 25,
    principal: Principal = Depends(require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value})),
    db: Session = Depends(get_db),
) -> dict:
    return seed_demo_fleet(db, operator_id=principal.operator_id, vehicles=vehicles)  # type: ignore[arg-type]


@router.post("/admin/reset-seed", response_model=dict)
def reset_seed_demo(
    vehicles: int = 30,
    maintenance_ratio: float = 0.18,
    inactive_ratio: float = 0.08,
    principal: Principal = Depends(require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value})),
    db: Session = Depends(get_db),
) -> dict:
    return reset_and_seed_demo_fleet(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        vehicles=vehicles,
        maintenance_ratio=maintenance_ratio,
        inactive_ratio=inactive_ratio,
    )


@router.post("/admin/inbox/reset", response_model=dict)
def reset_inbox(
    principal: Principal = Depends(require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value})),
    db: Session = Depends(get_db),
) -> dict:
    return reset_operator_inbox(db, operator_id=principal.operator_id)  # type: ignore[arg-type]


@router.get("/inbox/requests", response_model=InboxListOut)
def inbox(principal: Principal = Depends(require_operator), db: Session = Depends(get_db)) -> InboxListOut:
    items = list_inbox(db, operator_id=principal.operator_id)  # type: ignore[arg-type]
    return InboxListOut(items=items)


@router.get("/inbox/requests/{supply_request_id}", response_model=InboxRequestDetailOut)
def inbox_detail(
    supply_request_id: str,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> InboxRequestDetailOut:
    d = get_inbox_request_detail(db, operator_id=principal.operator_id, supply_request_id=supply_request_id)  # type: ignore[arg-type]
    return InboxRequestDetailOut(**d)


@router.post("/inbox/requests/{supply_request_id}/state", response_model=dict)
def update_inbox_state(
    supply_request_id: str,
    payload: InboxUpdateIn,
    principal: Principal = Depends(require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value, OperatorMembershipRole.OPS.value})),
    db: Session = Depends(get_db),
) -> dict:
    row = upsert_inbox_state(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        supply_request_id=supply_request_id,
        state=payload.state,
        note=payload.note,
    )
    return {"ok": True, "state": row.state.value}


@router.post("/vehicles", response_model=VehicleOut)
def create_vehicle_route(
    payload: VehicleCreateIn,
    principal: Principal = Depends(require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value})),
    db: Session = Depends(get_db),
) -> VehicleOut:
    v = create_vehicle(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        registration_number=payload.registration_number,
        model=payload.model,
        meta=payload.meta,
    )
    return VehicleOut(
        id=v.id,
        registration_number=v.registration_number,
        status=v.status,
        model=v.model,
        meta=v.meta,
        last_lat=v.last_lat,
        last_lon=v.last_lon,
        last_telemetry_at=v.last_telemetry_at.isoformat() if v.last_telemetry_at else None,
        odometer_km=v.odometer_km,
        battery_pct=v.battery_pct,
    )


@router.get("/vehicles", response_model=VehicleListOut)
def vehicles(principal: Principal = Depends(require_operator), db: Session = Depends(get_db)) -> VehicleListOut:
    items = list_vehicles(db, operator_id=principal.operator_id)  # type: ignore[arg-type]
    return VehicleListOut(
        items=[
            VehicleOut(
                id=v.id,
                registration_number=v.registration_number,
                status=v.status,
                model=v.model,
                meta=v.meta,
                last_lat=v.last_lat,
                last_lon=v.last_lon,
                last_telemetry_at=v.last_telemetry_at.isoformat() if v.last_telemetry_at else None,
                odometer_km=v.odometer_km,
                battery_pct=v.battery_pct,
            )
            for v in items
        ]
    )


@router.post("/vehicles/{vehicle_id}/devices", response_model=dict)
def bind_device_route(
    vehicle_id: str,
    payload: TelematicsBindIn,
    principal: Principal = Depends(require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value})),
    db: Session = Depends(get_db),
) -> dict:
    d = bind_device(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        vehicle_id=vehicle_id,
        device_id=payload.device_id,
        provider=payload.provider,
    )
    return {"ok": True, "device_id": d.device_id}


@router.post("/vehicles/{vehicle_id}/telemetry", response_model=dict)
def telemetry_route(
    vehicle_id: str,
    payload: TelemetryIn,
    principal: Principal = Depends(
        require_operator_roles(
            {
                OperatorMembershipRole.OWNER.value,
                OperatorMembershipRole.ADMIN.value,
                OperatorMembershipRole.OPS.value,
                OperatorMembershipRole.MAINT.value,
            }
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    ingest_telemetry(db, operator_id=principal.operator_id, vehicle_id=vehicle_id, payload=payload.model_dump())  # type: ignore[arg-type]
    return {"ok": True}


@router.post("/vehicles/{vehicle_id}/maintenance", response_model=MaintenanceOut)
def create_maintenance_route(
    vehicle_id: str,
    payload: MaintenanceCreateIn,
    principal: Principal = Depends(
        require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value, OperatorMembershipRole.MAINT.value})
    ),
    db: Session = Depends(get_db),
) -> MaintenanceOut:
    r = create_maintenance(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        vehicle_id=vehicle_id,
        category=payload.category,
        description=payload.description,
        cost_inr=payload.cost_inr,
        expected_takt_hours=payload.expected_takt_hours,
    )
    return MaintenanceOut(
        id=r.id,
        vehicle_id=r.vehicle_id,
        status=r.status,
        category=r.category,
        description=r.description,
        cost_inr=r.cost_inr,
        created_at=r.created_at.isoformat(),
        updated_at=r.updated_at.isoformat() if getattr(r, "updated_at", None) else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        expected_ready_at=r.expected_ready_at.isoformat() if r.expected_ready_at else None,
        expected_takt_hours=r.expected_takt_hours,
        assigned_to_user_id=getattr(r, "assigned_to_user_id", None),
    )


@router.post("/vehicles/{vehicle_id}/maintenance/{record_id}/close", response_model=MaintenanceOut)
def close_maintenance_route(
    vehicle_id: str,
    record_id: str,
    principal: Principal = Depends(
        require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value, OperatorMembershipRole.MAINT.value})
    ),
    db: Session = Depends(get_db),
) -> MaintenanceOut:
    r = close_maintenance_ticket(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        vehicle_id=vehicle_id,
        record_id=record_id,
    )
    return MaintenanceOut(
        id=r.id,
        vehicle_id=r.vehicle_id,
        status=r.status,
        category=r.category,
        description=r.description,
        cost_inr=r.cost_inr,
        created_at=r.created_at.isoformat(),
        updated_at=r.updated_at.isoformat() if getattr(r, "updated_at", None) else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        expected_ready_at=r.expected_ready_at.isoformat() if r.expected_ready_at else None,
        expected_takt_hours=r.expected_takt_hours,
        assigned_to_user_id=getattr(r, "assigned_to_user_id", None),
    )


@router.post("/vehicles/{vehicle_id}/maintenance/{record_id}/takt", response_model=MaintenanceOut)
def update_takt_route(
    vehicle_id: str,
    record_id: str,
    payload: MaintenanceTaktUpdateIn,
    principal: Principal = Depends(
        require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value, OperatorMembershipRole.MAINT.value})
    ),
    db: Session = Depends(get_db),
) -> MaintenanceOut:
    r = update_maintenance_takt_time(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        vehicle_id=vehicle_id,
        record_id=record_id,
        expected_takt_hours=payload.expected_takt_hours,
    )
    return MaintenanceOut(
        id=r.id,
        vehicle_id=r.vehicle_id,
        status=r.status,
        category=r.category,
        description=r.description,
        cost_inr=r.cost_inr,
        created_at=r.created_at.isoformat(),
        updated_at=r.updated_at.isoformat() if getattr(r, "updated_at", None) else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        expected_ready_at=r.expected_ready_at.isoformat() if r.expected_ready_at else None,
        expected_takt_hours=r.expected_takt_hours,
        assigned_to_user_id=getattr(r, "assigned_to_user_id", None),
    )


@router.post("/vehicles/{vehicle_id}/maintenance/{record_id}/assign", response_model=MaintenanceOut)
def assign_maintenance_route(
    vehicle_id: str,
    record_id: str,
    payload: MaintenanceAssignIn,
    principal: Principal = Depends(
        require_operator_roles({OperatorMembershipRole.OWNER.value, OperatorMembershipRole.ADMIN.value, OperatorMembershipRole.MAINT.value})
    ),
    db: Session = Depends(get_db),
) -> MaintenanceOut:
    r = assign_maintenance_ticket(
        db,
        operator_id=principal.operator_id,  # type: ignore[arg-type]
        vehicle_id=vehicle_id,
        record_id=record_id,
        assigned_to_user_id=(principal.sub if payload.assigned else None),
    )
    return MaintenanceOut(
        id=r.id,
        vehicle_id=r.vehicle_id,
        status=r.status,
        category=r.category,
        description=r.description,
        cost_inr=r.cost_inr,
        created_at=r.created_at.isoformat(),
        updated_at=r.updated_at.isoformat() if getattr(r, "updated_at", None) else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        expected_ready_at=r.expected_ready_at.isoformat() if r.expected_ready_at else None,
        expected_takt_hours=r.expected_takt_hours,
        assigned_to_user_id=getattr(r, "assigned_to_user_id", None),
    )


@router.get("/vehicles/{vehicle_id}/maintenance", response_model=MaintenanceListOut)
def maintenance_list_route(
    vehicle_id: str,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MaintenanceListOut:
    items = list_maintenance(db, operator_id=principal.operator_id, vehicle_id=vehicle_id)  # type: ignore[arg-type]
    return MaintenanceListOut(
        items=[
            MaintenanceOut(
                id=r.id,
                vehicle_id=r.vehicle_id,
                status=r.status,
                category=r.category,
                description=r.description,
                cost_inr=r.cost_inr,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat() if getattr(r, "updated_at", None) else None,
                completed_at=r.completed_at.isoformat() if r.completed_at else None,
                expected_ready_at=r.expected_ready_at.isoformat() if r.expected_ready_at else None,
                expected_takt_hours=r.expected_takt_hours,
                assigned_to_user_id=getattr(r, "assigned_to_user_id", None),
            )
            for r in items
        ]
    )


