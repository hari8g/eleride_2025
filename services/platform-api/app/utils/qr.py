import base64
import hashlib
import hmac
import io
from typing import Any

import qrcode

from app.core.config import settings


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def build_pickup_qr_payload(*, supply_request_id: str, operator_id: str | None, vehicle_reg: str | None) -> str:
    """
    Small, stable payload suitable for a QR code.
    In production this should be a short-lived token stored server-side.
    """
    op = (operator_id or "").strip()
    vr = (vehicle_reg or "").strip().upper()
    msg = f"{supply_request_id}|{op}|{vr}".encode("utf-8")
    sig = _b64url(hmac.new(settings.jwt_secret.encode("utf-8"), msg, hashlib.sha256).digest()[:16])
    return f"ELERIDE|REQ:{supply_request_id}|OP:{op}|VEH:{vr}|SIG:{sig}"


def pickup_qr_code(*, supply_request_id: str, operator_id: str | None, vehicle_reg: str | None) -> str:
    """
    Short human-enterable code derived from the same signed payload.
    Useful as an MVP fallback when you can't scan QR via camera in the fleet portal.
    """
    op = (operator_id or "").strip()
    vr = (vehicle_reg or "").strip().upper()
    msg = f"{supply_request_id}|{op}|{vr}".encode("utf-8")
    sig = _b64url(hmac.new(settings.jwt_secret.encode("utf-8"), msg, hashlib.sha256).digest()[:16])
    return sig[:6].upper()


def qr_png_base64(data: str, *, box_size: int = 5, border: int = 2) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


