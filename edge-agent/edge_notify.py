import base64
import os
from typing import Any, Dict, Optional

import requests


def _sanitize(s: Any) -> str:
    return str(s or "").strip()


def _mask(s: str) -> str:
    v = _sanitize(s)
    if len(v) <= 6:
        return v
    return v[:2] + "***" + v[-2:]


def send_telegram(message: str, token: str, chat_id: str, timeout: float = 8.0, log: bool = False) -> bool:
    tok = _sanitize(token)
    cid = _sanitize(chat_id)
    if not tok or not cid:
        return False
    clean = tok[3:] if tok.lower().startswith("bot") else tok
    url = f"https://api.telegram.org/bot{clean}/sendMessage"
    body: Dict[str, Any] = {"chat_id": cid, "text": str(message or "")}
    try:
        r = requests.post(url, json=body, timeout=timeout)
        ok = r.status_code == 200
        if log and not ok:
            print(f"[Edge Notify] telegram failed status={r.status_code} chat={_mask(cid)}")
        return ok
    except Exception as e:
        if log:
            print(f"[Edge Notify] telegram exception: {str(e)}")
        return False


def send_whatsapp_twilio(
    message: str,
    account_sid: str,
    auth_token: str,
    to_number: str,
    from_number: Optional[str] = None,
    content_sid: Optional[str] = None,
    timeout: float = 10.0,
    log: bool = False,
) -> bool:
    sid = _sanitize(account_sid)
    tok = _sanitize(auth_token)
    to_raw = _sanitize(to_number)
    if not sid or not tok or not to_raw:
        return False

    to = to_raw if to_raw.startswith("+") else f"+{to_raw}"
    to_final = to if to.startswith("whatsapp:") else f"whatsapp:{to}"

    frm = _sanitize(from_number) or _sanitize(os.getenv("TWILIO_WHATSAPP_NUMBER") or "")
    frm_final = frm if frm.startswith("whatsapp:") else (f"whatsapp:{frm}" if frm else "whatsapp:+14155238886")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    auth = base64.b64encode(f"{sid}:{tok}".encode("utf-8")).decode("ascii")

    data: Dict[str, str] = {"To": to_final, "From": frm_final}
    csid = _sanitize(content_sid) or _sanitize(os.getenv("TWILIO_CONTENT_SID") or "")
    if csid:
        data["ContentSid"] = csid
    else:
        data["Body"] = str(message or "")

    try:
        r = requests.post(url, data=data, headers={"Authorization": f"Basic {auth}"}, timeout=timeout)
        ok = r.status_code in (200, 201)
        if log and not ok:
            masked_to = to_final.replace("+", "").replace("whatsapp:", "")
            if len(masked_to) > 4:
                masked_to = masked_to[:2] + "***" + masked_to[-2:]
            print(f"[Edge Notify] whatsapp(twilio) failed status={r.status_code} to={masked_to}")
        return ok
    except Exception as e:
        if log:
            print(f"[Edge Notify] whatsapp(twilio) exception: {str(e)}")
        return False

