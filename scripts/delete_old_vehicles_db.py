#!/usr/bin/env python3
"""
Delete old vehicles from database directly.
This script runs as an ECS task to connect to RDS and delete vehicles matching old patterns.
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "services" / "platform-api"))

from sqlalchemy import create_engine, text
from app.core.config import settings


def delete_old_vehicles(pattern: str = "MH12LZ"):
    """Delete vehicles matching the pattern."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    
    with engine.connect() as conn:
        # Find vehicles matching pattern
        query = text("""
            SELECT v.id, v.registration_number, v.operator_id
            FROM vehicles v
            WHERE v.registration_number LIKE :pattern
        """)
        
        result = conn.execute(query, {"pattern": f"%{pattern}%"})
        old_vehicles = result.fetchall()
        
        print(f"Found {len(old_vehicles)} vehicles matching pattern '{pattern}'")
        
        if not old_vehicles:
            print("No vehicles to delete")
            return
        
        # Show samples
        print("\nSample vehicles to delete:")
        for v in old_vehicles[:10]:
            print(f"  - {v[1]} (ID: {v[0][:8]}...)")
        if len(old_vehicles) > 10:
            print(f"  ... and {len(old_vehicles) - 10} more")
        
        # Delete related records
        vehicle_ids = [v[0] for v in old_vehicles]
        
        print(f"\nDeleting related records...")
        
        # Delete telemetry events
        del_telemetry = conn.execute(
            text("DELETE FROM vehicle_telemetry_events WHERE vehicle_id = ANY(:ids)"),
            {"ids": vehicle_ids}
        )
        print(f"  Deleted {del_telemetry.rowcount} telemetry events")
        
        # Delete devices
        del_devices = conn.execute(
            text("DELETE FROM telematics_devices WHERE vehicle_id = ANY(:ids)"),
            {"ids": vehicle_ids}
        )
        print(f"  Deleted {del_devices.rowcount} device bindings")
        
        # Delete maintenance records
        del_maintenance = conn.execute(
            text("DELETE FROM maintenance_records WHERE vehicle_id = ANY(:ids)"),
            {"ids": vehicle_ids}
        )
        print(f"  Deleted {del_maintenance.rowcount} maintenance records")
        
        # Delete vehicles
        print(f"\nDeleting {len(vehicle_ids)} vehicles...")
        del_vehicles = conn.execute(
            text("DELETE FROM vehicles WHERE id = ANY(:ids)"),
            {"ids": vehicle_ids}
        )
        
        conn.commit()
        print(f"✅ Deleted {del_vehicles.rowcount} vehicles")
        
        # Show remaining count
        remaining = conn.execute(text("SELECT COUNT(*) FROM vehicles")).scalar()
        print(f"📊 Remaining vehicles: {remaining}")


if __name__ == "__main__":
    pattern = os.getenv("DELETE_PATTERN", "MH12LZ")
    print(f"Deleting vehicles matching pattern: {pattern}\n")
    delete_old_vehicles(pattern=pattern)
    print("\n✅ Done!")

