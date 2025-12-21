from pydantic import BaseModel


class KYCStartIn(BaseModel):
    doc_type: str | None = None  # Aadhaar/PAN/DL etc


class KYCStatusOut(BaseModel):
    rider_id: str
    status: str


