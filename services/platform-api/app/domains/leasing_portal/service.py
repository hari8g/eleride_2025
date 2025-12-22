import random
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, generate_otp, hash_otp, verify_otp_hash
from app.domains.leasing_portal.models import (
    Lessor,
    LessorMembership,
    LessorMembershipRole,
    LessorOtpChallenge,
    LessorOtpChallengeMode,
    LessorUser,
    VehicleLease,
    VehicleLeaseStatus,
)
from app.domains.operator_portal.models import MaintenanceRecord, MaintenanceStatus, Operator, Vehicle, VehicleStatus
from app.utils.sms import msg91_channels_available, msg91_missing_fields, send_otp_best_effort


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:48] or "tenant"


def request_lessor_otp(
    db: Session,
    *,
    phone: str,
    mode: LessorOtpChallengeMode,
    lessor_name: str | None,
    lessor_slug: str | None,
) -> LessorOtpChallenge:
    missing = msg91_missing_fields()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OTP_SMS_NOT_CONFIGURED", "missing": missing},
        )

    channels = msg91_channels_available()
    if not channels.get("whatsapp") and not channels.get("sms"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "OTP_CHANNELS_NOT_CONFIGURED",
                "message": "Configure WhatsApp Flow or SMS template for OTP delivery.",
                "channels": channels,
            },
        )

    if mode == LessorOtpChallengeMode.SIGNUP:
        if not lessor_name or len(lessor_name.strip()) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lessor_name required for signup")
        slug = _slugify(lessor_slug or lessor_name)
        exists = db.query(Lessor).filter(Lessor.slug == slug).one_or_none()
        if exists:
            slug = f"{slug}-{phone[-4:]}"
    else:
        slug = _slugify(lessor_slug or "")
        if not slug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lessor_slug required for login")
        ls = db.query(Lessor).filter(Lessor.slug == slug).one_or_none()
        if not ls:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown lessor")

    otp = generate_otp()
    ch = LessorOtpChallenge(
        phone=phone,
        otp_hash=hash_otp(phone, otp),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.otp_ttl_seconds),
        verified=False,
        mode=mode,
        lessor_name=lessor_name.strip() if lessor_name else None,
        lessor_slug=slug if slug else None,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    ok, channel, debug = send_otp_best_effort(phone, otp)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OTP_SEND_FAILED", "message": "Could not deliver OTP via configured channels.", "debug": debug},
        )

    return ch


def _ensure_lessor(db: Session, *, name: str, slug: str) -> Lessor:
    ls = db.query(Lessor).filter(Lessor.slug == slug).one_or_none()
    if ls:
        return ls
    ls = Lessor(name=name, slug=slug)
    db.add(ls)
    db.commit()
    db.refresh(ls)
    return ls


