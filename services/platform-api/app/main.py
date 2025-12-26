from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.db import Base, engine
from fastapi.middleware.cors import CORSMiddleware
from app.domains.commitment_policy.router import router as commitment_router
from app.domains.demand_ml.router import router as demand_ml_router
from app.domains.demand_discovery.router import router as demand_router
from app.domains.identity.router import router as identity_router
from app.domains.kyc.router import router as kyc_router
from app.domains.rider.router import router as rider_router
from app.domains.supply.router import router as supply_router
from app.domains.operator_portal.router import router as operator_portal_router
from app.domains.leasing_portal.router import router as leasing_portal_router
from app.domains.matchmaking.router import router as matchmaking_router
from app.domains.cashflow.router import router as cashflow_router
from app.utils.sms import msg91_channels_available, msg91_missing_fields


app = FastAPI(title=settings.app_name)


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request, exc: RequestValidationError):
    # Helpful for debugging 422s in dev. Do not log full bodies in prod.
    if settings.env == "dev":
        try:
            body = await request.body()
        except Exception:
            body = b""
        print(f"[422] path={request.url.path} errors={exc.errors()} body={body[:500]!r}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# Dev CORS so a local frontend can call the API from the browser.
origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # MVP: auto-create tables. Replace with migrations when you harden the system.
    Base.metadata.create_all(bind=engine)
    # MVP: lightweight idempotent "migration" for newly added columns.
    # (create_all does not alter existing tables)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS maintenance_records
                ADD COLUMN IF NOT EXISTS expected_ready_at TIMESTAMPTZ NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS maintenance_records
                ADD COLUMN IF NOT EXISTS expected_takt_hours DOUBLE PRECISION NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS maintenance_records
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS maintenance_records
                ADD COLUMN IF NOT EXISTS assigned_to_user_id TEXT NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS supply_requests
                ADD COLUMN IF NOT EXISTS matched_vehicle_id TEXT NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS supply_requests
                ADD COLUMN IF NOT EXISTS matched_score DOUBLE PRECISION NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS supply_requests
                ADD COLUMN IF NOT EXISTS matched_reasons TEXT NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS supply_requests
                ADD COLUMN IF NOT EXISTS pickup_verified_at TIMESTAMPTZ NULL;
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS supply_requests
                ADD COLUMN IF NOT EXISTS pickup_verified_by_user_id TEXT NULL;
                """
            )
        )


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": settings.app_name,
        "env": settings.env,
        "otp_dev_mode": bool(settings.otp_dev_mode),
        "msg91_missing": msg91_missing_fields(),
        "msg91_channels": msg91_channels_available(),
    }


app.include_router(identity_router, tags=["identity"])
app.include_router(rider_router, tags=["rider"])
app.include_router(kyc_router, tags=["kyc"])
app.include_router(demand_router, tags=["demand-discovery"])
app.include_router(supply_router, tags=["supply-connect"])
app.include_router(operator_portal_router, tags=["operator-portal"])
app.include_router(leasing_portal_router, tags=["leasing-portal"])
app.include_router(matchmaking_router, tags=["matchmaking"])
app.include_router(commitment_router, tags=["commitment-policy"])
app.include_router(demand_ml_router, tags=["demand-ml-admin"])
app.include_router(cashflow_router, tags=["cashflow"])


