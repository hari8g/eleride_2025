#!/usr/bin/env python3
"""Clear all riders, vehicles, and related data from database."""
import sys
sys.path.insert(0, '/app')

from sqlalchemy import text
from app.core.db import engine

tables = [
    "vehicle_telemetry_events", "maintenance_records", "telematics_devices",
    "operator_request_inbox", "operator_memberships", "lessor_memberships",
    "operator_otp_challenges", "lessor_otp_challenges", "operator_users",
    "lessor_users", "vehicle_leases", "vehicles", "supply_requests",
    "commitments", "riders", "operators", "lessors", "otp_challenges",
    "store_demand_rankings_v2", "store_week_signals_v2",
]

print("=== Clearing Database ===\n")
with engine.connect() as conn:
    trans = conn.begin()
    try:
        for table in tables:
            result = conn.execute(text(f"DELETE FROM {table}"))
            print(f"✓ {table}: {result.rowcount} rows deleted")
        trans.commit()
        print("\n✅ All data cleared!\n")
        print("=== Verification ===")
        for t in ["riders", "vehicles", "operators", "lessors", "supply_requests", "commitments"]:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"{t}: {count}")
    except Exception as e:
        trans.rollback()
        print(f"❌ Error: {e}")
        raise
