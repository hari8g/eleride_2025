"""
Maps Pydantic model fields to DOCX template placeholders.
Converts snake_case to UPPERCASE_SNAKE_CASE for placeholders.
"""
from typing import Dict, Any
from app.models import ContractRenderRequest


def model_to_placeholders(request: ContractRenderRequest) -> Dict[str, str]:
    """
    Convert ContractRenderRequest model to placeholder dictionary.
    All placeholders are in format {{UPPERCASE_SNAKE_CASE}}.
    Missing optional fields become empty strings.
    """
    placeholders = {}
    
    # Agreement Metadata
    placeholders["{{AGREEMENT_CITY}}"] = request.agreement_city
    placeholders["{{AGREEMENT_DATE_LONG}}"] = request.agreement_date_long
    
    # Rider Identity
    placeholders["{{RIDER_NAME}}"] = request.rider_name
    placeholders["{{RIDER_AGE}}"] = str(request.rider_age)
    placeholders["{{RIDER_FATHER_NAME}}"] = request.rider_father_name or ""
    placeholders["{{RIDER_ADDRESS}}"] = request.rider_address
    placeholders["{{RIDER_ID}}"] = request.rider_id or ""
    
    # Commercials
    placeholders["{{WEEKLY_RENTAL_INR}}"] = f"₹{request.weekly_rental_inr:,.2f}"
    placeholders["{{SECURITY_DEPOSIT_INR}}"] = f"₹{request.security_deposit_inr:,.2f}"
    
    # Bank Details
    placeholders["{{ACCOUNT_HOLDER_NAME}}"] = request.account_holder_name
    placeholders["{{BANK_NAME}}"] = request.bank_name
    placeholders["{{ACCOUNT_NO}}"] = request.account_no
    placeholders["{{IFSC}}"] = request.ifsc
    placeholders["{{BRANCH}}"] = request.branch
    
    # Reference Contacts
    placeholders["{{FAMILY_NAME}}"] = request.family_name or ""
    placeholders["{{FAMILY_PHONE}}"] = request.family_phone or ""
    placeholders["{{FRIEND_NAME}}"] = request.friend_name or ""
    placeholders["{{FRIEND_PHONE}}"] = request.friend_phone or ""
    
    # Extra placeholders (escape hatch)
    for key, value in request.extra_placeholders.items():
        # Convert key to placeholder format
        placeholder_key = f"{{{{{key.upper()}}}}}"
        placeholders[placeholder_key] = str(value) if value is not None else ""
    
    return placeholders

