"""
Service to generate rider contracts via contract-service microservice.
"""
import os
import uuid
import requests
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.domains.rider.models import Rider
from app.domains.rider.service import get_rider_by_id


# Internal URL for backend-to-backend communication (Docker network)
CONTRACT_SERVICE_URL_INTERNAL = os.getenv("CONTRACT_SERVICE_URL", "http://contract-service:8000")
# External URL for browser access (host-accessible)
CONTRACT_SERVICE_URL_EXTERNAL = os.getenv("CONTRACT_SERVICE_URL_EXTERNAL", "http://localhost:8002")


def generate_rider_contract(db: Session, rider_id: str) -> Optional[str]:
    """
    Generate contract for rider via contract-service.
    Returns contract URL or None if generation fails.
    """
    try:
        rider = get_rider_by_id(db, rider_id)
        if not rider:
            print(f"[ERROR] Rider with ID {rider_id} not found for contract generation.")
            return None
        
        # Check if rider has required data
        if not rider.name or not rider.address:
            print(f"[ERROR] Rider {rider_id} missing required data: name={rider.name}, address={rider.address}")
            return None
        
        print(f"[DEBUG] Generating contract for rider {rider_id}: {rider.name}")
        
        # Calculate age from DOB (simple parsing - assumes format like "1990-01-15" or "01/15/1990")
        age = 25  # Default age if parsing fails
        if rider.dob:
            try:
                # Try to parse common date formats
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                    try:
                        dob_date = datetime.strptime(rider.dob, fmt)
                        age = (datetime.now() - dob_date).days // 365
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        
        # Extract emergency contact details (format: "Name: +91XXXXXXXXXX" or just phone)
        emergency_name = ""
        emergency_phone = rider.emergency_contact or ""
        if ":" in (rider.emergency_contact or ""):
            parts = rider.emergency_contact.split(":", 1)
            emergency_name = parts[0].strip()
            emergency_phone = parts[1].strip() if len(parts) > 1 else ""
        elif rider.emergency_contact:
            # If no colon, assume it's just the phone number
            emergency_phone = rider.emergency_contact.strip()
        
        # Format date with ordinal suffix (e.g., "27th December 2025")
        today = datetime.now()
        day = today.day
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day % 10 - 1]
        date_long = today.strftime(f"%d{suffix} %B %Y")
        
        # Determine city from address or use default
        agreement_city = "Mumbai"  # Default
        if rider.address:
            # Try to extract city from address (simple heuristic: last major word before postal code)
            address_parts = rider.address.split(",")
            if len(address_parts) >= 2:
                # Usually city is second-to-last or last before postal code
                agreement_city = address_parts[-2].strip() if len(address_parts) >= 2 else address_parts[-1].strip()
                # Clean up any postal code parts
                agreement_city = agreement_city.split("-")[0].strip()
        
        # Extract father's name if available (currently not in model, but can be added to extra_placeholders)
        rider_father_name = "N/A"  # Default, can be enhanced if father's name is stored separately
        
        # Generate a consistent filename once
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        base_filename = f"rider_agreement_{timestamp}_{unique_id}"
        
        # Prepare contract payload with all available rider details
        payload = {
            "template_name": "rider_agreement",  # Explicit template name
            "agreement_city": agreement_city,
            "agreement_date_long": date_long,
            "rider_name": rider.name or "Rider",
            "rider_age": age,
            "rider_father_name": rider_father_name,
            "rider_address": rider.address or "Not provided",
            "rider_id": rider.id,
            "weekly_rental_inr": 1500.0,  # Default, should come from operator/configuration
            "security_deposit_inr": 5000.0,  # Default
            "account_holder_name": "ELERIDE OPERATIONS PRIVATE LIMITED",
            "bank_name": "HDFC Bank",
            "account_no": "50100123456789",  # Should be from config
            "ifsc": "HDFC0000001",
            "branch": "Mumbai Main Branch",
            "family_name": emergency_name,
            "family_phone": emergency_phone,
            "friend_name": "",  # Not captured in current model
            "friend_phone": "",  # Not captured in current model
            "output_filename": base_filename,  # Add output_filename to payload
            "extra_placeholders": {
                "RIDER_PHONE": rider.phone,
                "RIDER_DOB": rider.dob or "",
                "PREFERRED_ZONES": rider.preferred_zones or "",
            }
        }
        
        print(f"[DEBUG] Contract payload prepared for rider {rider_id}, calling contract-service...")
        
        # Render and convert to PDF in one call
        pdf_response = requests.post(
            f"{CONTRACT_SERVICE_URL_INTERNAL}/render/pdf",
            json=payload,
            timeout=60,
            stream=True
        )
        
        if pdf_response.status_code == 200:
            # Extract actual filename from Content-Disposition header
            content_disposition = pdf_response.headers.get("Content-Disposition", "")
            print(f"[DEBUG] Content-Disposition header: {content_disposition}")
            
            if "filename=" in content_disposition:
                # Extract filename from header: inline; filename="rider_agreement_20251227_163452_425c77ca.pdf"
                filename = content_disposition.split("filename=")[-1].strip('"').strip("'")
                print(f"[DEBUG] Extracted filename: {filename}")
            else:
                # Fallback to our generated filename
                filename = f"{base_filename}.pdf"
                print(f"[DEBUG] Using fallback filename: {filename}")
            
            # Use external URL for browser access (not internal Docker network)
            contract_url = f"{CONTRACT_SERVICE_URL_EXTERNAL}/download/{filename}"
            print(f"[DEBUG] Generated contract URL: {contract_url}")
            return contract_url
        else:
            # Log error but don't fail the flow
            error_text = pdf_response.text[:500] if pdf_response.text else "No error text"
            print(f"[ERROR] Contract generation failed: {pdf_response.status_code} - {error_text}")
            import traceback
            traceback.print_exc()
            return None
            
    except Exception as e:
        # Log error but don't fail the flow
        print(f"[ERROR] Error generating contract: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def sign_rider_contract(db: Session, rider_id: str, signature_image: str) -> Optional[str]:
    """
    Sign the rider contract by merging signature with PDF.
    Returns signed contract URL or None if signing fails.
    """
    try:
        rider = get_rider_by_id(db, rider_id)
        if not rider or not rider.contract_url:
            print(f"Rider or contract not found for signing.")
            return None
        
        # Extract filename from contract URL
        contract_filename = rider.contract_url.split("/")[-1]
        
        # Call contract service to add signature to PDF
        sign_response = requests.post(
            f"{CONTRACT_SERVICE_URL_INTERNAL}/sign",
            json={
                "contract_filename": contract_filename,
                "signature_image": signature_image,
            },
            timeout=60,
            stream=True
        )
        
        if sign_response.status_code == 200:
            # Extract signed filename from Content-Disposition header
            content_disposition = sign_response.headers.get("Content-Disposition", "")
            if "filename=" in content_disposition:
                signed_filename = content_disposition.split("filename=")[-1].strip('"')
            else:
                # Generate signed filename
                base_name = contract_filename.replace(".pdf", "")
                signed_filename = f"{base_name}_signed.pdf"
            
            # Use external URL for browser access
            signed_contract_url = f"{CONTRACT_SERVICE_URL_EXTERNAL}/download/{signed_filename}"
            return signed_contract_url
        else:
            print(f"Contract signing failed: {sign_response.status_code} - {sign_response.text}")
            return None
            
    except Exception as e:
        print(f"Error signing contract: {str(e)}")
        return None

