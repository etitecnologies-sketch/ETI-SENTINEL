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
        cameras = discover_cameras(timeout=timeout, user=user, password=password, workers=int(env.get("CAMERA_SCAN_WORKERS") or 32))
        store.set_done(job_id, {"cameras": cameras, "count": len(cameras)})

        ingest_api_url = _sanitize_base_url(env.get("INGEST_API_URL") or "")
        collector_key = sanitize(env.get("COLLECTOR_KEY") or "")
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
            if path == "/health":
                return self._json(200, {"ok": True})
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
    httpd.serve_forever()


if __name__ == "__main__":
    main()
