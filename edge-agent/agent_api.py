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
from edge_notify import send_telegram, send_whatsapp_twilio
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


class PushRelay:
    def __init__(self, here: Path, env: Dict[str, str], log_path: Path):
        self.here = here
        self.env = env
        self.log_path = log_path
        self._lock = threading.Lock()
        self._client_notify: Dict[str, str] = {}
        self._rules: list = []
        self._last_cfg_ts = 0.0
        self._last_rules_ts = 0.0
        self._last_push_ok = 0.0
        self._queue_path = here / ".state" / "push_queue.jsonl"
        self._engine = RuleEngine()
        self._stop = False
        self._sess = requests.Session()

    def start(self) -> None:
        threading.Thread(target=self._loop_refresh, daemon=True).start()
        threading.Thread(target=self._loop_flush, daemon=True).start()

    def stop(self) -> None:
        self._stop = True

    def status(self) -> Dict[str, Any]:
        with self._lock:
            q = self._queue_size()
            return {
                "client_id": sanitize(self.env.get("CLIENT_ID") or ""),
                "last_client_notify_fetch": self._last_cfg_ts,
                "last_rules_fetch": self._last_rules_ts,
                "last_push_ok": self._last_push_ok,
                "queue_size": q,
                "rules_count": len(self._rules or []),
            }

    def rules_summary(self) -> Any:
        with self._lock:
            return [{"id": r.get("id"), "name": r.get("name"), "enabled": r.get("enabled")} for r in (self._rules or [])]

    def handle_event(self, payload: Dict[str, Any], source: str) -> Dict[str, Any]:
        ev = {
            "event_type": sanitize(payload.get("event_type") or ""),
            "channel": int(payload.get("channel") or 0) if str(payload.get("channel") or "").isdigit() else 0,
            "severity": sanitize(payload.get("severity") or "info"),
            "description": sanitize(payload.get("description") or ""),
            "device_id": int(payload.get("device_id") or 0) if str(payload.get("device_id") or "").isdigit() else None,
            "source": sanitize(source or payload.get("source") or "edge"),
        }
        self._engine.push_event(ev)

        with self._lock:
            rules = list(self._rules or [])
            cfg = dict(self._client_notify or {})

        fired = self._engine.eval(rules)
        fired_count = 0
        if fired:
            for rule_row, matched in fired:
                rule = rule_row.get("rule") or {}
                actions = rule.get("actions") or []
                msg = build_message(rule_row, matched)
                for a in actions:
                    if not isinstance(a, dict):
                        continue
                    if sanitize(a.get("type") or "") != "notify":
                        continue
                    chans = a.get("channels") or ["telegram", "whatsapp"]
                    if not isinstance(chans, list):
                        chans = [str(chans)]
                    if "telegram" in chans:
                        send_telegram(msg, cfg.get("telegram_token") or "", cfg.get("telegram_chat_id") or "", log=_bool(self.env.get("EDGE_NOTIFY_LOG") or "0"))
                    if "whatsapp" in chans:
                        send_whatsapp_twilio(
                            msg,
                            cfg.get("wa_instance") or "",
                            cfg.get("wa_token") or "",
                            cfg.get("wa_number") or "",
                            from_number=sanitize(self.env.get("TWILIO_WHATSAPP_NUMBER") or ""),
                            content_sid=sanitize(self.env.get("TWILIO_CONTENT_SID") or ""),
                            log=_bool(self.env.get("EDGE_NOTIFY_LOG") or "0"),
                        )
                fired_count += 1

        forwarded = self._forward_push(payload, source)
        return {"ok": True, "forwarded": forwarded, "rules_fired": fired_count}

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
                self._refresh_rules()
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
        try:
            r = self._sess.post(
                url + "/push",
                json=payload,
                headers={"x-event-source": sanitize(source or "edge")},
                timeout=(5, 12),
            )
            ok = r.status_code == 200
            if ok:
                with self._lock:
                    self._last_push_ok = time.time()
            return ok
        except Exception:
            self._enqueue(payload, source)
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
        keep = []
        for it in items:
            payload = it.get("payload") if isinstance(it, dict) else None
            src = it.get("source") if isinstance(it, dict) else ""
            if not isinstance(payload, dict):
                continue
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
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        try:
            n = int(self.headers.get("content-length") or "0")
        except Exception:
            n = 0
        if n <= 0:
            return {}
        data = self.rfile.read(n)
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self) -> None:
        try:
            path = (self.path or "").split("?")[0]
            q = _parse_query(self.path or "")
            if path == "/health":
                return self._json(200, {"ok": True})
            if path == "/api/status":
                return self._json(200, {"ok": True, "relay": self.server.relay.status()})
            if path == "/api/rules":
                return self._json(200, {"ok": True, "rules": self.server.relay.rules_summary()})
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
    load_dotenv(here / ".env")
    env = os.environ.copy()

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--bind", default=None)
    parser.add_argument("--port", default=None)
    args = parser.parse_args()

    bind = sanitize(args.bind) if args.bind is not None else sanitize(env.get("AGENT_API_BIND") or "0.0.0.0")
    port = int(args.port) if args.port is not None else int(env.get("AGENT_API_PORT") or 8808)
    store = JobStore(here / ".state" / "agent_api.json")
    log_path = here / ".state" / "agent_api.log"

    httpd = Server((bind, port), Handler, env, store, log_path)
    httpd.relay.start()
    httpd.serve_forever()


if __name__ == "__main__":
    main()
