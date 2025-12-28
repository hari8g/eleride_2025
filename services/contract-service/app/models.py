from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator


class ContractRenderRequest(BaseModel):
    """Request model for contract rendering with all required and optional fields."""
    
    # Agreement Metadata
    agreement_city: str = Field(..., description="City where agreement is signed")
    agreement_date_long: str = Field(default_factory=lambda: datetime.now().strftime("%B %d, %Y"), description="Long format date")
    
    # Rider Identity
    rider_name: str = Field(..., min_length=1, description="Full name of rider")
    rider_age: int = Field(..., ge=18, description="Age of rider (must be 18+)")
    rider_father_name: Optional[str] = Field(None, description="Father's name")
    rider_address: str = Field(..., description="Complete address")
    rider_id: Optional[str] = Field(None, description="ID number (Aadhaar/PAN)")
    
    # Commercials
    weekly_rental_inr: float = Field(..., ge=0, description="Weekly rental amount in INR")
    security_deposit_inr: float = Field(..., ge=0, description="Security deposit in INR")
    
    # Bank Details (ELERIDE)
    account_holder_name: str = Field(..., description="Account holder name")
    bank_name: str = Field(..., description="Bank name")
    account_no: str = Field(..., description="Account number")
    ifsc: str = Field(..., description="IFSC code")
    branch: str = Field(..., description="Branch name")
    
    # Reference Contacts
    family_name: Optional[str] = Field(None, description="Family member name")
    family_phone: Optional[str] = Field(None, description="Family member phone")
    friend_name: Optional[str] = Field(None, description="Friend name")
    friend_phone: Optional[str] = Field(None, description="Friend phone")
    
    # Escape hatch for extra placeholders
    extra_placeholders: Dict[str, Any] = Field(default_factory=dict, description="Additional placeholders")
    
    # Optional: specify output filename (without extension) for consistency
    output_filename: Optional[str] = Field(None, description="Optional output filename (without extension)")
    
    @field_validator("rider_age")
    @classmethod
    def validate_age(cls, v: int) -> int:
        if v < 18:
            raise ValueError("Rider must be at least 18 years old")
        return v


class ContractRenderResponse(BaseModel):
    """Response model for contract rendering."""
    success: bool
    filename: str
    message: str
    file_size_bytes: Optional[int] = None

