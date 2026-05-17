import base64
import json
import os
import threading
import time
import uuid
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

from camera_collector import _sanitize as sanitize
from camera_collector import discover_cameras
from edge_alert_format import format_telegram_alert
from edge_notify import send_telegram, send_telegram_photo, send_whatsapp_twilio
from edge_rules import RuleEngine, build_message
from workers.risk_scorer import RiskScorer
from workers.narrative_reporter import NarrativeReporter


def _sanitize_base_url(url: str) -> str:
    u = sanitize(url)
    if not u:
        return u
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _append_log(path: Path, msg: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        path.write_text(path.read_text(encoding="utf-8") + f"[{ts}] {msg}\n", encoding="utf-8")
    except Exception:
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            path.write_text(f"[{ts}] {msg}\n", encoding="utf-8")
        except Exception:
            pass


def _parse_query(path: str) -> Dict[str, str]:
    try:
        if "?" not in (path or ""):
            return {}
        qs = (path or "").split("?", 1)[1]
        out: Dict[str, str] = {}
        for part in qs.split("&"):
            if not part:
                continue
            if "=" not in part:
                out[sanitize(part)] = ""
                continue
            k, v = part.split("=", 1)
            out[sanitize(k)] = sanitize(v)
        return out
    except Exception:
        return {}


def _mask(s: Any) -> str:
    v = sanitize(s)
    if not v:
        return ""
    if len(v) <= 6:
        return v
    return v[:2] + "***" + v[-2:]


def _is_loopback_ip(ip: str) -> bool:
    s = sanitize(ip)
    if not s:
        return False
    if s == "::1":
        return True
    if s.startswith("127."):
        return True
    return False


class PushRelay:
    def __init__(self, here: Path, env: Dict[str, str], log_path: Path):
        self.here = here
        self.env = env
        self.log_path = log_path
        self._lock = threading.Lock()
        self._client_notify: Dict[str, str] = {}
        self._global_notify: Dict[str, str] = {}
        self._rules: list = []
        self._devices_by_id: Dict[int, Dict[str, Any]] = {}
        self._last_cfg_ts = 0.0
        self._last_global_cfg_ts = 0.0
        self._last_rules_ts = 0.0
        self._last_devices_ts = 0.0
        self._last_push_ok = 0.0
        self._queue_path = here / ".state" / "push_queue.jsonl"
        self._engine = RuleEngine()
        self._stop = False
        self._sess = requests.Session()
        self._event_last_ts: Dict[tuple, float] = {}
        self._videoloss_started_ts: Dict[tuple, float] = {}
        self._events_total = 0
        self._notify_suppressed_total = 0
        self._last_event_ts = 0.0
        self._stream_state: Dict[tuple, Dict[str, Any]] = {}
        self._recent_events: list = []
        self._risk = RiskScorer()
        self._narrator = NarrativeReporter(env)

    def start(self) -> None:
        threading.Thread(target=self._loop_refresh, daemon=True).start()
        threading.Thread(target=self._loop_flush, daemon=True).start()
        threading.Thread(target=self._loop_state, daemon=True).start()

    def stop(self) -> None:
        self._stop = True

    def status(self) -> Dict[str, Any]:
        with self._lock:
            q = self._queue_size()
            data = {
                "client_id": sanitize(self.env.get("CLIENT_ID") or ""),
                "last_client_notify_fetch": self._last_cfg_ts,
                "last_global_notify_fetch": self._last_global_cfg_ts,
                "last_rules_fetch": self._last_rules_ts,
                "last_devices_fetch": self._last_devices_ts,
                "last_push_ok": self._last_push_ok,
                "queue_size": q,
                "rules_count": len(self._rules or []),
                "events_total": int(self._events_total),
                "notify_suppressed_total": int(self._notify_suppressed_total),
                "last_event_ts": float(self._last_event_ts),
            }
        data["risk"] = self._risk.snapshot()
        return data

    def rules_summary(self) -> Any:
        with self._lock:
            return [{"id": r.get("id"), "name": r.get("name"), "enabled": r.get("enabled")} for r in (self._rules or [])]

    def events_recent(self, limit: int = 50, prefix: str = "", source: str = "", event_type: str = "") -> Any:
        try:
            lim = int(limit or 50)
        except Exception:
            lim = 50
        lim = max(1, min(500, lim))
        pfx = sanitize(prefix or "")
        src = sanitize(source or "")
        et = sanitize(event_type or "")

        with self._lock:
            data = list(self._recent_events)

        if not (pfx or src or et):
            return data[-lim:]

        out = []
        for rec in reversed(data):
            try:
                if pfx and not sanitize(rec.get("event_type") or "").startswith(pfx):
                    continue
                if src and sanitize(rec.get("source") or "") != src:
                    continue
                if et and sanitize(rec.get("event_type") or "") != et:
                    continue
                out.append(rec)
                if len(out) >= lim:
                    break
            except Exception:
                continue
        return list(reversed(out))

    def handle_event(self, payload: Dict[str, Any], source: str) -> Dict[str, Any]:
        # BLOQUEIO PROFISSIONAL MULTITENANT
        # Força o client_id do .env local para evitar vazamento de dados entre redes de clientes diferentes
        env_client_id = sanitize(self.env.get("CLIENT_ID") or "")
        if env_client_id:
            try:
                payload["client_id"] = int(env_client_id)
            except:
                pass

        ev = {
            "event_type": sanitize(payload.get("event_type") or ""),
            "channel": int(payload.get("channel") or 0) if str(payload.get("channel") or "").isdigit() else 0,
            "severity": sanitize(payload.get("severity") or "info"),
            "description": sanitize(payload.get("description") or ""),
            "device_id": int(payload.get("device_id") or 0) if str(payload.get("device_id") or "").isdigit() else None,
            "source": sanitize(source or payload.get("source") or "edge"),
        }
        try:
            try:
                snap_max = int(self.env.get("EDGE_SNAPSHOT_B64_MAX_LEN") or 1400000)
            except Exception:
                snap_max = 800000
            for k, v in (payload or {}).items():
                kk = sanitize(k)
                if not kk:
                    continue
                lk = kk.lower()
                # Permitir token para encaminhamento à nuvem, mas ignorar senhas
                if lk in {"password", "pass"} or "password" in lk or "pass" in lk:
                    continue
                if kk in ev or kk.startswith("_"):
                    continue
                if isinstance(v, (int, float)):
                    ev[kk] = v
                elif isinstance(v, str) and len(v) <= 200:
                    ev[kk] = sanitize(v)
                elif lk == "tags" and isinstance(v, list):
                    tags = []
                    for t in v:
                        if isinstance(t, str) and sanitize(t):
                            tags.append(sanitize(t))
                    if tags:
                        ev["tags"] = tags[:20]
                elif lk == "snapshot_jpg_b64" and isinstance(v, str) and 0 < len(v) <= max(1000, snap_max):
                    ev["snapshot_jpg_b64"] = v.strip()
        except Exception:
            pass

        now_evt = time.time()
        with self._lock:
            self._events_total += 1
            self._last_event_ts = now_evt
            try:
                snap = ev.get("snapshot_jpg_b64")
                has_snap = isinstance(snap, str) and bool(snap)
                snap_len = int(len(snap)) if isinstance(snap, str) else 0
            except Exception:
                has_snap = False
                snap_len = 0
            rec = {
                "ts": float(now_evt),
                "event_type": sanitize(ev.get("event_type") or ""),
                "device_id": ev.get("device_id"),
                "device_type": sanitize(ev.get("device_type") or ""),
                "channel": int(ev.get("channel") or 0),
                "severity": sanitize(ev.get("severity") or ""),
                "source": sanitize(ev.get("source") or ""),
                "description": sanitize(ev.get("description") or "")[:200],
                "tags": ev.get("tags") if isinstance(ev.get("tags"), list) else [],
                "has_snapshot": bool(has_snap),
                "snapshot_len": int(snap_len),
            }
            self._recent_events.append(rec)
            if len(self._recent_events) > 5000:
                self._recent_events = self._recent_events[-2000:]

        self._risk.ingest(ev)

        suppress_notify = False
        et = sanitize(ev.get("event_type") or "")
        did = ev.get("device_id")
        ch = int(ev.get("channel") or 0)
        suppress_list = set()
        try:
            raw = sanitize(self.env.get("EDGE_SUPPRESS_EVENT_TYPES") or "")
            if raw:
                suppress_list = {sanitize(x).strip() for x in raw.split(",") if sanitize(x).strip()}
        except Exception:
            suppress_list = set()
        if et and et in suppress_list:
            suppress_notify = True

        if et in {"edge_heartbeat", "gateway_heartbeat"}:
            suppress_notify = True

        state_key = None
        if isinstance(did, int) and did > 0:
            state_key = (int(did), int(ch))
        if state_key and et in {"videoloss_started", "videoloss_stopped", "edge_stream_offline", "edge_stream_online"}:
            try:
                confirm_offline_s = float(self.env.get("EDGE_VIDEOLOSS_CONFIRM_SECONDS") or 15)
            except Exception:
                confirm_offline_s = 15.0
            try:
                confirm_online_s = float(self.env.get("EDGE_RECOVERY_CONFIRM_SECONDS") or 10)
            except Exception:
                confirm_online_s = 10.0
            try:
                alert_dedupe_s = float(self.env.get("EDGE_EVENT_DEDUPE_SECONDS") or 600)
            except Exception:
                alert_dedupe_s = 600.0
            notify_recovery = _bool(self.env.get("EDGE_NOTIFY_RECOVERY") or "0")

            with self._lock:
                st = self._stream_state.get(state_key) or {"status": "unknown", "pending_offline": None, "pending_online": None, "last_alert_ts": 0.0}
                status = sanitize(st.get("status") or "unknown")
                last_alert_ts = float(st.get("last_alert_ts") or 0.0)

                if et in {"videoloss_started", "edge_stream_offline"}:
                    st["pending_offline"] = {"ts": now_evt, "ev": dict(ev), "payload": dict(payload), "source": sanitize(source)}
                    st["pending_online"] = None
                    if status != "offline":
                        st["status"] = "unstable"
                    self._stream_state[state_key] = st
                    suppress_notify = True

                elif et in {"videoloss_stopped", "edge_stream_online"}:
                    st["pending_offline"] = None
                    if status == "offline":
                        if notify_recovery:
                            st["pending_online"] = {"ts": now_evt, "ev": dict(ev), "payload": dict(payload), "source": sanitize(source)}
                        else:
                            st["pending_online"] = None
                            st["status"] = "online"
                        self._stream_state[state_key] = st
                        suppress_notify = True
                    else:
                        st["pending_online"] = None
                        st["status"] = "online"
                        self._stream_state[state_key] = st
                        suppress_notify = True

                st = self._stream_state.get(state_key) or st
                st["confirm_offline_s"] = confirm_offline_s
                st["confirm_online_s"] = confirm_online_s
                st["alert_dedupe_s"] = alert_dedupe_s
                st["notify_recovery"] = bool(notify_recovery)
                if last_alert_ts:
                    st["last_alert_ts"] = last_alert_ts
                self._stream_state[state_key] = st
        if et in {"videoloss_started", "videoloss_stopped"} and isinstance(did, int) and did > 0:
            now = time.time()
            try:
                dedupe_seconds = float(self.env.get("EDGE_EVENT_DEDUPE_SECONDS") or 60)
            except Exception:
                dedupe_seconds = 60.0
            try:
                min_videoloss_seconds = float(self.env.get("EDGE_VIDEOLOSS_MIN_SECONDS") or 30)
            except Exception:
                min_videoloss_seconds = 30.0


            sig = (et, int(did), int(ch))
            with self._lock:
                last = float(self._event_last_ts.get(sig) or 0)
                self._event_last_ts[sig] = now
                if et == "videoloss_started":
                    self._videoloss_started_ts[(int(did), int(ch))] = now
                started = float(self._videoloss_started_ts.get((int(did), int(ch))) or 0)
                if et == "videoloss_stopped":
                    self._videoloss_started_ts.pop((int(did), int(ch)), None)

            if last and (now - last) < max(1.0, dedupe_seconds):
                suppress_notify = True
            if et == "videoloss_stopped" and started and (now - started) < max(0.0, min_videoloss_seconds):
                suppress_notify = True

        fired_count = 0
        if not suppress_notify:
            fired_count = self._notify_from_event(ev)
        else:
            with self._lock:
                self._notify_suppressed_total += 1

        forwarded = self._forward_push(payload, source)
        return {"ok": True, "forwarded": forwarded, "rules_fired": fired_count, "notify_suppressed": suppress_notify}

    def _notify_from_event(self, ev: Dict[str, Any]) -> int:
        self._engine.push_event(ev)

        with self._lock:
            rules = list(self._rules or [])
            cfg = dict(self._client_notify or {})
            gcfg = dict(self._global_notify or {})
            devs = dict(self._devices_by_id or {})

        fired = self._engine.eval(rules)
        fired_count = 0
        if fired:
            for rule_row, matched in fired:
                rule = rule_row.get("rule") or {}
                actions = rule.get("actions") or []
                base_msg = build_message(rule_row, matched)
                msg = format_telegram_alert(base_msg, matched, devs, cfg.get("client_name") or "")
                snap_bytes = None
                try:
                    for e in matched or []:
                        b64 = e.get("snapshot_jpg_b64") if isinstance(e, dict) else None
                        if isinstance(b64, str) and b64:
                            try:
                                raw = b64.encode("ascii", errors="ignore")
                                snap_bytes = base64.b64decode(raw)
                                if snap_bytes:
                                    break
                            except Exception:
                                snap_bytes = None
                except Exception:
                    snap_bytes = None
                for a in actions:
                    if not isinstance(a, dict):
                        continue
                    if sanitize(a.get("type") or "") != "notify":
                        continue
                    chans = a.get("channels") or ["telegram", "whatsapp"]
                    if not isinstance(chans, list):
                        chans = [str(chans)]
                    dedupe = set()
                    if "telegram" in chans:
                        ctok = cfg.get("telegram_token") or ""
                        ccid = cfg.get("telegram_chat_id") or ""
                        if ctok and ccid:
                            dedupe.add("tg:" + ccid)
                        log_enabled = _bool(self.env.get("EDGE_NOTIFY_LOG") or "0")
                        ok_client = False
                        if snap_bytes:
                            ok_client = send_telegram_photo(msg, ctok, ccid, snap_bytes, log=log_enabled)
                            if not ok_client:
                                ok_client = send_telegram(msg, ctok, ccid, log=log_enabled)
                        else:
                            ok_client = send_telegram(msg, ctok, ccid, log=log_enabled)
                        gt = gcfg.get("telegram_token") or ""
                        gc = gcfg.get("telegram_chat_id") or ""
                        ok_global = None
                        if gt and gc and ("tg:" + gc) not in dedupe:
                            if snap_bytes:
                                ok_global = send_telegram_photo(msg, gt, gc, snap_bytes, log=log_enabled)
                                if not ok_global:
                                    ok_global = send_telegram(msg, gt, gc, log=log_enabled)
                            else:
                                ok_global = send_telegram(msg, gt, gc, log=log_enabled)
                        if log_enabled:
                            print(
                                f"[Edge Notify] tg client={_mask(ccid)} ok={ok_client} | global={_mask(gc)} ok={ok_global}"
                            )
                    if "whatsapp" in chans:
                        cwa = cfg.get("wa_number") or ""
                        if (cfg.get("wa_instance") or "") and (cfg.get("wa_token") or "") and cwa:
                            dedupe.add("wa:" + cwa.lstrip("+").replace("whatsapp:", ""))
                        log_enabled = _bool(self.env.get("EDGE_NOTIFY_LOG") or "0")
                        ok_client = send_whatsapp_twilio(
                            msg,
                            cfg.get("wa_instance") or "",
                            cfg.get("wa_token") or "",
                            cwa,
                            from_number=(gcfg.get("twilio_whatsapp_number") or sanitize(self.env.get("TWILIO_WHATSAPP_NUMBER") or "")),
                            content_sid=(gcfg.get("twilio_content_sid") or sanitize(self.env.get("TWILIO_CONTENT_SID") or "")),
                            log=log_enabled,
                        )
                        gwa = gcfg.get("wa_number") or ""
                        gwa_key = gwa.lstrip("+").replace("whatsapp:", "")
                        ok_global = None
                        if (gcfg.get("wa_instance") or "") and (gcfg.get("wa_token") or "") and gwa and ("wa:" + gwa_key) not in dedupe:
                            ok_global = send_whatsapp_twilio(
                                msg,
                                gcfg.get("wa_instance") or "",
                                gcfg.get("wa_token") or "",
                                gwa,
                                from_number=(gcfg.get("twilio_whatsapp_number") or sanitize(self.env.get("TWILIO_WHATSAPP_NUMBER") or "")),
                                content_sid=(gcfg.get("twilio_content_sid") or sanitize(self.env.get("TWILIO_CONTENT_SID") or "")),
                                log=log_enabled,
                            )
                        if log_enabled:
                            print(
                                f"[Edge Notify] wa client={_mask(cwa)} ok={ok_client} | global={_mask(gwa)} ok={ok_global}"
                            )
                fired_count += 1

        if fired_count > 0:
            d_id = ev.get("device_id")
            d_name = ""
            if isinstance(d_id, int) and d_id in devs:
                d_name = devs[d_id].get("name") or devs[d_id].get("device_type") or ""
            risk_snap = self._risk.snapshot()
            log_enabled = _bool(self.env.get("EDGE_NOTIFY_LOG") or "0")
            def _tg_follow_up(msg: str, _cfg: dict = cfg, _gcfg: dict = gcfg) -> None:
                tok = _cfg.get("telegram_token") or ""
                cid_t = _cfg.get("telegram_chat_id") or ""
                if tok and cid_t:
                    send_telegram(msg, tok, cid_t, log=log_enabled)
            self._narrator.analyze_async(ev, d_name, risk_snap, _tg_follow_up)

        return fired_count

    def _loop_state(self) -> None:
        while not self._stop:
            try:
                self._process_stream_state()
            except Exception:
                pass
            time.sleep(1)

    def _process_stream_state(self) -> None:
        now = time.time()
        to_fire: list = []
        with self._lock:
            for k, st in list(self._stream_state.items()):
                status = sanitize(st.get("status") or "unknown")
                confirm_offline_s = float(st.get("confirm_offline_s") or 15)
                confirm_online_s = float(st.get("confirm_online_s") or 10)
                alert_dedupe_s = float(st.get("alert_dedupe_s") or 600)
                last_alert_ts = float(st.get("last_alert_ts") or 0.0)

                po = st.get("pending_offline")
                if po and isinstance(po, dict):
                    ts = float(po.get("ts") or 0)
                    if ts and (now - ts) >= max(0.0, confirm_offline_s) and status != "offline":
                        if (not last_alert_ts) or (now - last_alert_ts) >= max(1.0, alert_dedupe_s):
                            st["status"] = "offline"
                            st["pending_offline"] = None
                            st["last_alert_ts"] = now
                            to_fire.append(po.get("ev"))
                        else:
                            st["status"] = "offline"
                            st["pending_offline"] = None

                pn = st.get("pending_online")
                if pn and isinstance(pn, dict):
                    ts = float(pn.get("ts") or 0)
                    if ts and (now - ts) >= max(0.0, confirm_online_s):
                        st["status"] = "online"
                        st["pending_online"] = None
                        to_fire.append(pn.get("ev"))

                self._stream_state[k] = st

        for ev in to_fire:
            if isinstance(ev, dict):
                try:
                    self._notify_from_event(ev)
                except Exception:
                    pass

    def _ingest_url(self) -> str:
        return _sanitize_base_url(self.env.get("INGEST_API_URL") or "")

    def _collector_key(self) -> str:
        return sanitize(self.env.get("COLLECTOR_KEY") or "")

    def _client_id(self) -> Optional[int]:
        cid = sanitize(self.env.get("CLIENT_ID") or "")
        return int(cid) if cid.isdigit() else None

    def _loop_refresh(self) -> None:
        while not self._stop:
            try:
                self._refresh_client_notify()
                self._refresh_global_notify()
                self._refresh_rules()
                self._refresh_devices()
            except Exception:
                pass
            time.sleep(max(3, int(self.env.get("EDGE_REFRESH_SECONDS") or 10)))

    def _refresh_client_notify(self) -> None:
        url = self._ingest_url()
        key = self._collector_key()
        cid = self._client_id()
        if not url or not key or not cid:
            return
        try:
            r = self._sess.get(
                url + "/collector/client-notify",
                headers={"x-collector-key": key},
                params={"client_id": cid},
                timeout=(5, 18),
            )
            if r.status_code != 200:
                return
            data = r.json() or {}
            with self._lock:
                self._client_notify = {
                    "client_name": sanitize(data.get("name") or ""),
                    "telegram_token": sanitize(data.get("telegram_token") or ""),
                    "telegram_chat_id": sanitize(data.get("telegram_chat_id") or ""),
                    "wa_instance": sanitize(data.get("wa_instance") or ""),
                    "wa_token": sanitize(data.get("wa_token") or ""),
                    "wa_number": sanitize(data.get("wa_number") or ""),
                }
                self._last_cfg_ts = time.time()
        except Exception:
            return

    def _refresh_rules(self) -> None:
        url = self._ingest_url()
        key = self._collector_key()
        cid = self._client_id()
        if not url or not key or not cid:
            return
        try:
            r = self._sess.get(
                url + "/collector/automation-rules",
                headers={"x-collector-key": key},
                params={"client_id": cid},
                timeout=(5, 18),
            )
            if r.status_code != 200:
                return
            data = r.json() or []
            if not isinstance(data, list):
                return
            with self._lock:
                self._rules = data
                self._last_rules_ts = time.time()
        except Exception:
            return

    def _refresh_global_notify(self) -> None:
        url = self._ingest_url()
        key = self._collector_key()
        cid = self._client_id()
        if not url or not key or not cid:
            return
        try:
            r = self._sess.get(
                url + "/collector/global-notify",
                headers={"x-collector-key": key},
                params={"client_id": cid},
                timeout=(5, 18),
            )
            if r.status_code != 200:
                return
            data = r.json() or {}
            with self._lock:
                self._global_notify = {
                    "telegram_token": sanitize(data.get("telegram_token") or ""),
                    "telegram_chat_id": sanitize(data.get("telegram_chat_id") or ""),
                    "wa_instance": sanitize(data.get("wa_instance") or ""),
                    "wa_token": sanitize(data.get("wa_token") or ""),
                    "wa_number": sanitize(data.get("wa_number") or ""),
                    "twilio_whatsapp_number": sanitize(data.get("twilio_whatsapp_number") or ""),
                    "twilio_content_sid": sanitize(data.get("twilio_content_sid") or ""),
                }
                self._last_global_cfg_ts = time.time()
        except Exception:
            return

    def _refresh_devices(self) -> None:
        url = self._ingest_url()
        key = self._collector_key()
        cid = self._client_id()
        if not url or not key or not cid:
            return
        try:
            r = self._sess.get(
                url + "/collector/devices",
                headers={"x-collector-key": key},
                params={"client_id": cid},
                timeout=(5, 18),
            )
            if r.status_code != 200:
                return
            data = r.json() or []
            if not isinstance(data, list):
                return
            by_id: Dict[int, Dict[str, Any]] = {}
            for row in data:
                if not isinstance(row, dict):
                    continue
                did = row.get("device_id")
                did_int = int(did) if str(did or "").isdigit() else None
                if did_int is None:
                    continue
                by_id[did_int] = {
                    "device_id": did_int,
                    "name": sanitize(row.get("name") or ""),
                    "device_type": sanitize(row.get("device_type") or ""),
                    "ip_address": sanitize(row.get("ip_address") or ""),
                    "ddns_address": sanitize(row.get("ddns_address") or ""),
                    "hostname": sanitize(row.get("hostname") or ""),
                    "mac_address": sanitize(row.get("mac_address") or ""),
                    "serial_number": sanitize(row.get("serial_number") or ""),
                }
            with self._lock:
                self._devices_by_id = by_id
                self._last_devices_ts = time.time()
        except Exception:
            return

    def _queue_size(self) -> int:
        try:
            if not self._queue_path.exists():
                return 0
            return len([1 for _ in self._queue_path.read_text(encoding="utf-8").splitlines() if _.strip()])
        except Exception:
            return 0

    def _enqueue(self, payload: Dict[str, Any], source: str) -> None:
        try:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            item = {"ts": time.time(), "payload": payload, "source": sanitize(source)}
            with self._queue_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _read_queue(self) -> Any:
        try:
            if not self._queue_path.exists():
                return []
            lines = [ln for ln in self._queue_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            out = []
            for ln in lines:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def _write_queue(self, items: Any) -> None:
        try:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            txt = "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in (items or []) if it)
            self._queue_path.write_text(txt, encoding="utf-8")
        except Exception:
            pass

    def _forward_push(self, payload: Dict[str, Any], source: str) -> bool:
        url = self._ingest_url()
        if not url:
            return False

        # Eventos de heartbeat interno sao sinais de monitoramento local.
        # Nao devem ser encaminhados para a nuvem pois o HeartbeatWorker
        # ja envia o sinal de vida com metricas do sistema separadamente.
        et = sanitize((payload or {}).get("event_type") or "")
        _no_forward = {"edge_heartbeat", "gateway_heartbeat"}
        try:
            extra = sanitize(self.env.get("EDGE_FORWARD_SUPPRESS_EVENT_TYPES") or "")
            if extra:
                _no_forward |= {sanitize(x) for x in extra.split(",") if sanitize(x)}
        except Exception:
            pass
        if et in _no_forward:
            return True  # Registra localmente mas nao envia para a nuvem

        # GARANTIA MULTITENANT: Força o client_id do agente antes de enviar para a nuvem
        cid = self._client_id()
        safe_payload = dict(payload or {})
        if cid:
            try:
                safe_payload["client_id"] = int(cid)
            except:
                pass
        
        safe_payload.pop("snapshot_jpg_b64", None)
        key = self._collector_key()
        try:
            r = self._sess.post(
                url + "/push",
                json=safe_payload,
                headers={
                    "x-event-source": sanitize(source or "edge"),
                    "x-collector-key": key,
                },
                timeout=(5, 12),
            )
            ok = r.status_code == 200
            if ok:
                with self._lock:
                    self._last_push_ok = time.time()
            return ok
        except Exception:
            self._enqueue(safe_payload, source)
            return False

    def _loop_flush(self) -> None:
        while not self._stop:
            try:
                self._flush_once()
            except Exception:
                pass
            time.sleep(max(2, int(self.env.get("EDGE_FLUSH_SECONDS") or 5)))

    def _flush_once(self) -> None:
        items = self._read_queue()
        if not items:
            return
        url = self._ingest_url()
        if not url:
            return
        cid = self._client_id()
        keep = []
        for it in items:
            payload = it.get("payload") if isinstance(it, dict) else None
            src = it.get("source") if isinstance(it, dict) else ""
            if not isinstance(payload, dict):
                continue
            
            # GARANTIA MULTITENANT NO FLUSH
            if cid:
                try:
                    payload["client_id"] = int(cid)
                except:
                    pass

            try:
                r = self._sess.post(
                    url + "/push",
                    json=payload,
                    headers={"x-event-source": sanitize(src or "edge")},
                    timeout=(5, 12),
                )
                if r.status_code == 200:
                    with self._lock:
                        self._last_push_ok = time.time()
                    continue
            except Exception:
                pass
            keep.append(it)
        if len(keep) != len(items):
            self._write_queue(keep)


class JobStore:
    def __init__(self, state_path: Path):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._latest: Optional[str] = None
        self._state_path = state_path

    def create(self) -> str:
        jid = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self._jobs[jid] = {"job_id": jid, "status": "running", "started_at": now, "finished_at": None, "result": None, "error": None}
            self._latest = jid
            self._save()
        return jid

    def set_done(self, jid: str, result: Any) -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(jid)
            if not job:
                return
            job["status"] = "done"
            job["finished_at"] = now
            job["result"] = result
            job["error"] = None
            self._latest = jid
            self._save()

    def set_error(self, jid: str, err: str) -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(jid)
            if not job:
                return
            job["status"] = "error"
            job["finished_at"] = now
            job["error"] = sanitize(err)
            self._latest = jid
            self._save()

    def get(self, jid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            j = self._jobs.get(jid)
            return json.loads(json.dumps(j)) if j else None

    def latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._latest:
                return None
            j = self._jobs.get(self._latest)
            return json.loads(json.dumps(j)) if j else None

    def _save(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"latest": self._latest, "jobs": self._jobs}
            self._state_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def _push_to_server(ingest_api_url: str, collector_key: str, agent_id: str, client_id: Optional[int], cameras: Any) -> None:
    items = []
    for c in cameras or []:
        ip = sanitize(c.get("ip") or "")
        if not ip:
            continue
        xaddr = sanitize(c.get("xaddr") or "")
        ports = [80, 554] if xaddr else [554]
        raw = {
            "source": "camera_discovery",
            "manufacturer": sanitize(c.get("manufacturer") or ""),
            "model": sanitize(c.get("model") or ""),
            "firmware": sanitize(c.get("firmware") or ""),
            "serial": sanitize(c.get("serial") or ""),
            "ptz": bool(c.get("ptz")),
            "profiles": c.get("profiles") or [],
        }
        items.append(
            {
                "ip_address": ip,
                "mac_address": "",
                "hostname": "",
                "vendor": raw.get("manufacturer") or "",
                "guess_type": "camera",
                "open_ports": ports,
                "onvif_xaddrs": xaddr,
                "raw": raw,
            }
        )

    if not items:
        return

    url = ingest_api_url.rstrip("/") + "/collector/discovery"
    body: Dict[str, Any] = {"agent_id": agent_id, "items": items}
    if client_id:
        body["client_id"] = int(client_id)
    requests.post(url, headers={"x-collector-key": collector_key}, json=body, timeout=25)


def _run_scan(job_id: str, store: JobStore, env: Dict[str, str], user: str, password: str, timeout: float) -> None:
    try:
        ingest_api_url = _sanitize_base_url(env.get("INGEST_API_URL") or "")
        collector_key = sanitize(env.get("COLLECTOR_KEY") or "")

        creds_by_ip = None
        remote_creds = {
            "enabled": False,
            "fetched": False,
            "http_status": None,
            "ip_count": 0,
            "error": "",
            "error_detail": "",
            "url": "",
        }
        if _bool(env.get("CAMERA_REMOTE_CREDS") or "1") and ingest_api_url and collector_key:
            remote_creds["enabled"] = True
            remote_creds["url"] = ingest_api_url.rstrip("/") + "/collector/onvif-config"
            try:
                last_exc = None
                for _ in range(2):
                    try:
                        r = requests.get(
                            remote_creds["url"],
                            headers={"x-collector-key": collector_key},
                            timeout=(5, 18),
                        )
                        remote_creds["http_status"] = int(r.status_code)
                        if r.status_code != 200:
                            remote_creds["error"] = "http_error"
                            remote_creds["error_detail"] = sanitize(r.text)[:240]
                            break
                        data = r.json() or []
                        m = {}
                        for row in data:
                            ip = sanitize(row.get("host") or "")
                            u = sanitize(row.get("username") or "")
                            p = sanitize(row.get("password") or "")
                            if not ip or not u:
                                continue
                            m.setdefault(ip, []).append({"user": u, "password": p})
                        creds_by_ip = m
                        remote_creds["fetched"] = True
                        remote_creds["ip_count"] = len(m.keys())
                        remote_creds["error"] = ""
                        remote_creds["error_detail"] = ""
                        break
                    except Exception as e:
                        last_exc = e
                        time.sleep(0.5)
                if (not remote_creds["fetched"]) and last_exc is not None:
                    remote_creds["error"] = "failed_to_fetch"
                    remote_creds["error_detail"] = sanitize(str(last_exc))[:240]
            except Exception as e:
                creds_by_ip = None
                remote_creds["error"] = "failed_to_fetch"
                remote_creds["error_detail"] = sanitize(str(e))[:240]

        cameras = discover_cameras(
            timeout=timeout,
            user=user,
            password=password,
            workers=int(env.get("CAMERA_SCAN_WORKERS") or 32),
            creds_by_ip=creds_by_ip,
            max_cred_tries=int(env.get("CAMERA_MAX_CRED_TRIES") or 2),
        )
        store.set_done(job_id, {"cameras": cameras, "count": len(cameras), "remote_creds": remote_creds})

        agent_id = sanitize(env.get("AGENT_ID") or os.getenv("COMPUTERNAME") or os.getenv("HOSTNAME") or "edge")
        client_id = sanitize(env.get("CLIENT_ID") or "")
        client_id_int = int(client_id) if client_id.isdigit() else None

        if _bool(env.get("CAMERA_DISCOVERY_AUTO_PUSH") or "1") and ingest_api_url and collector_key:
            _push_to_server(ingest_api_url, collector_key, agent_id, client_id_int, cameras)
    except Exception as e:
        store.set_error(job_id, str(e))


class Handler(BaseHTTPRequestHandler):
    server_version = "eti-sentinel-edge"

    def log_message(self, fmt: str, *args) -> None:
        try:
            msg = fmt % args if args else str(fmt)
            ip = ""
            try:
                ip = str(self.client_address[0])
            except Exception:
                ip = ""
            _append_log(self.server.log_path, f"http {ip} {msg}")
        except Exception:
            return

    def handle(self) -> None:
        try:
            return super().handle()
        except Exception:
            _append_log(self.server.log_path, traceback.format_exc())
            try:
                raw = json.dumps({"error": "internal_error"}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except Exception:
                pass
            return

    def _json(self, code: int, obj: Any) -> None:
        try:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            try:
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                return
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                return
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            try:
                _append_log(self.server.log_path, traceback.format_exc())
            except Exception:
                pass
            return

    def _read_json(self) -> Dict[str, Any]:
        try:
            n = int(self.headers.get("content-length") or "0")
        except Exception:
            n = 0
        if n <= 0:
            return {}
        try:
            raw = self.rfile.read(n)
            return json.loads(raw.decode("utf-8", errors="replace")) or {}
        except Exception:
            return {}

    def _authorized(self) -> bool:
        try:
            remote_ip = ""
            try:
                remote_ip = str(self.client_address[0])
            except Exception:
                remote_ip = ""
            if _is_loopback_ip(remote_ip):
                return True
            expected = sanitize(self.server.env.get("AGENT_API_KEY") or "")
            if not expected:
                return False
            key = sanitize(self.headers.get("x-agent-key") or "")
            auth = sanitize(self.headers.get("Authorization") or "")
            if auth.lower().startswith("bearer "):
                key = sanitize(auth.split(" ", 1)[1] or "")
            return key == expected
        except Exception:
            return False

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        try:
            raw = json.dumps({"error": "forbidden"}, ensure_ascii=False).encode("utf-8")
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except Exception:
            pass
        return False
        data = self.rfile.read(n)
        try:
            txt = data.decode("utf-8", errors="replace")
            if txt.startswith("\ufeff"):
                txt = txt.lstrip("\ufeff")
            return json.loads(txt)
        except Exception:
            return {}

    def do_GET(self) -> None:
        try:
            path = (self.path or "").split("?")[0]
            q = _parse_query(self.path or "")
            if path == "/" or path == "":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                
                # Coleta dados para o Dashboard Técnico
                relay_status = self.server.relay.status()
                
                # Busca o nome amigável do cliente (obtido via refresh_client_notify)
                client_name = "Não identificado"
                with self.server.relay._lock:
                    client_name = self.server.relay._client_notify.get("client_name") or "Carregando..."
                
                client_id = sanitize(self.server.env.get("CLIENT_ID") or "Não configurado")
                ingest_url = sanitize(self.server.env.get("INGEST_API_URL") or "Não configurado")
                gateway_ip = os.environ.get("INTERNAL_GATEWAY_IP", "Não detectado")
                
                # NOVO: Verifica se o Heartbeat está realmente chegando na Railway
                # Se o status.last_push_ok for recente, marcamos como Online
                from core.api_client import APIClient
                last_push_ts = relay_status.get("last_push_ok", 0)
                last_heartbeat_ts = APIClient.get_last_heartbeat()
                
                # Consideramos ONLINE se o Push de eventos OU o Heartbeat de saude funcionou nos ultimos 60s
                effective_last_push = max(last_push_ts, last_heartbeat_ts)
                is_cloud_online = (time.time() - effective_last_push) < 60 if effective_last_push > 0 else False
                
                def format_ts(ts):
                    if not ts: return "Nunca"
                    return time.strftime("%H:%M:%S", time.localtime(ts))

                last_push = format_ts(effective_last_push)
                last_event = format_ts(relay_status.get("last_event_ts"))
                
                # Coleta eventos recentes e deteccoes de IA para o dashboard
                events_all  = self.server.relay.events_recent(30)
                ai_events   = [e for e in events_all if (e.get("event_type") or "").startswith("ai_") and e.get("snapshot_jpg_b64")][:4]
                ev_feed     = [e for e in events_all if not (e.get("event_type") or "").startswith("ai_")][:8]
                queue_ok    = relay_status.get("queue_size", 0) == 0

                def sev_color(sev):
                    return {"warn": "#f59e0b", "error": "#ef4444", "critical": "#dc2626"}.get(str(sev or ""), "#22d3ee")

                def ev_icon(et):
                    et = str(et or "")
                    if "videoloss" in et: return "📷"
                    if "heartbeat" in et: return "💓"
                    if "online" in et:    return "🟢"
                    if "offline" in et:   return "🔴"
                    if "stream" in et:    return "📡"
                    return "🔔"

                def fmt_ts(ts):
                    if not ts: return "--"
                    try: return time.strftime("%d/%m %H:%M:%S", time.localtime(float(ts)))
                    except: return str(ts)

                ai_cards_html = ""
                for ai in ai_events:
                    et   = str(ai.get("event_type") or "")
                    desc = str(ai.get("description") or et)
                    snap = ai.get("snapshot_jpg_b64") or ""
                    ts   = fmt_ts(ai.get("timestamp") or ai.get("ts"))
                    ai_cards_html += f"""
                    <div class="ai-card">
                        <img src="data:image/jpeg;base64,{snap}" alt="deteccao" class="ai-img" onclick="openPhoto(this.src)"/>
                        <div class="ai-info">
                            <div class="ai-desc">{desc}</div>
                            <div class="ai-ts">{ts}</div>
                        </div>
                    </div>"""

                ev_rows_html = ""
                for ev in ev_feed:
                    et   = str(ev.get("event_type") or "")
                    desc = str(ev.get("description") or et)[:80]
                    ts   = fmt_ts(ev.get("timestamp") or ev.get("ts"))
                    sev  = str(ev.get("severity") or "info")
                    ev_rows_html += f"""
                    <div class="ev-row">
                        <span class="ev-icon">{ev_icon(et)}</span>
                        <span class="ev-desc">{desc}</span>
                        <span class="ev-ts">{ts}</span>
                        <span class="ev-dot" style="background:{sev_color(sev)}"></span>
                    </div>"""

                risk_snap  = self.server.relay._risk.snapshot()
                risk_score = risk_snap["score"]
                risk_label = risk_snap["label"]
                risk_color = risk_snap["color"]

                html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETI SENTINEL — Painel do Técnico</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:#060e1c;color:#e2eaf5;min-height:100vh}}
  /* HEADER */
  .hdr{{background:#0b1525;border-bottom:1px solid rgba(59,158,255,.12);padding:14px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:10}}
  .hdr-dot{{width:10px;height:10px;border-radius:50%;background:#00c9a7;box-shadow:0 0 10px #00c9a7;animation:pulse 2s infinite}}
  @keyframes pulse{{0%,100%{{opacity:.4}}50%{{opacity:1}}}}
  .hdr-title{{font-size:17px;font-weight:700;color:#3b9eff;letter-spacing:.5px}}
  .hdr-client{{font-size:13px;color:#00c9a7;font-weight:600;margin-left:auto}}
  .hdr-time{{font-size:12px;color:#475569;margin-left:16px}}
  /* LAYOUT */
  .page{{max-width:1100px;margin:0 auto;padding:20px 16px}}
  /* STAT CARDS */
  .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:20px}}
  .sc{{background:#0b1525;border:1px solid rgba(255,255,255,.05);border-radius:14px;padding:16px 20px}}
  .sc-label{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}}
  .sc-val{{font-size:22px;font-weight:700}}
  .ok{{color:#00c9a7}}.warn{{color:#f59e0b}}.err{{color:#ef4444}}.blue{{color:#3b9eff}}
  /* INFO TABLE */
  .card{{background:#0b1525;border:1px solid rgba(255,255,255,.05);border-radius:14px;padding:18px 20px;margin-bottom:20px}}
  .card-title{{font-size:13px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.6px;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
  .irow{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04)}}
  .irow:last-child{{border:none}}
  .ilabel{{color:#64748b;font-size:13px}}
  .ival{{font-size:13px;font-weight:600;color:#cbd5e1}}
  /* AI DETECTIONS */
  .ai-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}}
  .ai-card{{background:#0c1a2e;border:1px solid rgba(59,158,255,.12);border-radius:12px;overflow:hidden;transition:.2s}}
  .ai-card:hover{{border-color:#3b9eff;transform:translateY(-2px)}}
  .ai-img{{width:100%;height:130px;object-fit:cover;cursor:pointer;display:block}}
  .ai-info{{padding:10px 12px}}
  .ai-desc{{font-size:13px;font-weight:600;color:#e2eaf5;margin-bottom:4px}}
  .ai-ts{{font-size:11px;color:#475569}}
  .no-ai{{color:#334155;font-size:14px;text-align:center;padding:24px;width:100%}}
  /* EVENTS FEED */
  .ev-row{{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.04)}}
  .ev-row:last-child{{border:none}}
  .ev-icon{{font-size:16px;flex-shrink:0}}
  .ev-desc{{flex:1;font-size:13px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .ev-ts{{font-size:11px;color:#475569;flex-shrink:0}}
  .ev-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
  /* TWO COL */
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
  @media(max-width:700px){{.two-col{{grid-template-columns:1fr}}}}
  /* ACTIONS */
  .actions{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
  .btn{{background:#1e293b;color:#f8fafc;border:1px solid rgba(255,255,255,.1);border-radius:9px;padding:9px 18px;font-size:13px;font-weight:600;cursor:pointer;transition:.2s;text-decoration:none;display:inline-flex;align-items:center;gap:6px}}
  .btn:hover{{background:#3b9eff;border-color:#3b9eff;transform:translateY(-1px)}}
  .btn-green{{background:#065f46;border-color:#047857}}.btn-green:hover{{background:#047857}}
  .btn-red{{background:#7f1d1d;border-color:#991b1b}}.btn-red:hover{{background:#dc2626}}
  /* MODAL */
  .mo{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:100;align-items:center;justify-content:center;backdrop-filter:blur(4px)}}
  .mo-box{{background:#0b1525;border:1px solid rgba(59,158,255,.2);border-radius:16px;width:94%;max-width:780px;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.6)}}
  .mo-hdr{{padding:14px 20px;border-bottom:1px solid rgba(255,255,255,.06);display:flex;justify-content:space-between;align-items:center}}
  .mo-title{{font-weight:700;color:#3b9eff;font-size:14px;text-transform:uppercase}}
  .mo-x{{cursor:pointer;color:#64748b;font-size:26px;line-height:1}}
  .mo-body{{padding:20px;overflow-y:auto;flex:1}}
  .json-pre{{font-family:Consolas,monospace;font-size:12px;color:#00c9a7;white-space:pre-wrap;word-break:break-all}}
  .photo-modal img{{width:100%;border-radius:8px}}
  /* FOOTER */
  footer{{text-align:center;color:#334155;font-size:12px;padding:20px 0 30px}}
</style>
</head>
<body>
<div class="hdr">
  <div class="hdr-dot"></div>
  <div class="hdr-title">ETI SENTINEL EDGE</div>
  <div class="hdr-client">📍 {client_name}</div>
  <div class="hdr-time" id="clock"></div>
</div>

<!-- Modal genérico (JSON / foto) -->
<div id="modal" class="mo" onclick="if(event.target===this)closeModal()">
  <div class="mo-box">
    <div class="mo-hdr">
      <div id="mo-title" class="mo-title">—</div>
      <div class="mo-x" onclick="closeModal()">×</div>
    </div>
    <div id="mo-body" class="mo-body"></div>
  </div>
</div>

<div class="page">

  <!-- STATUS CARDS -->
  <div class="stats">
    <div class="sc">
      <div class="sc-label">☁ Conexão Cloud</div>
      <div class="sc-val {'ok' if is_cloud_online else 'warn'}">{'● Online' if is_cloud_online else '◌ Sincronizando'}</div>
    </div>
    <div class="sc">
      <div class="sc-label">📦 Fila de Envio</div>
      <div class="sc-val {'ok' if queue_ok else 'warn'}">{relay_status.get('queue_size',0)} {'pacotes' if relay_status.get('queue_size',0)!=1 else 'pacote'}</div>
    </div>
    <div class="sc">
      <div class="sc-label">🔔 Eventos Totais</div>
      <div class="sc-val blue">{relay_status.get('events_total',0)}</div>
    </div>
    <div class="sc">
      <div class="sc-label">⏱ Último Envio</div>
      <div class="sc-val" style="font-size:16px;color:#94a3b8">{last_push}</div>
    </div>
    <div class="sc">
      <div class="sc-label">🛡 Score de Risco</div>
      <div id="risk-score" class="sc-val" style="color:{risk_color}">{int(risk_score)}</div>
      <div id="risk-label" style="font-size:11px;font-weight:700;letter-spacing:.5px;color:{risk_color};margin-top:2px">{risk_label}</div>
    </div>
  </div>

  <!-- ÚLTIMAS DETECÇÕES DE IA -->
  <div class="card">
    <div class="card-title">🤖 Últimas Detecções de IA <span id="ai-badge" style="margin-left:auto;background:#1e3a5f;color:#60a5fa;font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600">auto-atualiza</span></div>
    <div id="ai-grid" class="ai-grid">
      {''.join([ai_cards_html]) if ai_cards_html else '<div class="no-ai">Nenhuma detecção com foto ainda. Passe em frente à câmera para testar.</div>'}
    </div>
  </div>

  <div class="two-col">
    <!-- INFORMAÇÕES DO SISTEMA -->
    <div class="card">
      <div class="card-title">⚙️ Sistema</div>
      <div class="irow"><span class="ilabel">Cliente</span><span class="ival" style="color:#00c9a7">{client_name}</span></div>
      <div class="irow"><span class="ilabel">ID do Cliente</span><span class="ival">{client_id}</span></div>
      <div class="irow"><span class="ilabel">IP Gateway</span><span class="ival" style="color:#3b9eff">{gateway_ip}</span></div>
      <div class="irow"><span class="ilabel">Servidor</span><span class="ival" style="font-size:11px">{ingest_url}</span></div>
      <div class="irow"><span class="ilabel">Último Evento</span><span class="ival">{last_event}</span></div>
    </div>

    <!-- FEED DE EVENTOS -->
    <div class="card">
      <div class="card-title">📋 Eventos Recentes</div>
      <div id="ev-feed">
        {''.join([ev_rows_html]) if ev_rows_html else '<div class="no-ai">Nenhum evento ainda.</div>'}
      </div>
    </div>
  </div>

  <!-- AÇÕES -->
  <div class="actions">
    <button class="btn btn-green" onclick="openModal('/api/status','📊 Status do Sistema',renderStatus)">📊 Status</button>
    <button class="btn" onclick="openModal('/api/events?limit=30','📋 Últimos 30 Eventos',renderEvents)">📋 Eventos</button>
    <button class="btn" onclick="openModal('/api/events?limit=20','🤖 Detecções de IA',renderAI)">🤖 IA / Câmeras</button>
    <button class="btn" onclick="openModal('/api/rules','⚡ Regras de Automação',renderRules)">⚡ Regras</button>
    <a href="{ingest_url.rstrip('/')}/health" target="_blank" class="btn">🌐 Servidor</a>
    <button class="btn btn-red" onclick="if(confirm('Recarregar dashboard?'))window.location.reload()">🔄 Recarregar</button>
  </div>

  <footer>&copy; 2026 ETI Tecnologies · Monitoramento Inteligente 24/7 · v2.0</footer>
</div>

<script>
// ---- Relógio ----
function tick(){{ document.getElementById('clock').textContent = new Date().toLocaleTimeString('pt-BR'); }}
tick(); setInterval(tick,1000);

// ---- Auto-refresh dos dados (sem reload de página) ----
async function refreshData(){{
  try{{
    const [evRes, aiRes, riskRes] = await Promise.all([
      fetch('/api/events?limit=8'),
      fetch('/api/events?limit=4&event_type=ai_'),
      fetch('/api/risk')
    ]);
    const evData = await evRes.json();
    const aiData = await aiRes.json();
    const riskData = await riskRes.json();
    const rsEl = document.getElementById('risk-score');
    const rlEl = document.getElementById('risk-label');
    if(rsEl && riskData.score!==undefined){{
      rsEl.textContent = Math.round(riskData.score);
      rsEl.style.color = riskData.color||'#00c9a7';
      if(rlEl){{ rlEl.textContent=riskData.label||'BAIXO'; rlEl.style.color=riskData.color||'#00c9a7'; }}
    }}

    // Atualiza feed de eventos
    const evFeed = document.getElementById('ev-feed');
    const icons = {{videoloss:'📷',heartbeat:'💓',online:'🟢',offline:'🔴',stream:'📡'}};
    const sevColors = {{warn:'#f59e0b',error:'#ef4444',critical:'#dc2626'}};
    const evHtml = (evData.events||[])
      .filter(e=>!((e.event_type||'').startsWith('ai_')))
      .slice(0,8)
      .map(e=>{{
        const icon = Object.keys(icons).find(k=>(e.event_type||'').includes(k))||'🔔';
        const dot = sevColors[e.severity]||'#22d3ee';
        const ts = e.timestamp ? new Date(e.timestamp*1000).toLocaleTimeString('pt-BR') : '--';
        const desc = (e.description||e.event_type||'').slice(0,70);
        return `<div class="ev-row"><span class="ev-icon">${{icons[Object.keys(icons).find(k=>(e.event_type||'').includes(k))||'🔔']||icon}}</span><span class="ev-desc">${{desc}}</span><span class="ev-ts">${{ts}}</span><span class="ev-dot" style="background:${{dot}}"></span></div>`;
      }}).join('') || '<div class="no-ai">Nenhum evento ainda.</div>';
    if(evFeed) evFeed.innerHTML = evHtml;

    // Atualiza detecções de IA
    const aiGrid = document.getElementById('ai-grid');
    const aiWithPhoto = (aiData.events||[]).filter(e=>e.snapshot_jpg_b64).slice(0,4);
    if(aiGrid && aiWithPhoto.length>0){{
      aiGrid.innerHTML = aiWithPhoto.map(e=>{{
        const ts = e.timestamp ? new Date(e.timestamp*1000).toLocaleString('pt-BR') : '--';
        const desc = (e.description||e.event_type||'').slice(0,60);
        return `<div class="ai-card"><img src="data:image/jpeg;base64,${{e.snapshot_jpg_b64}}" class="ai-img" onclick="openPhoto(this.src)" alt="deteccao"/><div class="ai-info"><div class="ai-desc">${{desc}}</div><div class="ai-ts">${{ts}}</div></div></div>`;
      }}).join('');
    }}
  }}catch(err){{console.warn('refresh error',err);}}
}}
setInterval(refreshData, 12000);

// ---- Helpers visuais ----
const SEV_COLOR = {{warn:'#f59e0b',error:'#ef4444',critical:'#dc2626',info:'#22d3ee',success:'#00c9a7'}};
const EV_ICON = {{videoloss:'📷',heartbeat:'💓',online:'🟢',offline:'🔴',stream:'📡',ai_:'🤖',gateway:'🔌',push:'📤'}};
function evIcon(et){{
  const k=Object.keys(EV_ICON).find(k=>(et||'').includes(k));
  return k?EV_ICON[k]:'🔔';
}}
function fmtTs(ts){{
  if(!ts)return'--';
  const d=new Date((typeof ts==='number'&&ts<1e12)?ts*1000:ts);
  return d.toLocaleString('pt-BR',{{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}});
}}
function pill(label,color){{
  return`<span style="background:${{color||'#1e3a5f'}};color:#f8fafc;font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px">${{label}}</span>`;
}}

// ---- Renderizador: Status do Sistema ----
function renderStatus(d){{
  const r=d.relay||{{}};
  const lastPush=r.last_push_ok?fmtTs(r.last_push_ok):'Nunca';
  const isOnline=r.last_push_ok&&(Date.now()/1000-r.last_push_ok)<60;
  return`
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
    <div style="background:#0d1f35;border-radius:12px;padding:14px;text-align:center">
      <div style="font-size:11px;color:#64748b;margin-bottom:6px">☁ CONEXÃO CLOUD</div>
      <div style="font-size:20px;font-weight:800;color:${{isOnline?'#00c9a7':'#f59e0b'}}">${{isOnline?'● Online':'◌ Verificando'}}</div>
    </div>
    <div style="background:#0d1f35;border-radius:12px;padding:14px;text-align:center">
      <div style="font-size:11px;color:#64748b;margin-bottom:6px">📦 FILA</div>
      <div style="font-size:20px;font-weight:800;color:${{(r.queue_size||0)===0?'#00c9a7':'#f59e0b'}}">${{r.queue_size||0}} pacotes</div>
    </div>
    <div style="background:#0d1f35;border-radius:12px;padding:14px;text-align:center">
      <div style="font-size:11px;color:#64748b;margin-bottom:6px">🔔 EVENTOS</div>
      <div style="font-size:20px;font-weight:800;color:#3b9eff">${{r.events_total||0}}</div>
    </div>
  </div>
  <div style="background:#0d1f35;border-radius:12px;overflow:hidden">
    ${{[
      ['Último envio para a nuvem', lastPush],
      ['ID do Cliente', r.client_id||'—'],
      ['Regras configuradas', (r.rules_count||0)+' regra(s)'],
      ['Notificações suprimidas', (r.notify_suppressed_total||0)+' evento(s)'],
    ].map(([l,v])=>`<div style="display:flex;justify-content:space-between;padding:11px 16px;border-bottom:1px solid rgba(255,255,255,.04)"><span style="color:#64748b;font-size:13px">${{l}}</span><span style="font-weight:700;font-size:13px;color:#cbd5e1">${{v}}</span></div>`).join('')}}
  </div>`;
}}

// ---- Renderizador: Lista de Eventos ----
function renderEvents(d){{
  const evs=d.events||[];
  if(!evs.length)return'<div style="text-align:center;padding:30px;color:#475569">Nenhum evento registrado ainda.</div>';
  return`<div style="display:flex;flex-direction:column;gap:6px">${{
    evs.map(e=>{{
      const et=e.event_type||'';
      const sev=String(e.severity||'info').toLowerCase();
      const col=SEV_COLOR[sev]||'#22d3ee';
      const desc=(e.description||et).slice(0,80);
      const ts=fmtTs(e.timestamp||e.ts||e.created_at);
      return`<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:#0d1f35;border-radius:10px;border-left:3px solid ${{col}}">
        <span style="font-size:18px;flex-shrink:0">${{evIcon(et)}}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:700;color:#e2eaf5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${{desc}}</div>
          <div style="font-size:11px;color:#475569;margin-top:2px">${{et}}</div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:11px;color:#475569">${{ts}}</div>
          ${{pill(sev.toUpperCase(),col)}}
        </div>
      </div>`;
    }}).join('')
  }}</div>`;
}}

// ---- Renderizador: Detecções de IA ----
function renderAI(d){{
  const evs=(d.events||[]).filter(e=>(e.event_type||'').startsWith('ai_'));
  if(!evs.length)return`<div style="text-align:center;padding:40px;color:#475569">
    <div style="font-size:40px;margin-bottom:12px">🤖</div>
    <div>Nenhuma detecção de IA registrada ainda.</div>
    <div style="font-size:12px;margin-top:8px">Passe em frente a uma câmera para testar.</div>
  </div>`;
  return`<div style="display:flex;flex-direction:column;gap:10px">${{
    evs.map(e=>{{
      const desc=e.description||e.event_type||'Detecção';
      const ts=fmtTs(e.timestamp||e.ts||e.created_at);
      const snap=e.snapshot_jpg_b64;
      return`<div style="background:#0d1f35;border-radius:12px;overflow:hidden;border:1px solid rgba(59,158,255,.15)">
        ${{snap?`<img src="data:image/jpeg;base64,${{snap}}" style="width:100%;max-height:220px;object-fit:cover;cursor:pointer" onclick="openPhoto(this.src)" />`:'<div style="background:#0a1628;height:60px;display:flex;align-items:center;justify-content:center;color:#334155;font-size:28px">🎥</div>'}}
        <div style="padding:10px 14px;display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:13px;font-weight:700;color:#e2eaf5">${{desc.slice(0,70)}}</span>
          <span style="font-size:11px;color:#475569;flex-shrink:0;margin-left:10px">${{ts}}</span>
        </div>
      </div>`;
    }}).join('')
  }}</div>`;
}}

// ---- Renderizador: Regras de Automação ----
function renderRules(d){{
  const rules=d.rules||[];
  if(!rules.length)return`<div style="text-align:center;padding:40px;color:#475569">
    <div style="font-size:40px;margin-bottom:12px">⚡</div>
    <div>Nenhuma regra de automação configurada.</div>
    <div style="font-size:12px;margin-top:8px">Configure regras no painel da Railway para automatizar alertas.</div>
  </div>`;
  return`<div style="display:flex;flex-direction:column;gap:8px">${{
    rules.map(r=>{{
      const cond=r.condition||r.trigger||'—';
      const action=r.action||r.notify||'—';
      const name=r.name||r.id||'Regra';
      return`<div style="background:#0d1f35;border-radius:12px;padding:14px 16px">
        <div style="font-size:14px;font-weight:800;color:#3b9eff;margin-bottom:8px">⚡ ${{name}}</div>
        <div style="font-size:12px;color:#64748b;margin-bottom:4px">SE</div>
        <div style="font-size:13px;color:#e2eaf5;margin-bottom:8px">${{JSON.stringify(cond)}}</div>
        <div style="font-size:12px;color:#64748b;margin-bottom:4px">ENTÃO</div>
        <div style="font-size:13px;color:#00c9a7">${{JSON.stringify(action)}}</div>
      </div>`;
    }}).join('')
  }}</div>`;
}}

// ---- Dispatcher: chama o renderizador certo para cada URL ----
async function openModal(url, title, renderer){{
  const mo=document.getElementById('modal');
  document.getElementById('mo-title').textContent=title;
  document.getElementById('mo-body').innerHTML='<div style="text-align:center;padding:40px;color:#475569"><div style="font-size:30px;animation:pulse 1s infinite">⏳</div><div style="margin-top:12px">Carregando...</div></div>';
  mo.style.display='flex';
  try{{
    const r=await fetch(url);
    const d=await r.json();
    document.getElementById('mo-body').innerHTML=renderer(d);
  }}catch(e){{
    document.getElementById('mo-body').innerHTML=`<div style="text-align:center;padding:30px;color:#ef4444">❌ Erro ao carregar dados:<br><small>${{e}}</small></div>`;
  }}
}}

// ---- Modal Foto em tela cheia ----
function openPhoto(src){{
  document.getElementById('mo-title').textContent='📸 Foto da Detecção';
  document.getElementById('mo-body').innerHTML=`<img src="${{src}}" style="width:100%;border-radius:8px;display:block"/>`;
  document.getElementById('modal').style.display='flex';
}}

function closeModal(){{ document.getElementById('modal').style.display='none'; }}
</script>
</body>
</html>"""
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
                return
            if path == "/health":
                return self._json(200, {"ok": True})
            if not self._require_auth():
                return
            if path == "/api/status":
                return self._json(200, {"ok": True, "relay": self.server.relay.status()})
            if path == "/api/rules":
                return self._json(200, {"ok": True, "rules": self.server.relay.rules_summary()})
            if path == "/api/events":
                try:
                    lim = int(q.get("limit") or 50)
                except Exception:
                    lim = 50
                pfx = sanitize(q.get("prefix") or "")
                src = sanitize(q.get("source") or "")
                et = sanitize(q.get("event_type") or "")
                return self._json(200, {"ok": True, "events": self.server.relay.events_recent(lim, prefix=pfx, source=src, event_type=et)})
            if path == "/api/risk":
                return self._json(200, {"ok": True, **self.server.relay._risk.snapshot()})
            if path == "/api/recordings/list":
                base_dir = Path(sanitize(self.server.env.get("RECORD_BASE_DIR") or str(Path(__file__).resolve().parent / ".recordings"))).resolve()
                device_id = sanitize(q.get("device_id") or "")
                channel = sanitize(q.get("channel") or "")
                if not device_id.isdigit() or not channel.isdigit():
                    return self._json(400, {"error": "device_id_and_channel_required"})
                ddir = (base_dir / f"device_{int(device_id)}" / f"ch_{int(channel)}").resolve()
                if not str(ddir).startswith(str(base_dir)):
                    return self._json(400, {"error": "invalid_path"})
                if not ddir.exists():
                    return self._json(200, {"ok": True, "files": []})
                out = []
                for p in sorted(ddir.rglob("*.mp4"), reverse=True):
                    try:
                        rel = str(p.relative_to(ddir)).replace("\\", "/")
                        out.append({"rel": rel, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime)})
                        if len(out) >= 200:
                            break
                    except Exception:
                        continue
                return self._json(200, {"ok": True, "base": str(ddir), "files": out})
            if path == "/api/recordings/get":
                base_dir = Path(sanitize(self.server.env.get("RECORD_BASE_DIR") or str(Path(__file__).resolve().parent / ".recordings"))).resolve()
                device_id = sanitize(q.get("device_id") or "")
                channel = sanitize(q.get("channel") or "")
                rel = sanitize(q.get("rel") or "").replace("\\", "/")
                if not device_id.isdigit() or not channel.isdigit() or not rel:
                    return self._json(400, {"error": "device_id_channel_rel_required"})
                if ".." in rel or rel.startswith("/"):
                    return self._json(400, {"error": "invalid_rel"})
                ddir = (base_dir / f"device_{int(device_id)}" / f"ch_{int(channel)}").resolve()
                fp = (ddir / rel).resolve()
                if not str(fp).startswith(str(ddir)) or not str(ddir).startswith(str(base_dir)):
                    return self._json(400, {"error": "invalid_path"})
                if not fp.exists() or not fp.is_file():
                    return self._json(404, {"error": "not_found"})
                try:
                    data = fp.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception:
                    return self._json(500, {"error": "read_failed"})
            if path == "/api/discover/cameras":
                job = self.server.store.latest()
                if not job:
                    return self._json(200, {"status": "idle", "cameras": [], "count": 0})
                st = job.get("status")
                if st == "running":
                    return self._json(200, {"status": "running", "job_id": job.get("job_id")})
                if st == "error":
                    return self._json(200, {"status": "error", "job_id": job.get("job_id"), "error": job.get("error")})
                res = job.get("result") or {}
                return self._json(200, {"status": "done", "job_id": job.get("job_id"), **res})

            if path.startswith("/api/discover/cameras/"):
                jid = sanitize(path.rsplit("/", 1)[-1])
                job = self.server.store.get(jid)
                if not job:
                    return self._json(404, {"error": "not_found"})
                st = job.get("status")
                if st == "running":
                    return self._json(200, {"status": "running", "job_id": jid})
                if st == "error":
                    return self._json(200, {"status": "error", "job_id": jid, "error": job.get("error")})
                res = job.get("result") or {}
                return self._json(200, {"status": "done", "job_id": jid, **res})

            return self._json(404, {"error": "not_found"})
        except Exception as e:
            _append_log(self.server.log_path, traceback.format_exc())
            try:
                return self._json(500, {"error": "internal_error", "detail": sanitize(str(e))})
            except Exception:
                return

    def do_POST(self) -> None:
        try:
            path = (self.path or "").split("?")[0]
            if not self._require_auth():
                return
            if path == "/api/push":
                body = self._read_json()
                source = sanitize(self.headers.get("x-event-source") or body.get("source") or "edge")
                if not isinstance(body, dict) or not sanitize(body.get("token") or ""):
                    return self._json(400, {"error": "token_required"})
                res = self.server.relay.handle_event(body, source)
                return self._json(200, res)
            if path == "/api/discover/cameras/scan":
                body = self._read_json()
                user = sanitize(body.get("user") or os.getenv("CAMERA_DEFAULT_USER") or "admin")
                password = sanitize(body.get("password") or os.getenv("CAMERA_DEFAULT_PASS") or "")
                timeout = body.get("timeout")
                try:
                    timeout_f = float(timeout) if timeout is not None else float(os.getenv("CAMERA_SCAN_TIMEOUT") or 6)
                except Exception:
                    timeout_f = 6.0

                jid = self.server.store.create()
                t = threading.Thread(
                    target=_run_scan,
                    args=(jid, self.server.store, self.server.env, user, password, timeout_f),
                    daemon=True,
                )
                t.start()
                return self._json(200, {"job_id": jid, "status": "running"})
            return self._json(404, {"error": "not_found"})
        except Exception as e:
            _append_log(self.server.log_path, traceback.format_exc())
            try:
                return self._json(500, {"error": "internal_error", "detail": sanitize(str(e))})
            except Exception:
                return


class Server(ThreadingHTTPServer):
    def __init__(self, addr, handler_cls, env, store, log_path: Path):
        super().__init__(addr, handler_cls)
        self.env = env
        self.store = store
        self.log_path = log_path
        self.relay = PushRelay(Path(__file__).resolve().parent, env, log_path)


def main() -> None:
    import argparse

    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env", override=True)
    env = os.environ.copy()

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--bind", default=None)
    parser.add_argument("--port", default=None)
    args = parser.parse_args()

    bind = sanitize(args.bind) if args.bind is not None else sanitize(env.get("AGENT_API_BIND") or "127.0.0.1")
    port = int(args.port) if args.port is not None else int(env.get("AGENT_API_PORT") or 8808)
    store = JobStore(here / ".state" / "agent_api.json")
    log_path = here / ".state" / "agent_api.log"

    httpd = Server((bind, port), Handler, env, store, log_path)
    httpd.relay.start()
    httpd.serve_forever()


if __name__ == "__main__":
    main()
