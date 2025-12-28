import re
import random
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, generate_otp, hash_otp, verify_otp_hash
from app.domains.commitment_policy.models import CommitmentLockMode
from app.domains.commitment_policy.service import create_commitment
from app.domains.matchmaking.service import lane_anchor, score_vehicle
from app.domains.operator_portal.models import (
    MaintenanceRecord,
    MaintenanceStatus,
    Operator,
    OperatorInboxState,
    OperatorMembership,
    OperatorMembershipRole,
    OperatorOtpChallenge,
    OperatorOtpChallengeMode,
    OperatorRequestInbox,
    OperatorUser,
    TelematicsDevice,
    Vehicle,
    VehicleStatus,
    VehicleTelemetryEvent,
)
from app.domains.supply.models import SupplyRequest
from app.domains.rider.models import Rider
from app.utils.qr import pickup_qr_code
from app.utils.sms import msg91_channels_available, msg91_missing_fields, send_otp_best_effort


def accept_inbox_request_auto_assign_vehicle(
    db: Session,
    *,
    operator_id: str,
    supply_request_id: str,
    note: str | None = None,
) -> dict:
    """
    Accept (ONBOARDED) an incoming rider request and auto-assign a vehicle.

    "Blocked" vehicle semantics for this MVP:
    - A vehicle is considered blocked/unavailable if it is the matched vehicle of any
      supply_request for this operator whose inbox state is ONBOARDED.
    - This avoids schema changes/migrations by deriving blocking from existing tables.
    """
    now = datetime.now(timezone.utc)

    # Lock request row so two accepts don't race on the same request.
    req: SupplyRequest | None = (
        db.query(SupplyRequest)
        .filter(SupplyRequest.id == supply_request_id, SupplyRequest.operator_id == operator_id)
        .with_for_update()
        .one_or_none()
    )
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    # Current inbox state (if any). We'll update/insert to ONBOARDED.
    st: OperatorRequestInbox | None = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == operator_id, OperatorRequestInbox.supply_request_id == supply_request_id)
        .with_for_update()
        .one_or_none()
    )
    prev_state = st.state if st else None
    if st and st.state == OperatorInboxState.ONBOARDED:
        # Already accepted. Return current assignment (best-effort).
        vid = req.matched_vehicle_id
        v = db.get(Vehicle, vid) if vid else None
        return {
            "ok": True,
            "state": OperatorInboxState.ONBOARDED,
            "matched_vehicle_id": vid or "",
            "matched_vehicle_registration_number": (v.registration_number if v else ""),
            "matched_score": req.matched_score,
            "matched_reasons": (json.loads(req.matched_reasons) if req.matched_reasons else None),
        }

    # Vehicles blocked by already-accepted (ONBOARDED) requests.
    blocked_vehicle_ids = {
        r[0]
        for r in (
            db.query(SupplyRequest.matched_vehicle_id)
            .join(OperatorRequestInbox, OperatorRequestInbox.supply_request_id == SupplyRequest.id)
            .filter(
                OperatorRequestInbox.operator_id == operator_id,
                OperatorRequestInbox.state == OperatorInboxState.ONBOARDED,
                SupplyRequest.matched_vehicle_id.isnot(None),
            )
            .all()
        )
        if r[0]
    }

    chosen: Vehicle | None = None
    # Use the lane anchor to keep assignment city-consistent (Bangalore riders get Bangalore vehicles, etc.)
    lane_lat, lane_lon, _lane_source = lane_anchor(lane_id=req.lane_id, rider_lat=None, rider_lon=None)
    # ~50-60km bounding box for city-level filtering (quick SQL filter; avoids JSON meta parsing)
    lat_min = lane_lat - 0.55
    lat_max = lane_lat + 0.55
    lon_min = lane_lon - 0.70
    lon_max = lane_lon + 0.70

    # Prefer existing recommendation if it’s still available.
    if req.matched_vehicle_id and req.matched_vehicle_id not in blocked_vehicle_ids:
        preferred: Vehicle | None = (
            db.query(Vehicle)
            .filter(
                Vehicle.id == req.matched_vehicle_id,
                Vehicle.operator_id == operator_id,
                Vehicle.status == VehicleStatus.ACTIVE,
                Vehicle.last_lat.isnot(None),
                Vehicle.last_lon.isnot(None),
                Vehicle.last_lat >= lat_min,
                Vehicle.last_lat <= lat_max,
                Vehicle.last_lon >= lon_min,
                Vehicle.last_lon <= lon_max,
            )
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        chosen = preferred

    # Otherwise pick best available ACTIVE vehicle, excluding blocked ones.
    if not chosen:
        q = (
            db.query(Vehicle)
            .filter(
                Vehicle.operator_id == operator_id,
                Vehicle.status == VehicleStatus.ACTIVE,
                (~Vehicle.id.in_(blocked_vehicle_ids)) if blocked_vehicle_ids else True,  # type: ignore[arg-type]
                Vehicle.last_lat.isnot(None),
                Vehicle.last_lon.isnot(None),
                Vehicle.last_lat >= lat_min,
                Vehicle.last_lat <= lat_max,
                Vehicle.last_lon >= lon_min,
                Vehicle.last_lon <= lon_max,
            )
            .order_by(
                Vehicle.battery_pct.desc().nullslast(),
                Vehicle.last_telemetry_at.desc().nullslast(),
                Vehicle.created_at.asc(),
            )
            .with_for_update(skip_locked=True)
        )
        chosen = q.first()

    if not chosen:
        # Fallback: if there are no city-local vehicles, allow any ACTIVE vehicle so the demo doesn't hard-fail.
        q = (
            db.query(Vehicle)
            .filter(
                Vehicle.operator_id == operator_id,
                Vehicle.status == VehicleStatus.ACTIVE,
                (~Vehicle.id.in_(blocked_vehicle_ids)) if blocked_vehicle_ids else True,  # type: ignore[arg-type]
            )
            .order_by(
                Vehicle.battery_pct.desc().nullslast(),
                Vehicle.last_telemetry_at.desc().nullslast(),
                Vehicle.created_at.asc(),
            )
            .with_for_update(skip_locked=True)
        )
        chosen = q.first()

    if not chosen:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "NO_AVAILABLE_VEHICLE", "message": "No ACTIVE vehicles available to assign."},
        )

    # Explainable score (lane anchor uses deterministic fallback if no rider lat/lon are stored in MVP).
    score, _dist, reasons, _eligible = score_vehicle(
        v=chosen,
        lane_lat=lane_lat,
        lane_lon=lane_lon,
        max_km=12.0,
        min_batt=20.0,
        max_age_min=240.0,
    )

    req.matched_vehicle_id = chosen.id
    req.matched_score = float(score)
    try:
        req.matched_reasons = json.dumps(reasons)
    except Exception:
        req.matched_reasons = None

    # Update/insert inbox state row to ONBOARDED (accepted).
    auto_note = note or f"Accepted. Auto-assigned vehicle {chosen.registration_number}."
    if st:
        st.state = OperatorInboxState.ONBOARDED
        st.note = auto_note
        st.updated_at = now
    else:
        st = OperatorRequestInbox(
            operator_id=operator_id,
            supply_request_id=supply_request_id,
            state=OperatorInboxState.ONBOARDED,
            note=auto_note,
            updated_at=now,
        )
        db.add(st)

    db.commit()
    db.refresh(req)
    db.refresh(st)

    # When a rider is marked onboarded/approved, hide demand for 5 days.
    if prev_state != OperatorInboxState.ONBOARDED:
        create_commitment(
            db,
            rider_id=req.rider_id,
            operator_id=operator_id,
            lane_id=req.lane_id,
            min_days=5,
            lock_mode=CommitmentLockMode.HIDE_ALL_DEMAND,
        )

    return {
        "ok": True,
        "state": st.state,
        "matched_vehicle_id": chosen.id,
        "matched_vehicle_registration_number": chosen.registration_number,
        "matched_score": req.matched_score,
        "matched_reasons": (json.loads(req.matched_reasons) if req.matched_reasons else None),
    }


