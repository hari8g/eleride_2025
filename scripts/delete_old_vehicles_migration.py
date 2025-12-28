#!/usr/bin/env python3
"""
Migration script to delete old vehicle datapoints.
Run this via ECS task or locally to clean up old vehicles.
"""

import os
import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
platform_api_path = project_root / "services" / "platform-api"
sys.path.insert(0, str(platform_api_path))

# If running in Docker, app might be directly available
try:
    from app.core.config import settings
except ImportError:
    # Fallback: construct database URL from environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise Exception("DATABASE_URL not set and cannot import settings")
    settings = type('Settings', (), {'database_url': db_url})()

from sqlalchemy import create_engine, text


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else "MH12LZ"
    
    print(f"🗑️  Deleting vehicles matching pattern: {pattern}\n")
    
    db_url = getattr(settings, 'database_url', None) or os.getenv('DATABASE_URL')
    if not db_url:
        raise Exception("DATABASE_URL not set")
    
    engine = create_engine(db_url, pool_pre_ping=True)
    
    with engine.begin() as conn:  # begin() auto-commits or rolls back
        # Count vehicles to delete
        count_query = text("""
            SELECT COUNT(*) 
            FROM vehicles 
            WHERE registration_number LIKE :pattern
        """)
        count = conn.execute(count_query, {"pattern": f"%{pattern}%"}).scalar()
        
        if count == 0:
            print(f"✅ No vehicles found matching pattern '{pattern}'")
            return
        
        print(f"📋 Found {count} vehicles to delete\n")
        
        # Show samples
        sample_query = text("""
            SELECT id, registration_number 
            FROM vehicles 
            WHERE registration_number LIKE :pattern
            LIMIT 10
        """)
        samples = conn.execute(sample_query, {"pattern": f"%{pattern}%"}).fetchall()
        print("Sample vehicles to delete:")
        for v_id, reg_num in samples:
            print(f"  - {reg_num} (ID: {v_id[:8]}...)")
        if count > 10:
            print(f"  ... and {count - 10} more\n")
        
        # Delete in correct order (child records first)
        print("🗑️  Deleting related records...")
        
        # Delete telemetry events
        del_telemetry = conn.execute(text("""
            DELETE FROM vehicle_telemetry_events 
            WHERE vehicle_id IN (
                SELECT id FROM vehicles WHERE registration_number LIKE :pattern
            )
        """), {"pattern": f"%{pattern}%"})
        print(f"  ✅ Deleted {del_telemetry.rowcount} telemetry events")
        
        # Delete devices
        del_devices = conn.execute(text("""
            DELETE FROM telematics_devices 
            WHERE vehicle_id IN (
                SELECT id FROM vehicles WHERE registration_number LIKE :pattern
            )
        """), {"pattern": f"%{pattern}%"})
        print(f"  ✅ Deleted {del_devices.rowcount} device bindings")
        
        # Delete maintenance records
        del_maintenance = conn.execute(text("""
            DELETE FROM maintenance_records 
            WHERE vehicle_id IN (
                SELECT id FROM vehicles WHERE registration_number LIKE :pattern
            )
        """), {"pattern": f"%{pattern}%"})
        print(f"  ✅ Deleted {del_maintenance.rowcount} maintenance records")
        
        # Delete vehicles
        print(f"\n🗑️  Deleting {count} vehicles...")
        del_vehicles = conn.execute(text("""
            DELETE FROM vehicles 
            WHERE registration_number LIKE :pattern
        """), {"pattern": f"%{pattern}%"})
        
        print(f"  ✅ Deleted {del_vehicles.rowcount} vehicles")
        
        # Show remaining count
        remaining = conn.execute(text("SELECT COUNT(*) FROM vehicles")).scalar()
        print(f"\n📊 Remaining vehicles: {remaining}")
    
    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    main()

