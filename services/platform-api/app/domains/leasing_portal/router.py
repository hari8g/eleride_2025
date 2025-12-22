from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_lessor, require_lessor_roles
from app.core.security import Principal
from app.domains.leasing_portal.models import LessorMembershipRole, LessorOtpChallengeMode
from app.domains.leasing_portal.schemas import (
    BuybackEstimateOut,
    LeasedVehiclesOut,
    LessorDashboardOut,
    LessorMeOut,
    LessorOtpRequestIn,
    LessorOtpRequestOut,
    LessorOtpVerifyIn,
    LessorSessionOut,
)
from app.domains.leasing_portal.service import (
    buyback_for_vehicle,
    dashboard,
    get_lessor_me,
    list_leased_vehicles,
    request_lessor_otp,
    seed_demo_leases,
    verify_lessor_otp,
)


router = APIRouter(prefix="/lessor")


@router.post("/auth/otp/request", response_model=LessorOtpRequestOut)
def lessor_otp_request(payload: LessorOtpRequestIn, db: Session = Depends(get_db)) -> LessorOtpRequestOut:
    mode = LessorOtpChallengeMode.SIGNUP if payload.mode == "signup" else LessorOtpChallengeMode.LOGIN
    ch = request_lessor_otp(
        db,
        phone=payload.phone,
        mode=mode,
        lessor_name=payload.lessor_name,
        lessor_slug=payload.lessor_slug,
    )
    dev_otp = getattr(ch, "_dev_otp", None) if settings.env == "dev" else None
    return LessorOtpRequestOut(request_id=ch.id, expires_in_seconds=settings.otp_ttl_seconds, dev_otp=dev_otp)


@router.post("/auth/otp/verify", response_model=LessorSessionOut)
def lessor_otp_verify(payload: LessorOtpVerifyIn, db: Session = Depends(get_db)) -> LessorSessionOut:
    s = verify_lessor_otp(db, request_id=payload.request_id, otp=payload.otp)
    return LessorSessionOut(**s)


@router.get("/me", response_model=LessorMeOut)
def me(principal: Principal = Depends(require_lessor), db: Session = Depends(get_db)) -> LessorMeOut:
    data = get_lessor_me(db, lessor_id=principal.lessor_id, user_id=principal.sub)  # type: ignore[arg-type]
    return LessorMeOut(**data)


@router.get("/dashboard", response_model=LessorDashboardOut)
def dashboard_route(principal: Principal = Depends(require_lessor), db: Session = Depends(get_db)) -> LessorDashboardOut:
    d = dashboard(db, lessor_id=principal.lessor_id)  # type: ignore[arg-type]
    return LessorDashboardOut(**d)


@router.get("/vehicles", response_model=LeasedVehiclesOut)
def vehicles(principal: Principal = Depends(require_lessor), db: Session = Depends(get_db)) -> LeasedVehiclesOut:
    items = list_leased_vehicles(db, lessor_id=principal.lessor_id)  # type: ignore[arg-type]
    return LeasedVehiclesOut(items=items)


@router.get("/vehicles/{vehicle_id}/buyback", response_model=BuybackEstimateOut)
def buyback(vehicle_id: str, principal: Principal = Depends(require_lessor), db: Session = Depends(get_db)) -> BuybackEstimateOut:
    b = buyback_for_vehicle(db, lessor_id=principal.lessor_id, vehicle_id=vehicle_id)  # type: ignore[arg-type]
    return BuybackEstimateOut(**b)


@router.post("/admin/seed-demo", response_model=dict)
def seed_demo(
    per_partner: int = 12,
    principal: Principal = Depends(require_lessor_roles({LessorMembershipRole.OWNER.value, LessorMembershipRole.ANALYST.value})),
    db: Session = Depends(get_db),
) -> dict:
    return seed_demo_leases(db, lessor_id=principal.lessor_id, per_partner=per_partner)  # type: ignore[arg-type]