def verify_pickup_qr(
    db: Session,
    *,
    operator_id: str,
    supply_request_id: str,
    pickup_code: str,
    verified_by_user_id: str,
) -> dict:
    now = datetime.now(timezone.utc)
    code_in = pickup_code.strip().upper()

    req: SupplyRequest | None = (
        db.query(SupplyRequest)
        .filter(SupplyRequest.id == supply_request_id, SupplyRequest.operator_id == operator_id)
        .with_for_update()
        .one_or_none()
    )
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    # Must be accepted first.
    st: OperatorRequestInbox | None = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == operator_id, OperatorRequestInbox.supply_request_id == supply_request_id)
        .one_or_none()
    )
    if not st or st.state != OperatorInboxState.ONBOARDED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "NOT_APPROVED", "message": "Request is not approved yet."})

    if req.pickup_verified_at is not None:
        return {"ok": True, "pickup_verified_at": req.pickup_verified_at.isoformat()}

    # Verify code against expected signature-derived code.
    v = db.get(Vehicle, req.matched_vehicle_id) if req.matched_vehicle_id else None
    vehicle_reg = v.registration_number if v else None
    expected = pickup_qr_code(supply_request_id=req.id, operator_id=req.operator_id, vehicle_reg=vehicle_reg)
    if code_in != expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "INVALID_PICKUP_CODE", "message": "Pickup code does not match."})

    req.pickup_verified_at = now
    req.pickup_verified_by_user_id = verified_by_user_id
    st.note = "Pickup verified (QR)."
    st.updated_at = now
    
    # Generate contract when pickup is verified
    from app.domains.rider.models import Rider
    rider = db.query(Rider).filter(Rider.id == req.rider_id).one_or_none()
    if rider:
        try:
            from app.domains.rider.contract_service import generate_rider_contract
            contract_url = generate_rider_contract(db, rider.id)
            if contract_url:
                rider.contract_url = contract_url
                print(f"[SUCCESS] Contract generated successfully for rider {rider.id}: {contract_url}")
                # Commit contract URL immediately so it's available
                db.commit()
                db.refresh(rider)
            else:
                print(f"[WARNING] Contract generation returned None for rider {rider.id}")
        except Exception as e:
            # Don't fail pickup verification if contract generation fails
            print(f"[ERROR] Contract generation failed (non-blocking): {str(e)}")
            import traceback
            traceback.print_exc()
    
    db.commit()
    db.refresh(req)
    if rider:
        db.refresh(rider)
    return {"ok": True, "pickup_verified_at": req.pickup_verified_at.isoformat()}


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:48] or "tenant"


def request_operator_otp(
    db: Session,
    *,
    phone: str,
    mode: OperatorOtpChallengeMode,
    operator_name: str | None,
    operator_slug: str | None,
) -> OperatorOtpChallenge:
    if settings.env != "dev" and not settings.otp_dev_mode:
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

    if mode == OperatorOtpChallengeMode.SIGNUP:
        if not operator_name or len(operator_name.strip()) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="operator_name required for signup")
        slug = _slugify(operator_slug or operator_name)
        # avoid collisions
        exists = db.query(Operator).filter(Operator.slug == slug).one_or_none()
        if exists:
            slug = f"{slug}-{phone[-4:]}"
    else:
        slug = _slugify(operator_slug or "")
        if not slug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="operator_slug required for login")
        op = db.query(Operator).filter(Operator.slug == slug).one_or_none()
        if not op:
            # After DB resets in dev, operators may not exist yet. Allow bootstrapping by slug.
            if settings.env == "dev":
                op = Operator(name=(operator_name or slug).strip() or "Eleride Fleet", slug=slug)
                db.add(op)
                db.commit()
                db.refresh(op)
            else:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown operator")

    otp = generate_otp()
    ch = OperatorOtpChallenge(
        phone=phone,
        otp_hash=hash_otp(phone, otp),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.otp_ttl_seconds),
        verified=False,
        mode=mode,
        operator_name=operator_name.strip() if operator_name else None,
        operator_slug=slug if slug else None,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    if settings.env == "dev" or settings.otp_dev_mode:
        setattr(ch, "_dev_otp", otp)
        return ch

    ok, channel, debug = send_otp_best_effort(phone, otp)
    if not ok and settings.env != "dev" and not settings.otp_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OTP_SEND_FAILED", "message": "Could not deliver OTP via configured channels.", "debug": debug},
        )

    # Attach OTP for dev router response (not persisted).
    setattr(ch, "_dev_otp", otp)
    return ch


