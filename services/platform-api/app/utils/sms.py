import logging
from typing import Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_otp_msg91(phone: str, otp: str) -> bool:
    """
    Fire-and-forget OTP SMS via MSG91.
    Returns True if the request was accepted by MSG91, False otherwise.
    """
    api_key = settings.msg91_api_key
    template_id = settings.msg91_otp_template_id
    sender_id = settings.msg91_sender_id
    if not api_key or not template_id or not sender_id:
        logger.warning("MSG91 not configured; skipping SMS send")
        return False

    # MSG91 OTP API v5
    url = "https://api.msg91.com/api/v5/otp"
    payload = {
        "template_id": template_id,
        "mobile": phone,
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


