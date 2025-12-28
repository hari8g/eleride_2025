#!/usr/bin/env python3
"""
Import vehicles from Excel file into the fleet portal.

This script reads the Vehicle Inventory Data Excel file and creates vehicles
via the API, storing all registration details in the vehicle metadata.

Usage:
    python scripts/import_vehicles_from_excel.py --operator-slug eleride-fleet --api-url http://localhost:18080
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests


def normalize_column_name(col: str) -> str:
    """Normalize column names to handle variations."""
    col_lower = str(col).strip().lower()
    # Common variations
    col_map = {
        "vin": ["vin", "vehicle identification number"],
        "reg number": ["reg number", "registration number", "reg no", "registration no"],
        "reg date": ["reg date", "registration date"],
        "chassis number": ["chassis number", "chassis no", "chassis"],
        "mfg year": ["mfg year", "manufacturing year", "year", "manufacture year"],
        "rc owner name": ["rc owner name", "owner name", "registered owner"],
        "brand": ["brand", "make"],
        "model": ["model"],
        "variant": ["variant", "trim"],
        "color": ["color", "colour"],
    }
    for key, aliases in col_map.items():
        if any(alias in col_lower for alias in aliases):
            return key
    return col_lower.replace(" ", "_").replace("-", "_")


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find a column by trying multiple name variations."""
    normalized_cols = {normalize_column_name(c): c for c in df.columns}
    for cand in candidates:
        norm = normalize_column_name(cand)
        if norm in normalized_cols:
            return normalized_cols[norm]
    return None


def parse_excel(file_path: str) -> list[dict]:
    """Parse Excel file and return list of vehicle records."""
    df = pd.read_excel(file_path)
    
    # Normalize column names
    df.columns = [normalize_column_name(c) for c in df.columns]
    
    vehicles = []
    for _, row in df.iterrows():
        # Extract fields with fallbacks
        vin = str(row.get("vin", "")).strip() if pd.notna(row.get("vin")) else ""
        reg_number = str(row.get("reg_number", "")).strip() if pd.notna(row.get("reg_number")) else ""
        brand = str(row.get("brand", "")).strip() if pd.notna(row.get("brand")) else ""
        model = str(row.get("model", "")).strip() if pd.notna(row.get("model")) else ""
        variant = str(row.get("variant", "")).strip() if pd.notna(row.get("variant")) else ""
        color = str(row.get("color", "")).strip() if pd.notna(row.get("color")) else ""
        reg_date = str(row.get("reg_date", "")).strip() if pd.notna(row.get("reg_date")) else ""
        chassis_number = str(row.get("chassis_number", "")).strip() if pd.notna(row.get("chassis_number")) else ""
        mfg_year = str(row.get("mfg_year", "")).strip() if pd.notna(row.get("mfg_year")) else ""
        rc_owner_name = str(row.get("rc_owner_name", "")).strip() if pd.notna(row.get("rc_owner_name")) else ""
        
        # Skip if essential fields are missing
        if not vin and not reg_number:
            print(f"⚠️  Skipping row: Missing both VIN and registration number")
            continue
        
        # Use VIN as primary identifier, fallback to reg number
        identifier = vin if vin else reg_number
        
        # Build vehicle metadata
        meta = {
            "vin": vin,
            "registration_number": reg_number,
            "brand": brand,
            "model": model,
            "variant": variant,
            "color": color,
            "reg_date": reg_date,
            "chassis_number": chassis_number,
            "mfg_year": mfg_year,
            "rc_owner_name": rc_owner_name,
            # Additional fields that might be in Excel
            "battery_id": str(row.get("battery_id", "")).strip() if pd.notna(row.get("battery_id")) else "",
            "battery_number": str(row.get("battery_number", "")).strip() if pd.notna(row.get("battery_number")) else "",
            "location": str(row.get("location", "")).strip() if pd.notna(row.get("location")) else "",
            "city": str(row.get("city", "")).strip() if pd.notna(row.get("city")) else "",
        }
        
        # Remove empty values
        meta = {k: v for k, v in meta.items() if v}
        
        vehicles.append({
            "vin": vin or reg_number,  # Use VIN as primary ID
            "registration_number": reg_number or vin,  # Fallback
            "meta": meta,
            "model": f"{brand} {model}".strip() if brand or model else None,
        })
    
    return vehicles