def _ensure_operator(db: Session, *, name: str, slug: str) -> Operator:
    op = db.query(Operator).filter(Operator.slug == slug).one_or_none()
    if op:
        return op
    op = Operator(name=name, slug=slug)
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def _ensure_operator_user(db: Session, *, phone: str) -> OperatorUser:
    u = db.query(OperatorUser).filter(OperatorUser.phone == phone).one_or_none()
    if u:
        return u
    u = OperatorUser(phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _ensure_membership(db: Session, *, operator_id: str, user_id: str, role: OperatorMembershipRole) -> OperatorMembership:
    m = (
        db.query(OperatorMembership)
        .filter(OperatorMembership.operator_id == operator_id, OperatorMembership.user_id == user_id)
        .one_or_none()
    )
    if m:
        return m
    m = OperatorMembership(operator_id=operator_id, user_id=user_id, role=role)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def verify_operator_otp(db: Session, *, request_id: str, otp: str) -> dict:
    ch = db.get(OperatorOtpChallenge, request_id)
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

    if ch.mode == OperatorOtpChallengeMode.SIGNUP:
        op_name = ch.operator_name or "Fleet Operator"
        op_slug = ch.operator_slug or _slugify(op_name)
        op = _ensure_operator(db, name=op_name, slug=op_slug)
        user = _ensure_operator_user(db, phone=ch.phone)
        membership = _ensure_membership(db, operator_id=op.slug, user_id=user.id, role=OperatorMembershipRole.OWNER)
    else:
        if not ch.operator_slug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="operator_slug required for login")
        op = db.query(Operator).filter(Operator.slug == ch.operator_slug).one_or_none()
        if not op:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown operator")
        user = db.query(OperatorUser).filter(OperatorUser.phone == ch.phone).one_or_none()
        if not user:
            # Auto-create operator user when OTP is verified (if user can verify OTP, they should be able to log in)
                user = _ensure_operator_user(db, phone=ch.phone)
        membership = (
            db.query(OperatorMembership)
            .filter(OperatorMembership.operator_id == op.slug, OperatorMembership.user_id == user.id)
            .one_or_none()
        )
        if not membership:
            # Auto-create membership when OTP is verified (if user can verify OTP, grant them access)
                membership = _ensure_membership(db, operator_id=op.slug, user_id=user.id, role=OperatorMembershipRole.OWNER)

    token = create_access_token(
        sub=user.id,
        role="operator",
        # Use operator slug as the stable tenant key (matches supply_requests.operator_id)
        extra={"operator_id": op.slug, "operator_role": membership.role.value},
    )
    return {
        "access_token": token,
        "operator_id": op.slug,
        "operator_name": op.name,
        "operator_slug": op.slug,
        "user_id": user.id,
        "user_phone": user.phone,
        "role": membership.role,
    }


def get_operator_me(db: Session, *, operator_id: str, user_id: str) -> dict:
    op = db.query(Operator).filter(Operator.slug == operator_id).one_or_none()
    if not op:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown operator")
    u = db.get(OperatorUser, user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown operator user")
    m = (
        db.query(OperatorMembership)
        .filter(OperatorMembership.operator_id == operator_id, OperatorMembership.user_id == user_id)
        .one_or_none()
    )
    if not m:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this operator")
    return {
        "operator_id": op.slug,
        "operator_name": op.name,
        "operator_slug": op.slug,
        "user_id": u.id,
        "user_phone": u.phone,
        "role": m.role,
    }


def list_inbox(db: Session, *, operator_id: str, limit: int = 50) -> list[dict]:
    reqs: list[SupplyRequest] = (
        db.query(SupplyRequest)
        .filter(SupplyRequest.operator_id == operator_id)
        .order_by(SupplyRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    rider_ids = [r.rider_id for r in reqs]
    riders: list[Rider] = []
    if rider_ids:
        riders = db.query(Rider).filter(Rider.id.in_(rider_ids)).all()
    rider_by_id = {r.id: r for r in riders}

    states = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == operator_id, OperatorRequestInbox.supply_request_id.in_([r.id for r in reqs]))
        .all()
        if reqs
        else []
    )
    state_by_req = {s.supply_request_id: s for s in states}

    out: list[dict] = []
    for r in reqs:
        rider = rider_by_id.get(r.rider_id)
        st = state_by_req.get(r.id)
        zones = [z for z in (rider.preferred_zones or "").split(",") if z] if rider else None
        out.append(
            {
                "supply_request_id": r.id,
                "lane_id": r.lane_id,
                "created_at": r.created_at.isoformat(),
                "inbox_updated_at": (st.updated_at.isoformat() if st and st.updated_at else None),
                "pickup_location": r.pickup_location,
                "matched_vehicle_id": r.matched_vehicle_id,
                "state": (st.state if st else OperatorInboxState.NEW),
                "note": (st.note if st else None),
                "rider": {
                    "rider_id": rider.id if rider else r.rider_id,
                    "phone": rider.phone if rider else "",
                    "name": rider.name if rider else None,
                    "preferred_zones": zones or None,
                    "status": rider.status.value if rider else "UNKNOWN",
                },
            }
        )
    return out


def reset_operator_inbox(db: Session, *, operator_id: str) -> dict:
    """
    Hard reset of inbox for a tenant:
    - delete operator_request_inbox state rows
    - delete supply_requests rows for this operator
    Rider profiles are preserved.
    """
    inbox_deleted = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == operator_id)
        .delete(synchronize_session=False)
    )
    supply_deleted = (
        db.query(SupplyRequest)
        .filter(SupplyRequest.operator_id == operator_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "operator_id": operator_id, "supply_requests_deleted": int(supply_deleted), "inbox_rows_deleted": int(inbox_deleted)}


def get_inbox_request_detail(db: Session, *, operator_id: str, supply_request_id: str) -> dict:
    req: SupplyRequest | None = (
        db.query(SupplyRequest)
        .filter(SupplyRequest.id == supply_request_id, SupplyRequest.operator_id == operator_id)
        .one_or_none()
    )
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    rider: Rider | None = db.query(Rider).filter(Rider.id == req.rider_id).one_or_none()
    zones = [z for z in ((rider.preferred_zones or "").split(",") if rider else []) if z] if rider else None

    st = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == operator_id, OperatorRequestInbox.supply_request_id == req.id)
        .one_or_none()
    )

    return {
        "supply_request_id": req.id,
        "lane_id": req.lane_id,
        "created_at": req.created_at.isoformat(),
        "inbox_updated_at": (st.updated_at.isoformat() if st and st.updated_at else None),
        "pickup_location": req.pickup_location,
        "time_window": req.time_window,
        "requirements": req.requirements,
        "matched_vehicle_id": req.matched_vehicle_id,
        "state": (st.state if st else OperatorInboxState.NEW),
        "note": (st.note if st else None),
        "rider": {
            "rider_id": rider.id if rider else req.rider_id,
            "phone": rider.phone if rider else "",
            "name": rider.name if rider else None,
            "dob": rider.dob if rider else None,
            "address": rider.address if rider else None,
            "emergency_contact": rider.emergency_contact if rider else None,
            "preferred_zones": zones or None,
            "status": rider.status.value if rider else "UNKNOWN",
            "contract_url": rider.contract_url if rider else None,
            "signed_contract_url": rider.signed_contract_url if rider else None,
            "signed_at": rider.signed_at.isoformat() if rider and rider.signed_at else None,
        },
    }


