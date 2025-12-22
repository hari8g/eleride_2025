import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


def msg91_missing_fields() -> list[str]:
    missing: list[str] = []
    if not settings.msg91_api_key:
        missing.append("MSG91_API_KEY")
    if not settings.msg91_sender_id:
        missing.append("MSG91_SENDER_ID")
    return missing


def _digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "").strip() if ch.isdigit())


def msg91_whatsapp_missing_fields() -> list[str]:
    missing = msg91_missing_fields()
    if not settings.msg91_whatsapp_flow_id:
        missing.append("MSG91_WHATSAPP_FLOW_ID")
    return missing


def msg91_channels_available() -> dict:
    # SMS is "usable" only when template_id is present (DLT reality).
    sms_ready = (not msg91_missing_fields()) and bool(settings.msg91_otp_template_id)
    whatsapp_ready = (not msg91_whatsapp_missing_fields())
    return {"sms": sms_ready, "whatsapp": whatsapp_ready}


def _channel_order() -> list[str]:
    raw = (settings.msg91_otp_channel_order or "").strip()
    if not raw:
        return ["whatsapp", "sms"]
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    # de-dupe while keeping order
    out: list[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return out or ["whatsapp", "sms"]


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
    mobile = _digits(phone)
    if not mobile:
        logger.warning("MSG91 SMS send skipped: invalid phone=%r", phone)
        return False

    # MSG91 OTP API v5
    url = "https://api.msg91.com/api/v5/otp"
    payload = {"mobile": mobile, "otp": otp, "sender": sender_id}
    if template_id:
        payload["template_id"] = template_id
    else:
        logger.warning("MSG91_OTP_TEMPLATE_ID is empty; SMS delivery is likely blocked by DLT. Skipping SMS send.")
        return False
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


def send_otp_msg91_whatsapp(phone: str, otp: str) -> bool:
    """
    WhatsApp OTP via MSG91 Flow API.
    Requires MSG91_WHATSAPP_FLOW_ID and uses MSG91_WHATSAPP_OTP_VAR (default: "OTP") as the variable key.
    """
    missing = msg91_whatsapp_missing_fields()
    api_key = settings.msg91_api_key
    flow_id = settings.msg91_whatsapp_flow_id
    var_key = (settings.msg91_whatsapp_otp_var or "OTP").strip() or "OTP"
    if missing:
        logger.warning("MSG91 WhatsApp not configured; missing=%s", ",".join(missing))
        return False

    mobile = _digits(phone)
    if not mobile:
        logger.warning("MSG91 WhatsApp send skipped: invalid phone=%r", phone)
        return False

    url = "https://api.msg91.com/api/v5/flow/"
    payload: dict = {"flow_id": flow_id, "mobiles": mobile, var_key: otp}
    headers = {"accept": "application/json", "content-type": "application/json", "authkey": api_key}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code // 100 == 2:
            return True
        logger.warning("MSG91 WhatsApp send failed: status=%s body=%s", resp.status_code, resp.text[:300])
        return False
    except Exception as e:
        logger.warning("MSG91 WhatsApp send exception: %s", e)
        return False


def send_otp_best_effort(phone: str, otp: str) -> tuple[bool, str | None, dict]:
    """
    Try configured channels in order and return:
      (ok, channel_used, debug)
    """
    avail = msg91_channels_available()
    order = _channel_order()
    debug = {"available": avail, "order": order}

    for ch in order:
        if ch == "whatsapp" and avail.get("whatsapp"):
            if send_otp_msg91_whatsapp(phone, otp):
                return True, "whatsapp", debug
        if ch == "sms" and avail.get("sms"):
            if send_otp_msg91(phone, otp):
                return True, "sms", debug

    return False, None, debug
