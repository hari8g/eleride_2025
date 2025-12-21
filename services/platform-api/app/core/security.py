import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Literal

import jwt

from app.core.config import settings


Role = Literal["rider", "operator", "lessor", "admin"]


def _now_s() -> int:
    return int(time.time())


def generate_otp() -> str:
    # numeric OTP for MVP; replace with provider integration later
    upper = 10**settings.otp_len
    lower = 10 ** (settings.otp_len - 1)
    return str(secrets.randbelow(upper - lower) + lower)


def hash_otp(phone: str, otp: str) -> str:
    raw = f"{settings.jwt_secret}:{phone}:{otp}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_otp_hash(phone: str, otp: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_otp(phone, otp), expected_hash)


def create_access_token(*, sub: str, role: Role, extra: dict | None = None) -> str:
    now = _now_s()
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + settings.access_token_ttl_seconds,
        "sub": sub,
        "role": role,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@dataclass(frozen=True)
class Principal:
    sub: str
    role: Role
    operator_id: str | None = None
    operator_role: str | None = None
    lessor_id: str | None = None
    lessor_role: str | None = None


def decode_bearer_token(token: str) -> Principal:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    role = payload.get("role", "rider")
    if role not in ("rider", "operator", "lessor", "admin"):
        role = "rider"
    operator_id = payload.get("operator_id")
    operator_role = payload.get("operator_role")
    lessor_id = payload.get("lessor_id")
    lessor_role = payload.get("lessor_role")
    return Principal(
        sub=str(payload["sub"]),
        role=role,
        operator_id=str(operator_id) if operator_id is not None else None,
        operator_role=str(operator_role) if operator_role is not None else None,
        lessor_id=str(lessor_id) if lessor_id is not None else None,
        lessor_role=str(lessor_role) if lessor_role is not None else None,
    )