def upsert_inbox_state(
    db: Session,
    *,
    operator_id: str,
    supply_request_id: str,
    state: OperatorInboxState,
    note: str | None,
) -> OperatorRequestInbox:
    existing = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == operator_id, OperatorRequestInbox.supply_request_id == supply_request_id)
        .one_or_none()
    )
    if existing:
        prev = existing.state
        existing.state = state
        existing.note = note
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)

        # When a rider is marked onboarded/approved, hide demand for 5 days.
        if prev != state and state == OperatorInboxState.ONBOARDED:
            req = (
                db.query(SupplyRequest)
                .filter(SupplyRequest.id == supply_request_id, SupplyRequest.operator_id == operator_id)
                .one_or_none()
            )
            if req:
                create_commitment(
                    db,
                    rider_id=req.rider_id,
                    operator_id=req.operator_id,
                    lane_id=req.lane_id,
                    min_days=5,
                    lock_mode=CommitmentLockMode.HIDE_ALL_DEMAND,
                )
        return existing
    row = OperatorRequestInbox(
        operator_id=operator_id,
        supply_request_id=supply_request_id,
        state=state,
        note=note,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # When a rider is marked onboarded/approved, hide demand for 5 days.
    if state == OperatorInboxState.ONBOARDED:
        req = (
            db.query(SupplyRequest)
            .filter(SupplyRequest.id == supply_request_id, SupplyRequest.operator_id == operator_id)
            .one_or_none()
        )
        if req:
            create_commitment(
                db,
                rider_id=req.rider_id,
                operator_id=req.operator_id,
                lane_id=req.lane_id,
                min_days=5,
                lock_mode=CommitmentLockMode.HIDE_ALL_DEMAND,
            )
    return row


def _extract_vin_from_meta(meta: str | None) -> str | None:
    """Extract VIN from meta JSON string."""
    if not meta:
        return None
    try:
        meta_dict = json.loads(meta) if isinstance(meta, str) else meta
        return meta_dict.get("vin") or meta_dict.get("vehicle_identification_number")
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def create_vehicle(db: Session, *, operator_id: str, registration_number: str, vin: str | None = None, model: str | None = None, meta: str | None = None) -> Vehicle:
    reg = registration_number.strip().upper()
    exists = db.query(Vehicle).filter(Vehicle.operator_id == operator_id, Vehicle.registration_number == reg).one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vehicle already exists for this operator")
    
    # Merge VIN into meta JSON if provided
    meta_dict = {}
    if meta:
        try:
            meta_dict = json.loads(meta) if isinstance(meta, str) else meta
        except (json.JSONDecodeError, TypeError):
            meta_dict = {}
    if vin:
        meta_dict["vin"] = vin.strip()
    meta_final = json.dumps(meta_dict) if meta_dict else None
    
    v = Vehicle(operator_id=operator_id, registration_number=reg, model=model, meta=meta_final)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def list_vehicles(db: Session, *, operator_id: str, limit: int = 200) -> list[Vehicle]:
    return (
        db.query(Vehicle)
        .filter(Vehicle.operator_id == operator_id)
        .order_by(Vehicle.created_at.desc())
        .limit(limit)
        .all()
    )


def get_vehicle(db: Session, *, operator_id: str, vehicle_id: str) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")
    return v


def bind_device(db: Session, *, operator_id: str, vehicle_id: str, device_id: str, provider: str | None) -> TelematicsDevice:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")
    did = device_id.strip()
    existing = db.query(TelematicsDevice).filter(TelematicsDevice.device_id == did).one_or_none()
    if existing and existing.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already bound to another operator")
    if existing:
        existing.vehicle_id = vehicle_id
        existing.provider = provider
        db.commit()
        db.refresh(existing)
        return existing
    d = TelematicsDevice(operator_id=operator_id, device_id=did, vehicle_id=vehicle_id, provider=provider)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def ingest_telemetry(db: Session, *, operator_id: str, vehicle_id: str, payload: dict) -> VehicleTelemetryEvent:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")
    ev = VehicleTelemetryEvent(
        operator_id=operator_id,
        vehicle_id=vehicle_id,
        device_id=payload.get("device_id"),
        lat=payload.get("lat"),
        lon=payload.get("lon"),
        speed_kph=payload.get("speed_kph"),
        odometer_km=payload.get("odometer_km"),
        battery_pct=payload.get("battery_pct"),
        ts=datetime.now(timezone.utc),
    )
    db.add(ev)

    # update vehicle snapshot
    if payload.get("lat") is not None:
        v.last_lat = float(payload["lat"])
    if payload.get("lon") is not None:
        v.last_lon = float(payload["lon"])
    v.last_telemetry_at = datetime.now(timezone.utc)
    if payload.get("odometer_km") is not None:
        v.odometer_km = float(payload["odometer_km"])
    if payload.get("battery_pct") is not None:
        v.battery_pct = float(payload["battery_pct"])

    db.commit()
    db.refresh(ev)
    return ev


def create_maintenance(
    db: Session,
    *,
    operator_id: str,
    vehicle_id: str,
    category: str,
    description: str,
    cost_inr: float | None,
    expected_takt_hours: float | None = 24.0,
) -> MaintenanceRecord:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")
    now = datetime.now(timezone.utc)
    takt = float(expected_takt_hours) if expected_takt_hours is not None else 24.0
    takt = max(1.0, min(24.0 * 30.0, takt))

    # loop: ticket created -> vehicle goes under maintenance immediately
    v.status = VehicleStatus.IN_MAINTENANCE

    rec = MaintenanceRecord(
        operator_id=operator_id,
        vehicle_id=vehicle_id,
        category=category,
        description=description,
        cost_inr=cost_inr,
        expected_takt_hours=takt,
        expected_ready_at=now + timedelta(hours=takt),
        created_at=now,
        updated_at=now,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def close_maintenance_ticket(db: Session, *, operator_id: str, vehicle_id: str, record_id: str) -> MaintenanceRecord:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")

    rec = db.get(MaintenanceRecord, record_id)
    if not rec or rec.operator_id != operator_id or rec.vehicle_id != vehicle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown maintenance record")

    if rec.status == MaintenanceStatus.CLOSED:
        return rec

    # IMPORTANT: close the whole maintenance "episode" for this vehicle.
    # In practice, we treat a vehicle as either under maintenance (OPEN) or not.
    # If multiple OPEN records exist (e.g. demo seeding), closing one should close all OPEN tickets for that vehicle,
    # so counts match between portals and the vehicle can reliably transition back to ACTIVE.
    now = datetime.now(timezone.utc)
    open_rows: list[MaintenanceRecord] = (
        db.query(MaintenanceRecord)
        .filter(
            MaintenanceRecord.operator_id == operator_id,
            MaintenanceRecord.vehicle_id == vehicle_id,
            MaintenanceRecord.status == MaintenanceStatus.OPEN,
        )
        .all()
    )
    for r in open_rows:
        r.status = MaintenanceStatus.CLOSED
        r.completed_at = now
        r.updated_at = now
    db.commit()
    db.refresh(rec)

    # loop: if no open tickets remain, vehicle becomes ACTIVE again
    open_count = (
        db.query(MaintenanceRecord)
        .filter(
            MaintenanceRecord.operator_id == operator_id,
            MaintenanceRecord.vehicle_id == vehicle_id,
            MaintenanceRecord.status == MaintenanceStatus.OPEN,
        )
        .count()
    )
    if open_count == 0:
        v.status = VehicleStatus.ACTIVE
        db.commit()

    return rec


def list_maintenance(db: Session, *, operator_id: str, vehicle_id: str, limit: int = 100) -> list[MaintenanceRecord]:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")
    return (
        db.query(MaintenanceRecord)
        .filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.vehicle_id == vehicle_id)
        .order_by(MaintenanceRecord.created_at.desc())
        .limit(limit)
        .all()
    )


def list_open_maintenance(db: Session, *, operator_id: str, limit: int = 200) -> dict:
    """
    Technician view: OPEN tickets across fleet with vehicle snapshot + last known location.
    IMPORTANT: return `total_open` as the source-of-truth count (matches dashboard_summary.open_maintenance_count),
    while `items` may be limited for UI performance.
    """
    _reconcile_vehicle_status_from_open_maintenance(db, operator_id=operator_id)

    # Count distinct vehicles, not tickets (one vehicle should map to one active maintenance workflow).
    total_open = (
        db.query(func.count(func.distinct(MaintenanceRecord.vehicle_id)))
        .filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.status == MaintenanceStatus.OPEN)
        .scalar()
        or 0
    )

    rows = (
        db.query(MaintenanceRecord, Vehicle)
        .join(Vehicle, Vehicle.id == MaintenanceRecord.vehicle_id)
        .filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.status == MaintenanceStatus.OPEN)
        .order_by(MaintenanceRecord.created_at.desc())
        # If there are multiple tickets per vehicle, pull more rows and de-dupe per vehicle below.
        .limit(limit * 20)
        .all()
    )
    items: list[dict] = []
    seen_vehicles: set[str] = set()
    for rec, v in rows:
        if v.id in seen_vehicles:
            continue
        seen_vehicles.add(v.id)
        items.append(
            {
                "record_id": rec.id,
                "vehicle_id": v.id,
                "registration_number": v.registration_number,
                "vehicle_status": v.status.value if hasattr(v.status, "value") else v.status,
                "model": v.model,
                "category": rec.category,
                "description": rec.description,
                "status": rec.status.value if hasattr(rec.status, "value") else rec.status,
                "created_at": rec.created_at.isoformat(),
                "updated_at": rec.updated_at.isoformat() if getattr(rec, "updated_at", None) else None,
                "expected_ready_at": rec.expected_ready_at.isoformat() if rec.expected_ready_at else None,
                "expected_takt_hours": rec.expected_takt_hours,
                "assigned_to_user_id": getattr(rec, "assigned_to_user_id", None),
                "last_lat": v.last_lat,
                "last_lon": v.last_lon,
                "last_telemetry_at": v.last_telemetry_at.isoformat() if v.last_telemetry_at else None,
                "odometer_km": v.odometer_km,
                "battery_pct": v.battery_pct,
            }
        )
        if len(items) >= limit:
            break
    return {"total_open": int(total_open), "items": items}


