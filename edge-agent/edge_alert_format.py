import time
from typing import Any, Dict, List, Optional, Tuple


def _sev_rank(sev: str) -> int:
    s = (sev or "").strip().lower()
    if s in {"critical", "crit", "high"}:
        return 30
    if s in {"warn", "warning", "medium"}:
        return 20
    if s in {"info", "low"}:
        return 10
    return 0


def _sev_meta(sev: str) -> Tuple[str, str]:
    s = (sev or "").strip().lower()
    if s in {"critical", "crit", "high"}:
        return "🔴", "CRÍTICO — verifique o dispositivo."
    if s in {"warn", "warning", "medium"}:
        return "🟠", "ATENÇÃO — verifique o dispositivo."
    if s in {"info", "low"}:
        return "🟢", "INFO — evento registrado."
    return "⚪", "INFO — evento registrado."


def _fmt_ts(ts: Optional[float] = None) -> str:
    t = ts if isinstance(ts, (int, float)) and ts > 0 else time.time()
    return time.strftime("%Y.%m.%d-%H:%M:%S", time.localtime(t))


def _clean_problem(s: str) -> str:
    v = (s or "").strip()
    if not v:
        return ""
    for p in ("ALERTA:", "ALERTA -", "ALERTA"):
        if v.upper().startswith(p):
            v = v[len(p) :].strip(" :-")
            break
    return v


def format_telegram_alert(
    base_problem: str,
    matched_events: List[Dict[str, Any]],
    devices_by_id: Dict[int, Dict[str, Any]],
    client_name: str,
) -> str:
    best = None
    best_rank = -1
    for e in matched_events or []:
        r = _sev_rank(str(e.get("severity") or ""))
        if r > best_rank:
            best = e
            best_rank = r

    best = best or (matched_events[0] if matched_events else {})
    did = best.get("device_id")
    did_int = did if isinstance(did, int) else None
    dev = devices_by_id.get(did_int or -1) if did_int is not None else {}

    name = (dev.get("name") or "").strip() or (f"device {did_int}" if did_int else "dispositivo")
    dtype = (dev.get("device_type") or "").strip()
    mac = (dev.get("mac_address") or "").strip()
    ip = (dev.get("ip_address") or "").strip()
    serial = (dev.get("serial_number") or "").strip()

    sev = str(best.get("severity") or "info")
    icon, indication = _sev_meta(sev)

    problem = _clean_problem(base_problem) or (str(best.get("event_type") or "").strip() or "evento")

    details_parts = []
    if dtype:
        details_parts.append(dtype)
    ident = mac or serial or ip
    if ident:
        details_parts.append(ident)
    details = " - ".join(details_parts) if details_parts else "—"

    txt = "\n".join(
        [
            f"{icon} {name}",
            f"Problema: {problem}",
            "",
            f"Host: {name}",
            f"Data do Evento: {_fmt_ts(best.get('ts') or best.get('_ts'))}",
            f"Detalhes do Equipamento: {details}",
            f"Descrição: {client_name or 'ETI SENTINEL'}",
            f"Indicação: {indication}",
        ]
    )
    return txt.strip()
