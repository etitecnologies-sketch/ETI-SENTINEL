import time
from typing import Any, Dict, List, Optional, Tuple


def _sanitize(s: Any) -> str:
    return str(s or "").strip()


def _as_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        n = int(v)
        return n
    except Exception:
        return None


def _match_event(ev: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    et = _sanitize(cond.get("event_type") or "")
    if et and _sanitize(ev.get("event_type") or "") != et:
        return False
    did = _as_int(cond.get("device_id"))
    if did is not None:
        if _as_int(ev.get("device_id")) != did:
            return False
    ch = _as_int(cond.get("channel"))
    if ch is not None:
        if _as_int(ev.get("channel")) != ch:
            return False
    sev = _sanitize(cond.get("severity") or "")
    if sev and _sanitize(ev.get("severity") or "") != sev:
        return False
    src = _sanitize(cond.get("source") or "")
    if src and _sanitize(ev.get("source") or "") != src:
        return False
    dtype = _sanitize(cond.get("device_type") or "")
    if dtype and _sanitize(ev.get("device_type") or "") != dtype:
        return False
    tag = _sanitize(cond.get("tag") or "")
    if tag:
        tags = ev.get("tags") or []
        if not (isinstance(tags, list) and any(_sanitize(t).lower() == tag.lower() for t in tags)):
            return False
    return True


class RuleEngine:
    def __init__(self) -> None:
        self._recent: List[Dict[str, Any]] = []
        self._last_fire: Dict[Any, float] = {}

    def push_event(self, ev: Dict[str, Any], max_keep: int = 200) -> None:
        now = time.time()
        e = dict(ev)
        e["_ts"] = now
        self._recent.append(e)
        if len(self._recent) > max_keep:
            self._recent = self._recent[-max_keep:]

    def eval(self, rules: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        out: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
        now = time.time()
        for r in rules or []:
            rid = _as_int(r.get("id")) or 0
            rule = r.get("rule") or {}
            within = float(rule.get("within_seconds") or 10)
            cooldown = float(rule.get("cooldown_seconds") or within)
            cooldown_by = _sanitize(rule.get("cooldown_by") or "")
            if_all = rule.get("if_all") or []
            if_not = rule.get("if_not") or []
            actions = rule.get("actions") or []
            if not isinstance(if_all, list) or not if_all:
                continue
            if not isinstance(if_not, list):
                continue
            if not isinstance(actions, list) or not actions:
                continue

            matched: List[Dict[str, Any]] = []
            ok = True
            for cond in if_all:
                if not isinstance(cond, dict):
                    ok = False
                    break
                found = None
                for ev in reversed(self._recent):
                    ts = float(ev.get("_ts") or 0)
                    if now - ts > within:
                        break
                    if _match_event(ev, cond):
                        found = ev
                        break
                if not found:
                    ok = False
                    break
                matched.append(found)

            if ok and if_not:
                for cond in if_not:
                    if not isinstance(cond, dict):
                        ok = False
                        break
                    for ev in reversed(self._recent):
                        ts = float(ev.get("_ts") or 0)
                        if now - ts > within:
                            break
                        if _match_event(ev, cond):
                            ok = False
                            break
                    if not ok:
                        break

            if not ok:
                continue

            fire_key: Any = rid
            if cooldown_by in {"device", "device_id", "per_device"}:
                did = _as_int(matched[0].get("device_id")) if matched else None
                if did is not None:
                    fire_key = (rid, "device_id", int(did))
            elif cooldown_by in {"device_event", "device_id+event_type", "per_device_event"}:
                did = _as_int(matched[0].get("device_id")) if matched else None
                et = _sanitize(matched[0].get("event_type")) if matched else ""
                if did is not None and et:
                    fire_key = (rid, "device_event", int(did), et)

            last = float(self._last_fire.get(fire_key) or 0)
            if now - last < max(1.0, cooldown):
                continue
            self._last_fire[fire_key] = now
            out.append((r, matched))
        return out


def build_message(rule_row: Dict[str, Any], matched: List[Dict[str, Any]], default_prefix: str = "ETI SENTINEL") -> str:
    rule = rule_row.get("rule") or {}
    name = _sanitize(rule_row.get("name") or rule_row.get("id") or "rule")
    tmpl = _sanitize(rule.get("message") or "")
    if tmpl:
        msg = tmpl
        for i, ev in enumerate(matched or []):
            msg = msg.replace(f"{{e{i}.event_type}}", _sanitize(ev.get("event_type") or ""))
            msg = msg.replace(f"{{e{i}.device_id}}", _sanitize(ev.get("device_id") or ""))
            msg = msg.replace(f"{{e{i}.channel}}", _sanitize(ev.get("channel") or ""))
            msg = msg.replace(f"{{e{i}.severity}}", _sanitize(ev.get("severity") or ""))
            try:
                for k, v in (ev or {}).items():
                    if not isinstance(k, str):
                        continue
                    if k.startswith("_"):
                        continue
                    msg = msg.replace(f"{{e{i}.{k}}}", _sanitize(v))
            except Exception:
                pass
        return msg

    bits = [default_prefix, "Automação", name]
    for ev in matched or []:
        et = _sanitize(ev.get("event_type") or "")
        did = _sanitize(ev.get("device_id") or "")
        ch = _sanitize(ev.get("channel") or "")
        bits.append(f"{et} dev={did} ch={ch}".strip())
    return " | ".join([b for b in bits if b])