def _reconcile_vehicle_status_from_open_maintenance(db: Session, *, operator_id: str) -> None:
    """
    Ensure `Vehicle.status` reflects maintenance truth:
    - If a vehicle has >=1 OPEN maintenance ticket -> IN_MAINTENANCE
    - If a vehicle is IN_MAINTENANCE but has 0 OPEN tickets -> ACTIVE

    This fixes older/demo seeded data where OPEN tickets were created without updating vehicle status,
    which otherwise causes portal KPIs to disagree.
    """
    open_vehicle_ids = [
        r[0]
        for r in db.query(MaintenanceRecord.vehicle_id)
        .filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.status == MaintenanceStatus.OPEN)
        .distinct()
        .all()
    ]

    # Vehicles with open tickets -> IN_MAINTENANCE
    if open_vehicle_ids:
        db.query(Vehicle).filter(Vehicle.operator_id == operator_id, Vehicle.id.in_(open_vehicle_ids)).update(
            {"status": VehicleStatus.IN_MAINTENANCE}, synchronize_session=False
        )

    # Vehicles marked IN_MAINTENANCE but no open tickets -> ACTIVE
    q = db.query(Vehicle).filter(Vehicle.operator_id == operator_id, Vehicle.status == VehicleStatus.IN_MAINTENANCE)
    if open_vehicle_ids:
        q = q.filter(~Vehicle.id.in_(open_vehicle_ids))
    q.update({"status": VehicleStatus.ACTIVE}, synchronize_session=False)

    db.commit()


