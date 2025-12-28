from pydantic import BaseModel, Field

from app.domains.rider.models import RiderStatus


class RiderProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    dob: str = Field(min_length=4, max_length=32)
    address: str = Field(min_length=3, max_length=512)
    emergency_contact: str = Field(min_length=6, max_length=32)
    preferred_zones: list[str] | None = None


class RiderProfileOut(BaseModel):
    rider_id: str
    phone: str
    status: RiderStatus
    name: str | None = None
    dob: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    preferred_zones: list[str] | None = None
    contract_url: str | None = None
    signed_contract_url: str | None = None
    signed_at: str | None = None


class ContractSignIn(BaseModel):
    signature_image: str = Field(..., description="Base64 encoded signature image (data URL)")


class RiderStatusOut(BaseModel):
    rider_id: str
    phone: str
    status: RiderStatus
    active_commitment: dict | None = None