def create_vehicle(api_url: str, token: str, operator_slug: str, vehicle_data: dict) -> dict:
    """Create a vehicle via the API."""
    # Use VIN as the registration_number field (we'll update the frontend to display VIN)
    registration_number = vehicle_data["vin"]
    
    payload = {
        "registration_number": registration_number,
        "model": vehicle_data.get("model"),
        "meta": json.dumps(vehicle_data["meta"]),
    }
    
    response = requests.post(
        f"{api_url}/operator/vehicles",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    
    if response.status_code not in (200, 201):
        raise Exception(f"Failed to create vehicle {registration_number}: {response.status_code} - {response.text}")
    
    return response.json()


def get_auth_token(api_url: str, phone: str, operator_slug: str, otp: str = None) -> str:
    """Get authentication token. In dev mode, we can use a dev OTP."""
    # Request OTP
    otp_response = requests.post(
        f"{api_url}/operator/auth/otp/request",
        json={
            "phone": phone,
            "mode": "login",
            "operator_slug": operator_slug,
        },
        timeout=30,
    )
    
    if otp_response.status_code != 200:
        raise Exception(f"Failed to request OTP: {otp_response.status_code} - {otp_response.text}")
    
    otp_data = otp_response.json()
    request_id = otp_data["request_id"]
    dev_otp = otp_data.get("dev_otp") or otp
    
    if not dev_otp:
        raise Exception("No dev OTP available. Please provide OTP manually.")
    
    # Verify OTP
    verify_response = requests.post(
        f"{api_url}/operator/auth/otp/verify",
        json={
            "request_id": request_id,
            "otp": dev_otp,
        },
        timeout=30,
    )
    
    if verify_response.status_code != 200:
        raise Exception(f"Failed to verify OTP: {verify_response.status_code} - {verify_response.text}")
    
    session = verify_response.json()
    return session["access_token"]


def main():
    parser = argparse.ArgumentParser(description="Import vehicles from Excel file")
    parser.add_argument("--file", default="data/Vehicle Inventory Data-271225xlsx.xlsx", help="Path to Excel file")
    parser.add_argument("--operator-slug", default="eleride-fleet", help="Operator slug")
    parser.add_argument("--api-url", default="http://localhost:18080", help="API base URL")
    parser.add_argument("--phone", default="+919999000401", help="Phone number for authentication")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually create vehicles, just show what would be created")
    
    args = parser.parse_args()
    
    # Read Excel file
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        sys.exit(1)
    
    print(f"📖 Reading Excel file: {file_path}")
    vehicles = parse_excel(str(file_path))
    print(f"✅ Found {len(vehicles)} vehicles to import\n")
    
    if args.dry_run:
        print("🔍 DRY RUN - Would create the following vehicles:\n")
        for i, v in enumerate(vehicles[:5], 1):
            print(f"{i}. VIN: {v['vin']}, Reg: {v['registration_number']}")
            print(f"   Model: {v.get('model', 'N/A')}")
            print(f"   Meta keys: {list(v['meta'].keys())}\n")
        if len(vehicles) > 5:
            print(f"... and {len(vehicles) - 5} more vehicles\n")
        print(f"Total: {len(vehicles)} vehicles")
        return
    
    # Authenticate
    print(f"🔐 Authenticating with API: {args.api_url}")
    try:
        token = get_auth_token(args.api_url, args.phone, args.operator_slug)
        print("✅ Authenticated successfully\n")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)
    
    # Import vehicles
    created = 0
    failed = 0
    
    print(f"🚀 Starting import of {len(vehicles)} vehicles...\n")
    
    for i, vehicle_data in enumerate(vehicles, 1):
        try:
            result = create_vehicle(args.api_url, token, args.operator_slug, vehicle_data)
            created += 1
            print(f"✅ [{i}/{len(vehicles)}] Created: {vehicle_data['vin']} ({vehicle_data.get('registration_number', 'N/A')})")
        except Exception as e:
            failed += 1
            print(f"❌ [{i}/{len(vehicles)}] Failed: {vehicle_data['vin']} - {e}")
    
    print(f"\n📊 Import Summary:")
    print(f"   ✅ Created: {created}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📦 Total: {len(vehicles)}")


if __name__ == "__main__":
    main()