def update_maintenance_takt_time(
    db: Session,
    *,
    operator_id: str,
    vehicle_id: str,
    record_id: str,
    expected_takt_hours: float,
) -> MaintenanceRecord:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")

    rec = db.get(MaintenanceRecord, record_id)
    if not rec or rec.operator_id != operator_id or rec.vehicle_id != vehicle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown maintenance record")

    if rec.status != MaintenanceStatus.OPEN:
        return rec

    takt = float(expected_takt_hours)
    takt = max(1.0, min(24.0 * 30.0, takt))
    rec.expected_takt_hours = takt
    rec.expected_ready_at = datetime.now(timezone.utc) + timedelta(hours=takt)
    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return rec


def assign_maintenance_ticket(
    db: Session,
    *,
    operator_id: str,
    vehicle_id: str,
    record_id: str,
    assigned_to_user_id: str | None,
) -> MaintenanceRecord:
    v = db.get(Vehicle, vehicle_id)
    if not v or v.operator_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown vehicle")

    rec = db.get(MaintenanceRecord, record_id)
    if not rec or rec.operator_id != operator_id or rec.vehicle_id != vehicle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown maintenance record")

    if rec.status != MaintenanceStatus.OPEN:
        return rec

    rec.assigned_to_user_id = assigned_to_user_id
    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return rec


def _arena_centers(city: str | None = None) -> list[tuple[str, float, float]]:
    """
    Demo arena centers used for seeding vehicles + clustering summary.
    If city is None/empty/"ALL", return combined list.
    """
    c = (city or "").strip().upper()
    pune = [
        ("Pune • Wakad", 18.5975, 73.7700),
        ("Pune • Hinjewadi", 18.5960, 73.7400),
        ("Pune • Chinchwad", 18.6290, 73.8000),
        ("Pune • Kharadi", 18.5518, 73.9467),
        ("Pune • Hadapsar", 18.5089, 73.9260),
        ("Pune • Koregaon Park", 18.5362, 73.8940),
        ("Pune • Baner", 18.5590, 73.7868),
    ]
    blr = [
        ("Bangalore • Indiranagar", 12.9719, 77.6412),
        ("Bangalore • Koramangala", 12.9352, 77.6245),
        ("Bangalore • HSR Layout", 12.9116, 77.6387),
        ("Bangalore • Whitefield", 12.9698, 77.7500),
        ("Bangalore • Marathahalli", 12.9569, 77.7011),
        ("Bangalore • Hebbal", 13.0358, 77.5970),
        ("Bangalore • Electronic City", 12.8440, 77.6630),
    ]
    if c in {"BLR", "BENGALURU", "BANGALORE"}:
        return blr
    if c in {"PUNE", "PNQ"}:
        return pune
    # default: combined (also used by summary to support mixed-city fleets)
    return pune + blr


def _pick_arena_for_point(lat: float, lon: float) -> str:
    best = None
    for name, a_lat, a_lon in _arena_centers("ALL"):
        d = (lat - a_lat) ** 2 + (lon - a_lon) ** 2
        if best is None or d < best[0]:
            best = (d, name)
    return best[1] if best else "Unknown"


