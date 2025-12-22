import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


def msg91_missing_fields() -> list[str]:
    missing: list[str] = []
    if not settings.msg91_api_key:
        missing.append("MSG91_API_KEY")
    if not settings.msg91_otp_template_id:
        missing.append("MSG91_OTP_TEMPLATE_ID")
    if not settings.msg91_sender_id:
        missing.append("MSG91_SENDER_ID")
    return missing


def send_otp_msg91(phone: str, otp: str) -> bool:
    """
    Fire-and-forget OTP SMS via MSG91.
    Returns True if the request was accepted by MSG91, False otherwise.
    """
    missing = msg91_missing_fields()
    api_key = settings.msg91_api_key
    template_id = settings.msg91_otp_template_id
    sender_id = settings.msg91_sender_id
    if missing:
        logger.warning("MSG91 not configured; missing=%s", ",".join(missing))
        return False

    # MSG91 expects digits; accept "+91..." input.
    mobile = "".join(ch for ch in (phone or "").strip() if ch.isdigit())
    if not mobile:
        logger.warning("MSG91 SMS send skipped: invalid phone=%r", phone)
        return False

    # MSG91 OTP API v5
    url = "https://api.msg91.com/api/v5/otp"
    payload = {
        "template_id": template_id,
        "mobile": mobile,
        "otp": otp,
        "sender": sender_id,
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authkey": api_key,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        if resp.status_code // 100 == 2:
            return True
        logger.warning("MSG91 SMS send failed: status=%s body=%s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        logger.warning("MSG91 SMS send exception: %s", e)
        return False