def _ensure_lessor_user(db: Session, *, phone: str) -> LessorUser:
    u = db.query(LessorUser).filter(LessorUser.phone == phone).one_or_none()
    if u:
        return u
    u = LessorUser(phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _ensure_membership(db: Session, *, lessor_id: str, user_id: str, role: LessorMembershipRole) -> LessorMembership:
    m = (
        db.query(LessorMembership)
        .filter(LessorMembership.lessor_id == lessor_id, LessorMembership.user_id == user_id)
        .one_or_none()
    )
    if m:
        return m
    m = LessorMembership(lessor_id=lessor_id, user_id=user_id, role=role)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def verify_lessor_otp(db: Session, *, request_id: str, otp: str) -> dict:
    ch = db.get(LessorOtpChallenge, request_id)
    if not ch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request_id")
    if ch.verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP already used")
    if datetime.now(timezone.utc) > ch.expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")
    if not verify_otp_hash(ch.phone, otp, ch.otp_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    ch.verified = True
    db.commit()

    if ch.mode == LessorOtpChallengeMode.SIGNUP:
        name = ch.lessor_name or "Leasing Co"
        slug = ch.lessor_slug or _slugify(name)
        ls = _ensure_lessor(db, name=name, slug=slug)
        user = _ensure_lessor_user(db, phone=ch.phone)
        mem = _ensure_membership(db, lessor_id=ls.slug, user_id=user.id, role=LessorMembershipRole.OWNER)
    else:
        if not ch.lessor_slug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lessor_slug required for login")
        ls = db.query(Lessor).filter(Lessor.slug == ch.lessor_slug).one_or_none()
        if not ls:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown lessor")
        user = db.query(LessorUser).filter(LessorUser.phone == ch.phone).one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No lessor user for this phone")
        mem = (
            db.query(LessorMembership)
            .filter(LessorMembership.lessor_id == ls.slug, LessorMembership.user_id == user.id)
            .one_or_none()
        )
        if not mem:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not a member of this lessor")

    token = create_access_token(
        sub=user.id,
        role="lessor",
        extra={"lessor_id": ls.slug, "lessor_role": mem.role.value},
    )
    return {
        "access_token": token,
        "lessor_id": ls.slug,
        "lessor_name": ls.name,
        "lessor_slug": ls.slug,
        "user_id": user.id,
        "user_phone": user.phone,
        "role": mem.role,
    }


def get_lessor_me(db: Session, *, lessor_id: str, user_id: str) -> dict:
    ls = db.query(Lessor).filter(Lessor.slug == lessor_id).one_or_none()
    if not ls:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown lessor")
    u = db.get(LessorUser, user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown lessor user")
    m = (
        db.query(LessorMembership)
        .filter(LessorMembership.lessor_id == lessor_id, LessorMembership.user_id == user_id)
        .one_or_none()
    )
    if not m:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this lessor")
    return {
        "lessor_id": ls.slug,
        "lessor_name": ls.name,
        "lessor_slug": ls.slug,
        "user_id": u.id,
        "user_phone": u.phone,
        "role": m.role,
    }


def _buyback_estimate_for_vehicle(
    *,
    v: Vehicle,
    lease: VehicleLease,
    open_maint: int,
) -> tuple[float, list[str]]:
    # Portfolio underwriting buyback (3Y horizon, capped):
    # - compute a 3-year buyback value capped at <= 30% of purchase price per vehicle
    # - apply risk discounts (maintenance, battery) and utilization proxy (projected odo)
    reasons: list[str] = []
    purchase = float(lease.purchase_price_inr or 90000.0)
    cap = 0.30 * purchase
    reasons.append(f"purchase_price≈₹{int(purchase)}")
    reasons.append(f"cap=30%→₹{int(cap)}")

    # utilization proxy: project odometer at 3 years based on current odo and elapsed time since lease start
    try:
        start = datetime.strptime(lease.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        start = datetime.now(timezone.utc) - timedelta(days=180)
    months_elapsed = max(1.0, (datetime.now(timezone.utc) - start).days / 30.0)
    odo_now = float(v.odometer_km or 0.0)
    odo_3y = odo_now * (36.0 / months_elapsed)
    reasons.append(f"projected_odo_3y≈{odo_3y:.0f}km")

    discount = 0.0
    # maintenance discount (tight but not extreme): 1% per open ticket, capped 5%
    if open_maint:
        d = min(0.05, 0.01 * float(open_maint))
        discount += d
        reasons.append(f"maintenance_discount≈{d*100:.1f}% (open={open_maint})")

    # battery discount tiers (proxy for health) — keep mild to avoid extreme swings
    batt = v.battery_pct
    if batt is not None:
        b = float(batt)
        if b < 20.0:
            discount += 0.03
            reasons.append("battery_discount=3% (battery<20%)")
        elif b < 40.0:
            discount += 0.015
            reasons.append("battery_discount=1.5% (battery<40%)")

    # high-usage discount based on projected 3-year odometer.
    # Guardrails: only apply when we have meaningful usage signal (avoid extreme penalties from tiny elapsed time).
    if months_elapsed >= 2.0 and odo_now >= 200.0 and odo_3y > 30000.0:
        # 0% at 30k, up to 10% at 130k+
        ratio = min(1.0, max(0.0, (odo_3y - 30000.0) / 100000.0))
        d = 0.10 * ratio
        discount += d
        reasons.append(f"usage_discount≈{d*100:.1f}% (high km)")

    # cap total discount so we don't over-penalize and collapse estimates
    discount = min(0.18, discount)
    if discount:
        reasons.append(f"total_discount≈{discount*100:.1f}%")

    val = max(0.0, cap * (1.0 - discount))

    # optional buyback floor (guarantee), but never above the 30% cap
    floor = float(lease.buyback_floor_inr or 0.0)
    if floor > 0.0:
        floor_capped = min(floor, cap)
        if floor_capped != floor:
            reasons.append(f"floor≈₹{int(floor)} capped_to_30%→₹{int(floor_capped)}")
        else:
            reasons.append(f"floor≈₹{int(floor)}")
        val = max(val, floor_capped)

    # hard safety: never exceed 30% cap
    val = min(val, cap)
    return round(val, 0), reasons


def list_leased_vehicles(db: Session, *, lessor_id: str) -> list[dict]:
    leases: list[VehicleLease] = db.query(VehicleLease).filter(VehicleLease.lessor_id == lessor_id).all()
    if not leases:
        return []
    veh_ids = [l.vehicle_id for l in leases]
    vs: list[Vehicle] = db.query(Vehicle).filter(Vehicle.id.in_(veh_ids)).all()
    by_id = {v.id: v for v in vs}
    out = []
    for l in leases:
        v = by_id.get(l.vehicle_id)
        if not v:
            continue
        out.append(
            {
                "vehicle_id": v.id,
                "registration_number": v.registration_number,
                "operator_id": l.operator_id,
                "status": v.status.value,
                "last_lat": v.last_lat,
                "last_lon": v.last_lon,
                "odometer_km": v.odometer_km,
                "battery_pct": v.battery_pct,
                "lease_status": l.status,
                "purchase_price_inr": l.purchase_price_inr,
                "monthly_rent_inr": l.monthly_rent_inr,
                "start_date": l.start_date,
            }
        )
    return out


def dashboard(db: Session, *, lessor_id: str) -> dict:
    leases: list[VehicleLease] = db.query(VehicleLease).filter(VehicleLease.lessor_id == lessor_id).all()
    active_leases = [l for l in leases if l.status == VehicleLeaseStatus.ACTIVE]
    vehicles_leased_total = len(leases)

    # fetch vehicles
    veh_ids = [l.vehicle_id for l in leases]
    vs: list[Vehicle] = db.query(Vehicle).filter(Vehicle.id.in_(veh_ids)).all() if veh_ids else []
    v_by_id = {v.id: v for v in vs}

    # open maintenance by vehicle (leased subset)
    open_maint_by_vehicle: dict[str, int] = {}
    if veh_ids:
        rows = (
            db.query(MaintenanceRecord.vehicle_id)
            .filter(MaintenanceRecord.vehicle_id.in_(veh_ids), MaintenanceRecord.status == MaintenanceStatus.OPEN)
            .all()
        )
        for (vid,) in rows:
            open_maint_by_vehicle[vid] = open_maint_by_vehicle.get(vid, 0) + 1

    # group by partner operator_id (slug)
    # IMPORTANT: we expose both fleet-level metrics (match operator portal) and leased/covered subset metrics.
    # Fleet-level metrics are derived directly from operator tables (Vehicle + MaintenanceRecord) and do NOT depend on leases.
    by_partner: dict[str, dict] = {}
    total_buyback = 0.0
    total_valued = 0
    for l in active_leases:
        v = v_by_id.get(l.vehicle_id)
        # Vehicle may not exist if operator fleet was reset; still count the lease in `vehicles_leased`,
        # but we can’t compute buyback or leased subset health without the vehicle snapshot.
        p = by_partner.setdefault(
            l.operator_id,
            {
                "vehicles": 0,
                "valued": 0,
                "leased_active": 0,
                "leased_open": 0,
                "leased_in_maint": 0,
                "leased_low_batt": 0,
                "buyback": 0.0,
            },
        )
        p["vehicles"] += 1
        if not v:
            continue
        p["valued"] += 1
        total_valued += 1
        if v.status == VehicleStatus.ACTIVE:
            p["leased_active"] += 1
        if v.status == VehicleStatus.IN_MAINTENANCE:
            p["leased_in_maint"] += 1
        if v.battery_pct is not None and float(v.battery_pct) < 20.0:
            p["leased_low_batt"] += 1
        open_m = open_maint_by_vehicle.get(v.id, 0)
        if open_m > 0:
            p["leased_open"] += 1
        est, _ = _buyback_estimate_for_vehicle(v=v, lease=l, open_maint=open_m)
        p["buyback"] += float(est)
        total_buyback += float(est)

    # Fleet-level metrics per operator (match operator portal)
    op_ids = sorted({l.operator_id for l in active_leases})
    fleet_active_by_op: dict[str, int] = {}
    fleet_low_batt_by_op: dict[str, int] = {}
    fleet_avg_batt_by_op: dict[str, float | None] = {}
    fleet_open_tickets_by_op: dict[str, int] = {}

    if op_ids:
        v_rows = (
            db.query(Vehicle.operator_id, Vehicle.status, Vehicle.battery_pct)
            .filter(Vehicle.operator_id.in_(op_ids))
            .all()
        )
        batt_acc: dict[str, list[float]] = {op: [] for op in op_ids}
        for op, st, batt in v_rows:
            if st == VehicleStatus.ACTIVE:
                fleet_active_by_op[op] = fleet_active_by_op.get(op, 0) + 1
            if batt is not None:
                b = float(batt)
                batt_acc[op].append(b)
                if b < 20.0:
                    fleet_low_batt_by_op[op] = fleet_low_batt_by_op.get(op, 0) + 1
        for op in op_ids:
            bats = batt_acc.get(op) or []
            fleet_avg_batt_by_op[op] = round(sum(bats) / len(bats), 1) if bats else None

        # Count distinct vehicles with OPEN tickets per operator (matches operator portal semantics)
        t_rows = (
            db.query(MaintenanceRecord.operator_id, func.count(func.distinct(MaintenanceRecord.vehicle_id)))
            .filter(MaintenanceRecord.operator_id.in_(op_ids), MaintenanceRecord.status == MaintenanceStatus.OPEN)
            .group_by(MaintenanceRecord.operator_id)
            .all()
        )
        for op, c in t_rows:
            fleet_open_tickets_by_op[op] = int(c or 0)

    partners = []
    for op_id, p in sorted(by_partner.items(), key=lambda kv: -kv[1]["vehicles"]):
        partners.append(
            {
                "operator_id": op_id,
                "vehicles_leased": p["vehicles"],
                "vehicles_valued": int(p.get("valued", 0)),
                "fleet_vehicles_active": int(fleet_active_by_op.get(op_id, 0)),
                "fleet_open_tickets": int(fleet_open_tickets_by_op.get(op_id, 0)),
                "fleet_low_battery": int(fleet_low_batt_by_op.get(op_id, 0)),
                "fleet_avg_battery_pct": fleet_avg_batt_by_op.get(op_id),
                "leased_vehicles_active": int(p.get("leased_active", 0)),
                "leased_open_tickets": int(p.get("leased_open", 0)),
                "leased_vehicles_in_maintenance": int(p.get("leased_in_maint", 0)),
                "leased_low_battery": int(p.get("leased_low_batt", 0)),
                "est_buyback_value_inr": round(p["buyback"], 0),
            }
        )

    return {
        "vehicles_leased_total": vehicles_leased_total,
        "vehicles_valued_total": total_valued,
        "active_leases": len(active_leases),
        "partners": partners,
        "est_buyback_value_total_inr": round(total_buyback, 0),
    }


def buyback_for_vehicle(db: Session, *, lessor_id: str, vehicle_id: str) -> dict:
    lease = (
        db.query(VehicleLease)
        .filter(VehicleLease.lessor_id == lessor_id, VehicleLease.vehicle_id == vehicle_id)
        .one_or_none()
    )
    if not lease:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No lease for this vehicle")
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")
    open_maint = (
        db.query(MaintenanceRecord)
        .filter(MaintenanceRecord.vehicle_id == vehicle_id, MaintenanceRecord.status == MaintenanceStatus.OPEN)
        .count()
    )
    est, reasons = _buyback_estimate_for_vehicle(v=v, lease=lease, open_maint=int(open_maint))
    return {
        "vehicle_id": v.id,
        "registration_number": v.registration_number,
        "operator_id": lease.operator_id,
        "estimated_value_inr": est,
        "floor_inr": float(lease.buyback_floor_inr) if lease.buyback_floor_inr is not None else None,
        "reasons": reasons,
    }


def seed_demo_leases(db: Session, *, lessor_id: str, per_partner: int = 12) -> dict:
    # Ensure some operators exist
    partners = [
        ("eleride-fleet", "Eleride Fleet"),
        ("fastwheels", "FastWheels Logistics"),
        ("speedy", "Speedy Fleet Services"),
    ]
    for slug, name in partners:
        if not db.query(Operator).filter(Operator.slug == slug).one_or_none():
            db.add(Operator(name=name, slug=slug))
    db.commit()

    # Create vehicles under operators (if missing) and lease them to this lessor.
    # Also: normalize telemetry snapshots so the UI doesn't look "copy/pasted" (e.g., many 60% / 1201km rows).
    created = 0
    for op_slug, _ in partners:
        existing = db.query(Vehicle).filter(Vehicle.operator_id == op_slug).count()
        target = max(existing, per_partner)
        if existing < target:
            for _i in range(target - existing):
                reg = f"MH12LZ{random.randint(1000, 9999)}"
                v = Vehicle(
                    operator_id=op_slug,
                    registration_number=reg,
                    status=random.choice([VehicleStatus.ACTIVE, VehicleStatus.ACTIVE, VehicleStatus.IN_MAINTENANCE]),
                    model=random.choice(["EV Scooter", "EV Bike", "EV Cargo"]),
                    meta=f'{{"source":"lessor_demo","partner":"{op_slug}"}}',
                    last_lat=18.52 + random.uniform(-0.08, 0.10),
                    last_lon=73.85 + random.uniform(-0.10, 0.12),
                    last_telemetry_at=datetime.now(timezone.utc) - timedelta(minutes=random.randint(10, 240)),
                    odometer_km=round(max(50.0, random.gauss(5200.0, 2300.0)), 1),
                    battery_pct=round(max(8.0, min(98.0, random.gauss(58.0, 20.0))), 1),
                )
                db.add(v)
                db.commit()
                db.refresh(v)
                created += 1

                if v.status == VehicleStatus.IN_MAINTENANCE and random.random() < 0.7:
                    db.add(
                        MaintenanceRecord(
                            operator_id=op_slug,
                            vehicle_id=v.id,
                            status=MaintenanceStatus.OPEN,
                            category=random.choice(["BATTERY", "TIRES", "SERVICE"]),
                            description=random.choice(["Scheduled service", "Battery health check", "Tire replacement"]),
                            cost_inr=round(max(0.0, random.gauss(950.0, 700.0)), 0),
                            created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 12)),
                        )
                    )
                    db.commit()

        # Lease vehicles to lessor
        vehs = db.query(Vehicle).filter(Vehicle.operator_id == op_slug).all()
        # pick a random subset to avoid always leasing the first N "old" records
        random.shuffle(vehs)
        vehs = vehs[:per_partner]
        for v in vehs:
            exists = (
                db.query(VehicleLease)
                .filter(VehicleLease.lessor_id == lessor_id, VehicleLease.vehicle_id == v.id)
                .one_or_none()
            )
            # Normalize snapshot for realism even if the lease already exists.
            # This makes clicking "Seed demo portfolio" again refresh stale-looking telemetry.
            now = datetime.now(timezone.utc)
            # If battery/odo look missing or suspiciously identical across many vehicles, add a small random jitter
            if v.battery_pct is None:
                v.battery_pct = round(max(8.0, min(98.0, random.gauss(58.0, 20.0))), 1)
            else:
                v.battery_pct = round(max(5.0, min(99.0, float(v.battery_pct) + random.uniform(-8.0, 8.0))), 1)

            if v.odometer_km is None:
                v.odometer_km = round(max(50.0, random.gauss(5200.0, 2300.0)), 1)
            else:
                v.odometer_km = round(max(0.0, float(v.odometer_km) + random.uniform(-120.0, 420.0)), 1)

            if v.last_lat is None or v.last_lon is None:
                v.last_lat = 18.52 + random.uniform(-0.08, 0.10)
                v.last_lon = 73.85 + random.uniform(-0.10, 0.12)
            else:
                v.last_lat = float(v.last_lat) + random.uniform(-0.01, 0.01)
                v.last_lon = float(v.last_lon) + random.uniform(-0.01, 0.01)
            v.last_telemetry_at = now - timedelta(minutes=random.randint(5, 220))
            db.commit()

            if exists:
                continue
            lease = VehicleLease(
                lessor_id=lessor_id,
                operator_id=op_slug,
                vehicle_id=v.id,
                status=VehicleLeaseStatus.ACTIVE,
                start_date=(datetime.now(timezone.utc) - timedelta(days=random.randint(45, 420))).strftime("%Y-%m-%d"),
                purchase_price_inr=random.choice([85000.0, 90000.0, 95000.0, 100000.0]),
                monthly_rent_inr=random.choice([3800.0, 4200.0, 4600.0, 5200.0]),
                buyback_floor_inr=random.choice([25000.0, 28000.0, 30000.0]),
            )
            db.add(lease)
            db.commit()
    return {"ok": True, "vehicles_created": created}


