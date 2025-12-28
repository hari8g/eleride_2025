from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_rider
from app.core.security import Principal
from app.domains.rider.schemas import RiderProfileIn, RiderProfileOut, RiderStatusOut, ContractSignIn
from app.domains.rider.service import get_rider_by_phone, get_status_payload, upsert_profile


router = APIRouter(prefix="/riders")


@router.post("/profile", response_model=RiderProfileOut)
def create_or_update_profile(
    payload: RiderProfileIn,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderProfileOut:
    rider = upsert_profile(
        db,
        phone=principal.sub,
        name=payload.name,
        dob=payload.dob,
        address=payload.address,
        emergency_contact=payload.emergency_contact,
        preferred_zones=payload.preferred_zones,
    )
    zones = [z for z in (rider.preferred_zones or "").split(",") if z]
    return RiderProfileOut(
        rider_id=rider.id,
        phone=rider.phone,
        status=rider.status,
        name=rider.name,
        dob=rider.dob,
        address=rider.address,
        emergency_contact=rider.emergency_contact,
        preferred_zones=zones or None,
    )


@router.get("/status", response_model=RiderStatusOut)
def rider_status(
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderStatusOut:
    payload = get_status_payload(db, phone=principal.sub)
    return RiderStatusOut(**payload)


@router.get("/me", response_model=RiderProfileOut)
def me(principal: Principal = Depends(require_rider), db: Session = Depends(get_db)) -> RiderProfileOut:
    rider = get_rider_by_phone(db, principal.sub)
    zones = [z for z in (rider.preferred_zones or "").split(",") if z]
    return RiderProfileOut(
        rider_id=rider.id,
        phone=rider.phone,
        status=rider.status,
        name=rider.name,
        dob=rider.dob,
        address=rider.address,
        emergency_contact=rider.emergency_contact,
        preferred_zones=zones or None,
        contract_url=rider.contract_url,
        signed_contract_url=rider.signed_contract_url,
        signed_at=rider.signed_at.isoformat() if rider.signed_at else None,
    )


@router.post("/contract/sign")
def sign_contract(
    payload: ContractSignIn,
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderProfileOut:
    """Sign the rider contract with a signature."""
    from datetime import datetime, timezone
    from app.domains.rider.contract_service import sign_rider_contract
    
    rider = get_rider_by_phone(db, principal.sub)
    
    if not rider.contract_url:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found. Contract must be generated first."
        )
    
    if rider.signed_contract_url:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract already signed."
        )
    
    # Save signature and generate signed contract
    signed_contract_url = sign_rider_contract(db, rider.id, payload.signature_image)
    
    if signed_contract_url:
        rider.signature_image = payload.signature_image
        rider.signed_contract_url = signed_contract_url
        rider.signed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(rider)
    
    zones = [z for z in (rider.preferred_zones or "").split(",") if z]
    return RiderProfileOut(
        rider_id=rider.id,
        phone=rider.phone,
        status=rider.status,
        name=rider.name,
        dob=rider.dob,
        address=rider.address,
        emergency_contact=rider.emergency_contact,
        preferred_zones=zones or None,
        contract_url=rider.contract_url,
        signed_contract_url=rider.signed_contract_url,
        signed_at=rider.signed_at.isoformat() if rider.signed_at else None,
    )


@router.get("/contract")
def get_contract(
    principal: Principal = Depends(require_rider),
    db: Session = Depends(get_db),
):
    """Get rider's contract PDF."""
    from fastapi.responses import RedirectResponse
    rider = get_rider_by_phone(db, principal.sub)
    
    if not rider.contract_url:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not yet generated. Complete KYC verification first."
        )
    
    return RedirectResponse(url=rider.contract_url)


