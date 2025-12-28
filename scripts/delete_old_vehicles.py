#!/usr/bin/env python3
"""
Delete old vehicle datapoints from AWS database.
This script removes vehicles with old registration number patterns (MH12LZ*, etc.)
while keeping the newly imported vehicles (VOMHPUA*, VRMHPUA*).
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "services" / "platform-api"))

try:
    import requests
except ImportError as e:
    print(f"❌ Error: Missing dependency: {e}")
    print("Install with: pip install requests")
    sys.exit(1)

# Try to import database libraries, but make them optional if using API-only mode
try:
    from sqlalchemy import create_engine, text
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


def get_auth_token(api_url: str, phone: str, operator_slug: str) -> str:
    """Authenticate and get token."""
    print(f"🔐 Authenticating with {api_url}...")
    otp_resp = requests.post(
        f"{api_url}/operator/auth/otp/request",
        json={"phone": phone, "mode": "login", "operator_slug": operator_slug},
        timeout=30,
    )
    if otp_resp.status_code != 200:
        raise Exception(f"OTP request failed: {otp_resp.text}")
    
    otp_data = otp_resp.json()
    request_id = otp_data["request_id"]
    dev_otp = otp_data.get("dev_otp")
    
    if not dev_otp:
        otp = input("Enter OTP manually: ").strip()
    else:
        otp = dev_otp
        print(f"✅ Using dev OTP: {otp}")
    
    verify_resp = requests.post(
        f"{api_url}/operator/auth/otp/verify",
        json={"request_id": request_id, "otp": otp},
        timeout=30,
    )
    if verify_resp.status_code != 200:
        raise Exception(f"OTP verification failed: {verify_resp.text}")
    
    session = verify_resp.json()
    print("✅ Authenticated successfully\n")
    return session["access_token"]


def list_vehicles_api(api_url: str, token: str) -> list[dict]:
    """List all vehicles via API."""
    response = requests.get(
        f"{api_url}/operator/vehicles",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if response.status_code != 200:
        raise Exception(f"Failed to list vehicles: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("items", [])


def delete_vehicle_via_db(db_url: str, operator_id: str, vehicle_id: str) -> bool:
    """Delete a vehicle directly from database."""
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            # Delete related records first
            conn.execute(text("DELETE FROM vehicle_telemetry_events WHERE vehicle_id = :vid"), {"vid": vehicle_id})
            conn.execute(text("DELETE FROM vehicle_devices WHERE vehicle_id = :vid"), {"vid": vehicle_id})
            conn.execute(text("DELETE FROM maintenance_records WHERE vehicle_id = :vid"), {"vid": vehicle_id})
            # Delete the vehicle
            result = conn.execute(
                text("DELETE FROM vehicles WHERE id = :vid AND operator_id = :oid"),
                {"vid": vehicle_id, "oid": operator_id}
            )
            conn.commit()
            return result.rowcount > 0
    except Exception as e:
        print(f"  Error deleting {vehicle_id}: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Delete old vehicle datapoints")
    parser.add_argument("--api-url", default="https://api.eleride.co.in", help="API base URL")
    parser.add_argument("--phone", default="+919999000401", help="Phone number for authentication")
    parser.add_argument("--operator-slug", default="eleride-fleet", help="Operator slug")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually delete, just show what would be deleted")
    parser.add_argument("--pattern", default="MH12LZ", help="Pattern to match old vehicles (default: MH12LZ)")
    
    args = parser.parse_args()
    
    # Get database URL from environment or Terraform
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Try to get from Terraform output
        import subprocess
        try:
            result = subprocess.run(
                ["cd", "infra/terraform", "&&", "terraform", "output", "-raw", "rds_endpoint"],
                shell=True,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                db_endpoint = result.stdout.strip()
                db_password = os.getenv("TF_VAR_db_password", "ElerideDbPwd_2025!Strong#123")
                db_url = f"postgresql+psycopg://postgres:{db_password}@{db_endpoint}:5432/eleride"
        except:
            pass
    
    if not db_url:
        print("❌ Error: DATABASE_URL not set. Set it in environment or ensure Terraform outputs are available.")
        sys.exit(1)
    
    print(f"📋 Listing vehicles from API...")
    
    # Authenticate
    try:
        token = get_auth_token(args.api_url, args.phone, args.operator_slug)
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)
    
    # List vehicles
    try:
        vehicles = list_vehicles_api(args.api_url, token)
        print(f"✅ Found {len(vehicles)} total vehicles\n")
    except Exception as e:
        print(f"❌ Failed to list vehicles: {e}")
        sys.exit(1)
    
    # Identify old vehicles (match pattern in registration_number)
    old_vehicles = [
        v for v in vehicles
        if args.pattern in v.get("registration_number", "")
    ]
    
    print(f"🔍 Found {len(old_vehicles)} vehicles matching pattern '{args.pattern}'")
    print(f"   (Will keep {len(vehicles) - len(old_vehicles)} vehicles)\n")
    
    if not old_vehicles:
        print("✅ No old vehicles to delete!")
        return
    
    # Show sample
    print("Sample old vehicles to be deleted:")
    for v in old_vehicles[:5]:
        print(f"  - {v.get('registration_number', 'N/A')} (ID: {v.get('id', 'N/A')[:8]}...)")
    if len(old_vehicles) > 5:
        print(f"  ... and {len(old_vehicles) - 5} more\n")
    
    # Confirm
    if args.dry_run:
        print(f"\n🔍 DRY RUN: Would delete {len(old_vehicles)} vehicles")
        return
    
    import os
    if os.isatty(0):
        confirm = input(f"\n⚠️  Delete {len(old_vehicles)} old vehicles? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Deletion cancelled")
            return
    else:
        print(f"\n🗑️  Auto-deleting {len(old_vehicles)} old vehicles (non-interactive mode)...")
    
    # Get operator_id from first vehicle (all should have same operator)
    if vehicles:
        # We need operator_id - get it from the operator/me endpoint
        try:
            me_resp = requests.get(
                f"{args.api_url}/operator/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if me_resp.status_code == 200:
                me_data = me_resp.json()
                operator_id = me_data.get("operator", {}).get("id")
                if not operator_id:
                    print("❌ Could not get operator ID")
                    sys.exit(1)
            else:
                print("❌ Failed to get operator info")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error getting operator ID: {e}")
            sys.exit(1)
    else:
        print("❌ No vehicles found")
        return
    
    # Delete vehicles
    deleted = 0
    failed = 0
    
    print(f"\n🗑️  Deleting vehicles...")
    for i, vehicle in enumerate(old_vehicles, 1):
        vehicle_id = vehicle.get("id")
        reg_num = vehicle.get("registration_number", "unknown")
        
        if delete_vehicle_via_db(db_url, operator_id, vehicle_id):
            deleted += 1
            print(f"✅ [{i}/{len(old_vehicles)}] Deleted: {reg_num}")
        else:
            failed += 1
            print(f"❌ [{i}/{len(old_vehicles)}] Failed: {reg_num}")
    
    print(f"\n📊 Deletion Summary:")
    print(f"   ✅ Deleted: {deleted}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📦 Total processed: {len(old_vehicles)}")
    print(f"\n✅ Done! Remaining vehicles: {len(vehicles) - deleted}")


if __name__ == "__main__":
    main()

