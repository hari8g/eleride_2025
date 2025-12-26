from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "eleride-platform-api"
    env: str = "dev"

    # JWT
    jwt_secret: str = "dev-secret-change-me"
    jwt_issuer: str = "eleride"
    jwt_audience: str = "eleride-rider"
    access_token_ttl_seconds: int = 60 * 60 * 24

    # Data
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/eleride"
    redis_url: str = "redis://localhost:6379/0"

    # MVP-only knobs
    otp_ttl_seconds: int = 5 * 60
    otp_len: int = 6
    # If true, the backend will generate OTPs and return `dev_otp` even in prod,
    # without requiring MSG91 to be configured.
    otp_dev_mode: bool = False

    # CORS (dev)
    cors_allow_origins: str = (
        "http://localhost:5175,http://127.0.0.1:5175,"
        "http://localhost:5176,http://127.0.0.1:5176,"
        "http://localhost:5177,http://127.0.0.1:5177,"
        "http://localhost:5178,http://127.0.0.1:5178,"
        "http://localhost:5179,http://127.0.0.1:5179,"
        "http://localhost:5180,http://127.0.0.1:5180,"
        "http://localhost:3000"
    )

    # MSG91 (SMS OTP)
    msg91_api_key: str | None = None
    msg91_otp_template_id: str | None = None  # e.g., "120716XXXXX"
    msg91_sender_id: str | None = None       # e.g., "ELERID"

    # MSG91 WhatsApp (OTP via Flow)
    # Create a WhatsApp Flow in MSG91 that accepts a variable (default key: OTP).
    msg91_whatsapp_flow_id: str | None = None
    msg91_whatsapp_otp_var: str = "OTP"

    # Channel order for OTP delivery attempts (comma-separated): e.g. "whatsapp,sms"
    msg91_otp_channel_order: str = "whatsapp,sms"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Some providers (incl. Render) emit `postgres://...` which SQLAlchemy rejects.
        # Normalize to SQLAlchemy-compatible scheme.
        if isinstance(v, str) and v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://") :]
        if isinstance(v, str) and v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://") :]
        return v


settings = Settings()