def dashboard_summary(db: Session, *, operator_id: str) -> dict:
    _reconcile_vehicle_status_from_open_maintenance(db, operator_id=operator_id)
    vs: list[Vehicle] = db.query(Vehicle).filter(Vehicle.operator_id == operator_id).all()
    vehicles_total = len(vs)
    vehicles_active = sum(1 for v in vs if v.status == VehicleStatus.ACTIVE)
    vehicles_in_maintenance = sum(1 for v in vs if v.status == VehicleStatus.IN_MAINTENANCE)
    vehicles_inactive = sum(1 for v in vs if v.status == VehicleStatus.INACTIVE)

    batteries = [float(v.battery_pct) for v in vs if v.battery_pct is not None]
    avg_battery = round(sum(batteries) / len(batteries), 1) if batteries else None
    low_battery_count = sum(1 for v in vs if (v.battery_pct is not None and float(v.battery_pct) < 20.0))

    # Count vehicles with at least one OPEN ticket (not total ticket rows).
    open_maintenance_count = (
        db.query(func.count(func.distinct(MaintenanceRecord.vehicle_id)))
        .filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.status == MaintenanceStatus.OPEN)
        .scalar()
        or 0
    )

    open_maintenance_ticket_count = (
        db.query(func.count(MaintenanceRecord.id))
        .filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.status == MaintenanceStatus.OPEN)
        .scalar()
        or 0
    )
    open_maintenance_assigned_ticket_count = (
        db.query(func.count(MaintenanceRecord.id))
        .filter(
            MaintenanceRecord.operator_id == operator_id,
            MaintenanceRecord.status == MaintenanceStatus.OPEN,
            MaintenanceRecord.assigned_to_user_id.isnot(None),
        )
        .scalar()
        or 0
    )
    open_maintenance_unassigned_ticket_count = int(open_maintenance_ticket_count) - int(open_maintenance_assigned_ticket_count)
    open_maintenance_overdue_count = (
        db.query(func.count(MaintenanceRecord.id))
        .filter(
            MaintenanceRecord.operator_id == operator_id,
            MaintenanceRecord.status == MaintenanceStatus.OPEN,
            MaintenanceRecord.expected_ready_at.isnot(None),
            MaintenanceRecord.expected_ready_at < datetime.now(timezone.utc),
        )
        .scalar()
        or 0
    )

    # Inbox counts: treat missing state as NEW
    reqs: list[SupplyRequest] = db.query(SupplyRequest).filter(SupplyRequest.operator_id == operator_id).all()
    state_rows: list[OperatorRequestInbox] = (
        db.query(OperatorRequestInbox)
        .filter(OperatorRequestInbox.operator_id == operator_id, OperatorRequestInbox.supply_request_id.in_([r.id for r in reqs]))
        .all()
        if reqs
        else []
    )
    state_by_req = {s.supply_request_id: s.state for s in state_rows}
    inbox_new = inbox_contacted = inbox_onboarded = inbox_rejected = 0
    for r in reqs:
        st = state_by_req.get(r.id, OperatorInboxState.NEW)
        if st == OperatorInboxState.NEW:
            inbox_new += 1
        elif st == OperatorInboxState.CONTACTED:
            inbox_contacted += 1
        elif st == OperatorInboxState.ONBOARDED:
            inbox_onboarded += 1
        elif st == OperatorInboxState.REJECTED:
            inbox_rejected += 1

    # Arena distribution based on last known location (fallback to Pune center if missing).
    # Uses combined arena list so fleets can be demo-seeded in multiple cities.
    arena_buckets: dict[str, dict] = {}
    for v in vs:
        lat = float(v.last_lat) if v.last_lat is not None else 18.5204
        lon = float(v.last_lon) if v.last_lon is not None else 73.8567
        a = _pick_arena_for_point(lat, lon)
        b = arena_buckets.setdefault(a, {"total": 0, "active": 0, "maint": 0, "bats": []})
        b["total"] += 1
        if v.status == VehicleStatus.ACTIVE:
            b["active"] += 1
        if v.status == VehicleStatus.IN_MAINTENANCE:
            b["maint"] += 1
        if v.battery_pct is not None:
            b["bats"].append(float(v.battery_pct))

    arenas = []
    for name, b in sorted(arena_buckets.items(), key=lambda kv: (-kv[1]["total"], kv[0])):
        bats = b["bats"]
        arenas.append(
            {
                "name": name,
                "vehicles_total": b["total"],
                "vehicles_active": b["active"],
                "vehicles_in_maintenance": b["maint"],
                "avg_battery_pct": round(sum(bats) / len(bats), 1) if bats else None,
            }
        )

    return {
        "vehicles_total": vehicles_total,
        "vehicles_active": vehicles_active,
        "vehicles_in_maintenance": vehicles_in_maintenance,
        "vehicles_inactive": vehicles_inactive,
        "low_battery_count": low_battery_count,
        "avg_battery_pct": avg_battery,
        "open_maintenance_count": int(open_maintenance_count),
        "open_maintenance_ticket_count": int(open_maintenance_ticket_count),
        "open_maintenance_assigned_ticket_count": int(open_maintenance_assigned_ticket_count),
        "open_maintenance_unassigned_ticket_count": int(open_maintenance_unassigned_ticket_count),
        "open_maintenance_overdue_count": int(open_maintenance_overdue_count),
        "inbox_new": inbox_new,
        "inbox_contacted": inbox_contacted,
        "inbox_onboarded": inbox_onboarded,
        "inbox_rejected": inbox_rejected,
        "arenas": arenas,
    }


