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

    def start(self) -> None:
        threading.Thread(target=self._loop_refresh, daemon=True).start()
        threading.Thread(target=self._loop_flush, daemon=True).start()
        threading.Thread(target=self._loop_state, daemon=True).start()

    def stop(self) -> None:
        self._stop = True

    def status(self) -> Dict[str, Any]:
        with self._lock:
            q = self._queue_size()
            return {
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

        if et == "edge_heartbeat":
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
        
        # GARANTIA MULTITENANT: Força o client_id do agente antes de enviar para a nuvem
        cid = self._client_id()
        safe_payload = dict(payload or {})
        if cid:
            try:
                safe_payload["client_id"] = int(cid)
            except:
                pass
        
        safe_payload.pop("snapshot_jpg_b64", None)
        try:
            r = self._sess.post(
                url + "/push",
                json=safe_payload,
                headers={"x-event-source": sanitize(source or "edge")},
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
                client_id = sanitize(self.server.env.get("CLIENT_ID") or "Não configurado")
                ingest_url = sanitize(self.server.env.get("INGEST_API_URL") or "Não configurado")
                gateway_ip = os.environ.get("INTERNAL_GATEWAY_IP", "Não detectado")
                
                # Formata timestamps para leitura humana
                def format_ts(ts):
                    if not ts: return "Nunca"
                    return time.strftime("%H:%M:%S", time.localtime(ts))

                last_push = format_ts(relay_status.get("last_push_ok"))
                last_event = format_ts(relay_status.get("last_event_ts"))
                
                html = f"""
                <!DOCTYPE html>
                <html lang="pt-br">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>ETI SENTINEL - Dashboard do Técnico</title>
                    <style>
                        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #070d18; color: #e2eaf5; margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; min-height: 100vh; }}
                        .container {{ max-width: 800px; width: 100%; }}
                        .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; background: #0b1525; padding: 20px; border-radius: 16px; border: 1px solid rgba(59, 158, 255, 0.1); }}
                        .logo-area {{ display: flex; align-items: center; gap: 15px; }}
                        .logo-dot {{ width: 12px; height: 12px; background: #00c9a7; border-radius: 50%; box-shadow: 0 0 15px #00c9a7; animation: pulse 2s infinite; }}
                        @keyframes pulse {{ 0% {{ opacity: 0.4; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0.4; }} }}
                        h1 {{ margin: 0; font-size: 20px; letter-spacing: 1px; color: #3b9eff; }}
                        
                        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin-bottom: 24px; }}
                        .stat-card {{ background: #0b1525; padding: 20px; border-radius: 16px; border: 1px solid rgba(59, 158, 255, 0.05); }}
                        .stat-label {{ color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
                        .stat-value {{ font-size: 20px; font-weight: bold; color: #f8fafc; }}
                        .stat-value.ok {{ color: #00c9a7; }}
                        .stat-value.warn {{ color: #fbbf24; }}
                        
                        .info-table {{ background: #0b1525; border-radius: 16px; padding: 20px; border: 1px solid rgba(59, 158, 255, 0.05); margin-bottom: 24px; }}
                        .info-row {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
                        .info-row:last-child {{ border-bottom: none; }}
                        .info-label {{ color: #64748b; }}
                        .info-val {{ font-weight: 500; color: #cbd5e1; }}
                        
                        .actions {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }}
                        .btn {{ background: #1e293b; color: #f8fafc; text-decoration: none; padding: 10px 20px; border-radius: 8px; font-weight: 600; font-size: 14px; transition: all 0.2s; border: 1px solid rgba(255,255,255,0.1); }}
                        .btn:hover {{ background: #3b9eff; border-color: #3b9eff; transform: translateY(-2px); }}
                        .btn-primary {{ background: #3b9eff; border-color: #3b9eff; }}
                        
                        .footer {{ margin-top: auto; padding: 40px 0 20px; color: #3a5c7a; font-size: 12px; text-align: center; }}
                    </style>
                    <script>
                        setTimeout(() => window.location.reload(), 15000);
                    </script>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <div class="logo-area">
                                <div class="logo-dot"></div>
                                <h1>ETI SENTINEL EDGE</h1>
                            </div>
                            <div style="font-size: 12px; color: #64748b;">v1.0.5-tecnico</div>
                        </div>

                        <div class="grid">
                            <div class="stat-card">
                                <div class="stat-label">Conexão Cloud</div>
                                <div class="stat-value {'ok' if relay_status.get('last_push_ok') else 'warn'}">
                                    {'Online' if (time.time() - relay_status.get('last_push_ok', 0)) < 60 else 'Sincronizando...'}
                                </div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-label">Eventos Totais</div>
                                <div class="stat-value">{relay_status.get('events_total', 0)}</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-label">Fila de Envio</div>
                                <div class="stat-value {'' if relay_status.get('queue_size', 0) == 0 else 'warn'}">
                                    {relay_status.get('queue_size', 0)} pacotes
                                </div>
                            </div>
                        </div>

                        <div class="info-table">
                            <div class="info-row">
                                <div class="info-label">Identificador do Cliente</div>
                                <div class="info-val">{client_id}</div>
                            </div>
                            <div class="info-row">
                                <div class="info-label">IP Gateway (Máquina)</div>
                                <div class="info-val" style="color: #3b9eff; font-weight: 800;">{gateway_ip}</div>
                            </div>
                            <div class="info-row">
                                <div class="info-label">Último Envio Cloud</div>
                                <div class="info-val">{last_push}</div>
                            </div>
                            <div class="info-row">
                                <div class="info-label">Último Evento Local</div>
                                <div class="info-val">{last_event}</div>
                            </div>
                            <div class="info-row">
                                <div class="info-label">Servidor Ingestão</div>
                                <div class="info-val">{ingest_url}</div>
                            </div>
                        </div>

                        <div class="actions">
                            <a href="/api/status" class="btn">JSON Status</a>
                            <a href="/api/events?limit=20" class="btn">Logs Recentes</a>
                            <a href="/api/rules" class="btn">Regras Ativas</a>
                            <a href="https://eti-sentinel.com" target="_blank" class="btn btn-primary">Painel Cloud</a>
                        </div>

                        <div class="footer">
                            &copy; 2026 ETI Tecnologies - Monitoramento Inteligente 24/7
                        </div>
                    </div>
                </body>
                </html>
                """
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