def seed_demo_fleet(db: Session, *, operator_id: str, vehicles: int = 25, city: str = "PUNE") -> dict:
    # Create a realistic set of vehicles with varying status, locations, and maintenance.
    created = 0
    existing_regs = set(
        r[0] for r in db.query(Vehicle.registration_number).filter(Vehicle.operator_id == operator_id).all()
    )
    centers = _arena_centers(city)
    now = datetime.now(timezone.utc)
    reg_prefix = "MH12EL" if (city or "").strip().upper() in {"PUNE", "PNQ"} else "KA01EL"

    for i in range(vehicles):
        reg = f"{reg_prefix}{random.randint(1000, 9999)}"
        if reg in existing_regs:
            continue
        existing_regs.add(reg)

        status_roll = random.random()
        if status_roll < 0.78:
            v_status = VehicleStatus.ACTIVE
        elif status_roll < 0.92:
            v_status = VehicleStatus.IN_MAINTENANCE
        else:
            v_status = VehicleStatus.INACTIVE

        arena, a_lat, a_lon = random.choice(centers)
        lat = a_lat + random.uniform(-0.01, 0.01)
        lon = a_lon + random.uniform(-0.01, 0.01)
        battery = max(8.0, min(98.0, random.gauss(62.0, 18.0)))
        odo = max(120.0, random.gauss(4200.0, 1800.0))

        v = Vehicle(
            operator_id=operator_id,
            registration_number=reg,
            status=v_status,
            model=random.choice(["EV Scooter", "EV Bike", "EV Cargo"]),
            meta=f'{{"arena":"{arena}","city":"{(city or "").strip().upper()}","variant":"{random.choice(["S1","S2","C1"])}"}}',
            last_lat=lat,
            last_lon=lon,
            last_telemetry_at=now - timedelta(minutes=random.randint(1, 180)),
            odometer_km=round(odo, 1),
            battery_pct=round(battery, 1),
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        # Add a few telemetry points
        for _ in range(random.randint(1, 3)):
            ev = VehicleTelemetryEvent(
                operator_id=operator_id,
                vehicle_id=v.id,
                device_id=None,
                ts=now - timedelta(minutes=random.randint(1, 240)),
                lat=v.last_lat + random.uniform(-0.002, 0.002) if v.last_lat is not None else None,
                lon=v.last_lon + random.uniform(-0.002, 0.002) if v.last_lon is not None else None,
                speed_kph=round(max(0.0, random.gauss(24.0, 8.0)), 1),
                odometer_km=v.odometer_km,
                battery_pct=v.battery_pct,
            )
            db.add(ev)

        # Maintenance records realism
        if v_status == VehicleStatus.IN_MAINTENANCE or random.random() < 0.18:
            rec = MaintenanceRecord(
                operator_id=operator_id,
                vehicle_id=v.id,
                status=MaintenanceStatus.OPEN,
                category=random.choice(["BRAKES", "TIRES", "BATTERY", "SERVICE"]),
                description=random.choice(
                    [
                        "Scheduled service check",
                        "Brake pads replacement",
                        "Battery health inspection",
                        "Tire puncture / replacement",
                    ]
                ),
                cost_inr=round(max(0.0, random.gauss(850.0, 600.0)), 0),
                created_at=now - timedelta(days=random.randint(0, 14)),
            )
            db.add(rec)
            # Keep vehicle status consistent with open ticket (even if seeded status was ACTIVE/INACTIVE).
            v.status = VehicleStatus.IN_MAINTENANCE

        db.commit()
        created += 1

    return {"ok": True, "vehicles_created": created}


def reset_and_seed_demo_fleet(
    db: Session,
    *,
    operator_id: str,
    vehicles: int = 30,
    maintenance_ratio: float = 0.18,
    inactive_ratio: float = 0.08,
    city: str = "PUNE",
) -> dict:
    """
    Hard reset demo fleet data (vehicles/devices/telemetry/maintenance) for an operator and reseed.
    Clean distribution goals:
    - No duplicate OPEN tickets per vehicle (max 1 OPEN ticket)
    - Vehicle.status aligns with OPEN ticket existence
    - Reasonable mix: mostly ACTIVE, some IN_MAINTENANCE, small INACTIVE slice
    """
    vehicles = int(max(1, min(250, vehicles)))
    maintenance_ratio = float(max(0.0, min(0.6, maintenance_ratio)))
    inactive_ratio = float(max(0.0, min(0.4, inactive_ratio)))
    if maintenance_ratio + inactive_ratio > 0.9:
        maintenance_ratio = 0.6
        inactive_ratio = 0.2

    # Purge related data (operator scoped)
    vs: list[Vehicle] = db.query(Vehicle).filter(Vehicle.operator_id == operator_id).all()
    v_ids = [v.id for v in vs]
    if v_ids:
        db.query(MaintenanceRecord).filter(MaintenanceRecord.operator_id == operator_id, MaintenanceRecord.vehicle_id.in_(v_ids)).delete(
            synchronize_session=False
        )
        db.query(VehicleTelemetryEvent).filter(
            VehicleTelemetryEvent.operator_id == operator_id, VehicleTelemetryEvent.vehicle_id.in_(v_ids)
        ).delete(synchronize_session=False)
        db.query(TelematicsDevice).filter(TelematicsDevice.operator_id == operator_id, TelematicsDevice.vehicle_id.in_(v_ids)).delete(
            synchronize_session=False
        )
        db.query(Vehicle).filter(Vehicle.operator_id == operator_id).delete(synchronize_session=False)
    db.commit()

    # Reseed
    centers = _arena_centers(city)
    now = datetime.now(timezone.utc)
    created = 0
    reg_prefix = "MH12EL" if (city or "").strip().upper() in {"PUNE", "PNQ"} else "KA01EL"

    n_inactive = int(round(vehicles * inactive_ratio))
    n_maint = int(round(vehicles * maintenance_ratio))
    n_active = max(0, vehicles - n_inactive - n_maint)

    statuses: list[VehicleStatus] = (
        [VehicleStatus.ACTIVE] * n_active + [VehicleStatus.IN_MAINTENANCE] * n_maint + [VehicleStatus.INACTIVE] * n_inactive
    )
    random.shuffle(statuses)

    for i in range(vehicles):
        reg = f"{reg_prefix}{random.randint(1000, 9999)}"
        arena, a_lat, a_lon = random.choice(centers)
        lat = a_lat + random.uniform(-0.01, 0.01)
        lon = a_lon + random.uniform(-0.01, 0.01)
        battery = max(8.0, min(98.0, random.gauss(62.0, 18.0)))
        odo = max(120.0, random.gauss(4200.0, 1800.0))
        v_status = statuses[i] if i < len(statuses) else VehicleStatus.ACTIVE

        v = Vehicle(
            operator_id=operator_id,
            registration_number=reg,
            status=v_status,
            model=random.choice(["EV Scooter", "EV Bike", "EV Cargo"]),
            meta=f'{{"arena":"{arena}","city":"{(city or "").strip().upper()}","variant":"{random.choice(["S1","S2","C1"])}"}}',
            last_lat=lat,
            last_lon=lon,
            last_telemetry_at=now - timedelta(minutes=random.randint(1, 180)),
            odometer_km=round(odo, 1),
            battery_pct=round(battery, 1),
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        # 1-3 telemetry points
        for _ in range(random.randint(1, 3)):
            ev = VehicleTelemetryEvent(
                operator_id=operator_id,
                vehicle_id=v.id,
                device_id=None,
                ts=now - timedelta(minutes=random.randint(1, 240)),
                lat=v.last_lat + random.uniform(-0.002, 0.002) if v.last_lat is not None else None,
                lon=v.last_lon + random.uniform(-0.002, 0.002) if v.last_lon is not None else None,
                speed_kph=round(max(0.0, random.gauss(24.0, 8.0)), 1),
                odometer_km=v.odometer_km,
                battery_pct=v.battery_pct,
            )
            db.add(ev)

        # Exactly 1 OPEN ticket if vehicle is IN_MAINTENANCE
        if v_status == VehicleStatus.IN_MAINTENANCE:
            takt = round(max(2.0, min(72.0, random.gauss(16.0, 10.0))), 0)
            created_at = now - timedelta(hours=random.randint(0, 48))
            rec = MaintenanceRecord(
                operator_id=operator_id,
                vehicle_id=v.id,
                status=MaintenanceStatus.OPEN,
                category=random.choice(["BRAKES", "TIRES", "BATTERY", "SERVICE"]),
                description=random.choice(
                    [
                        "Scheduled service check",
                        "Brake pads replacement",
                        "Battery health inspection",
                        "Tire puncture / replacement",
                    ]
                ),
                cost_inr=round(max(0.0, random.gauss(850.0, 600.0)), 0),
                created_at=created_at,
                expected_takt_hours=float(takt),
                expected_ready_at=created_at + timedelta(hours=float(takt)),
            )
            db.add(rec)

        db.commit()
        created += 1

    # Final consistency pass
    _reconcile_vehicle_status_from_open_maintenance(db, operator_id=operator_id)
    return {
        "ok": True,
        "vehicles_created": created,
        "distribution": {"active": n_active, "in_maintenance": n_maint, "inactive": n_inactive},
    }


