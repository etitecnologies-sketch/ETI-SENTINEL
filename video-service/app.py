import json
import os
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _sanitize(s: Any) -> str:
    v = str(s or "").strip()
    v = v.replace("`", "")
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v


def _normalize_base_url(raw: str, default: str) -> str:
    s = _sanitize(raw)
    if not s:
        return default
    if s.startswith("http://") or s.startswith("https://"):
        return s.rstrip("/")
    return ("https://" + s).rstrip("/")


INGEST_API_URL = _normalize_base_url(os.getenv("INGEST_API_URL") or "", "http://localhost:3000")
COLLECTOR_KEY = _sanitize(os.getenv("COLLECTOR_KEY") or "")
ADMIN_TOKEN = _sanitize(os.getenv("ADMIN_TOKEN") or "")
CLIENT_ID = os.getenv("CLIENT_ID")

DISCOVERY_INTERVAL_SECONDS = _env_int("DISCOVERY_INTERVAL_SECONDS", 0)
DISCOVERY_TIMEOUT_SECONDS = _env_int("DISCOVERY_TIMEOUT_SECONDS", 3)

HEALTH_INTERVAL_SECONDS = _env_int("HEALTH_INTERVAL_SECONDS", 0)
DEFAULT_TIMEOUT_SECONDS = _env_int("DEFAULT_TIMEOUT_SECONDS", 8)

HLS_DIR = Path(os.getenv("HLS_DIR") or "/tmp/eti-sentinel-hls")
HLS_SEG_TIME = _env_int("HLS_SEG_TIME", 2)
HLS_LIST_SIZE = _env_int("HLS_LIST_SIZE", 6)


def _api_headers() -> Dict[str, str]:
    h: Dict[str, str] = {"Content-Type": "application/json"}
    if ADMIN_TOKEN:
        h["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    return h


def _collector_headers() -> Dict[str, str]:
    return {"x-collector-key": COLLECTOR_KEY}


def _post_push(token: str, event_type: str, channel: int, description: str, severity: str, payload: Optional[Dict[str, Any]] = None) -> None:
    url = INGEST_API_URL.rstrip("/") + "/push"
    body: Dict[str, Any] = {
        "token": token,
        "event_type": event_type,
        "channel": channel,
        "severity": severity,
        "description": description,
        "source": "video-service",
    }
    if payload:
        body.update(payload)
    requests.post(url, json=body, headers={"x-event-source": "video-service"}, timeout=10)


def _get_devices() -> List[Dict[str, Any]]:
    url = INGEST_API_URL.rstrip("/") + "/devices"
    try:
        r = requests.get(url, headers=_api_headers(), timeout=15)
        r.raise_for_status()
        return r.json() or []
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch devices: {e}")


def _create_camera_device(ip: str, xaddr: str) -> Optional[Dict[str, Any]]:
    if not ADMIN_TOKEN:
        return None
    url = INGEST_API_URL.rstrip("/") + "/devices"
    name = f"camera-{ip.replace('.', '-') }"
    body: Dict[str, Any] = {
        "name": name,
        "device_type": "camera",
        "ip_address": ip,
        "location": "",
        "description": "Descoberta ONVIF",
        "monitor_ping": True,
        "monitor_agent": False,
        "monitor_snmp": False,
        "notes": xaddr,
        "tags": ["camera", "onvif"],
    }
    if CLIENT_ID and str(CLIENT_ID).isdigit():
        body["client_id"] = int(CLIENT_ID)
    try:
        r = requests.post(url, headers=_api_headers(), json=body, timeout=15)
        if r.status_code >= 400:
            return None
        return r.json()
    except requests.RequestException:
        return None


def _probe_ws_discovery(timeout_seconds: int) -> List[Dict[str, Any]]:
    msg_id = f"uuid:{uuid.uuid4()}"
    probe = f"""<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>{msg_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>""".encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.4)
    try:
        sock.sendto(probe, ("239.255.255.250", 3702))
    except Exception:
        sock.close()
        return []

    found: Dict[str, Dict[str, Any]] = {}
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except Exception:
            break
        ip = addr[0]
        text = data.decode("utf-8", errors="ignore")
        xaddrs = ""
        if "XAddrs" in text:
            try:
                start = text.index("<XAddrs>") + len("<XAddrs>")
                end = text.index("</XAddrs>")
                xaddrs = text[start:end].strip()
            except Exception:
                xaddrs = ""
        if not xaddrs:
            continue
        found[ip] = {"ip": ip, "xaddrs": xaddrs}

    sock.close()
    return list(found.values())


def _fetch_rtsp_configs(client_id: Optional[int]) -> List[Dict[str, Any]]:
    url = INGEST_API_URL.rstrip("/") + "/collector/rtsp-config"
    params: Dict[str, Any] = {}
    if client_id:
        params["client_id"] = client_id
    try:
        r = requests.get(url, headers=_collector_headers(), params=params, timeout=15)
        if r.status_code != 200:
            body = (r.text or "").strip()
            if len(body) > 400:
                body = body[:400] + "…"
            if r.status_code == 401:
                raise HTTPException(status_code=401, detail=f"Unauthorized (COLLECTOR_KEY inválido). ingest-api respondeu: {body}")
            if r.status_code == 503:
                raise HTTPException(status_code=503, detail=f"Collector key não configurado no ingest-api. ingest-api respondeu: {body}")
            raise HTTPException(status_code=502, detail=f"ingest-api respondeu {r.status_code} em /collector/rtsp-config: {body}")
        return r.json() or []
    except HTTPException:
        raise
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch rtsp-config ({url}): {e}")


def _build_rtsp_url(url: str, username: str, password: str) -> str:
    u = url
    if "{username}" in u or "{password}" in u:
        return u.replace("{username}", username).replace("{password}", password)
    return u


def _probe_stream(url: str, transport: str, timeout_seconds: int) -> Tuple[bool, str]:
    timeout_us = max(1, int(timeout_seconds)) * 1_000_000
    t = (transport or "tcp").lower()
    if t not in {"tcp", "udp"}:
        t = "tcp"
    args = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        t,
        "-stimeout",
        str(timeout_us),
        "-i",
        url,
        "-an",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=max(3, timeout_seconds + 3))
        if p.returncode == 0:
            return True, ""
        err = (p.stderr or p.stdout or "").strip()
        return False, err[:400]
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError:
        return False, "ffmpeg_not_found"
    except Exception as e:
        return False, str(e)[:400]


class HlsProcess:
    def __init__(self, device_id: int, channel: int, rtsp_url: str, transport: str) -> None:
        self.device_id = device_id
        self.channel = channel
        self.rtsp_url = rtsp_url
        self.transport = transport
        self.started_at = time.time()
        self.proc: Optional[subprocess.Popen] = None
        self.output_dir = HLS_DIR / str(device_id) / str(channel)

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        playlist = str(self.output_dir / "index.m3u8")
        seg = str(self.output_dir / "seg_%05d.ts")
        t = (self.transport or "tcp").lower()
        if t not in {"tcp", "udp"}:
            t = "tcp"
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            t,
            "-i",
            self.rtsp_url,
            "-an",
            "-c:v",
            "copy",
            "-f",
            "hls",
            "-hls_time",
            str(max(1, HLS_SEG_TIME)),
            "-hls_list_size",
            str(max(2, HLS_LIST_SIZE)),
            "-hls_flags",
            "delete_segments+append_list",
            "-hls_segment_filename",
            seg,
            playlist,
        ]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


app = FastAPI(title="ETI SENTINEL Video Service", version="0.1.0")

_hls_lock = threading.Lock()
_hls: Dict[Tuple[int, int], HlsProcess] = {}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "ingest_api": INGEST_API_URL,
        "collector_key_configured": bool(COLLECTOR_KEY),
        "admin_token_configured": bool(ADMIN_TOKEN),
    }


@app.get("/discover")
def discover(run_register: bool = False) -> Dict[str, Any]:
    cams = _probe_ws_discovery(DISCOVERY_TIMEOUT_SECONDS)
    created = 0
    skipped = 0
    if run_register and ADMIN_TOKEN:
        try:
            existing = _get_devices()
        except Exception:
            existing = []
        existing_ips = {str(d.get("ip_address") or "").strip(): d for d in existing}
        for c in cams:
            ip = str(c.get("ip") or "").strip()
            xaddrs = str(c.get("xaddrs") or "").strip()
            if not ip:
                continue
            if ip in existing_ips:
                skipped += 1
                continue
            dev = _create_camera_device(ip, xaddrs)
            if not dev:
                continue
            created += 1
            token = dev.get("token")
            if token:
                _post_push(
                    str(token),
                    "camera_discovered",
                    0,
                    f"Câmera ONVIF encontrada em {ip}",
                    "info",
                    {"xaddrs": xaddrs, "ip": ip},
                )
    return {"count": len(cams), "cameras": cams, "registered": created, "skipped": skipped}


@app.get("/streams")
def streams() -> Dict[str, Any]:
    if not COLLECTOR_KEY:
        raise HTTPException(status_code=503, detail="COLLECTOR_KEY not configured")
    cid = int(CLIENT_ID) if CLIENT_ID and str(CLIENT_ID).isdigit() else None
    cfgs = _fetch_rtsp_configs(cid)
    out: List[Dict[str, Any]] = []
    for cfg in cfgs:
        device_id = int(cfg.get("device_id") or 0)
        token = _sanitize(cfg.get("token"))
        name = _sanitize(cfg.get("name"))
        username = _sanitize(cfg.get("username"))
        password = _sanitize(cfg.get("password"))
        streams = cfg.get("streams") or []
        if not device_id or not token or not isinstance(streams, list):
            continue
        for s in streams:
            if not s or s.get("enabled") is False:
                continue
            channel = int(s.get("channel") or 0)
            url = _sanitize(s.get("url"))
            if not url:
                continue
            out.append(
                {
                    "device_id": device_id,
                    "device_name": name,
                    "token": token,
                    "channel": channel,
                    "name": _sanitize(s.get("name")) or (f"Canal {channel}" if channel else "Stream"),
                    "url": _build_rtsp_url(url, username, password),
                    "transport": _sanitize(s.get("transport") or "tcp"),
                    "timeout_seconds": int(s.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
                }
            )
    return {"count": len(out), "streams": out}


def _ensure_hls(device_id: int, channel: int) -> HlsProcess:
    if not COLLECTOR_KEY:
        raise HTTPException(status_code=503, detail="COLLECTOR_KEY not configured")

    key = (device_id, channel)
    with _hls_lock:
        if key in _hls and _hls[key].is_running():
            return _hls[key]

    cid = int(CLIENT_ID) if CLIENT_ID and str(CLIENT_ID).isdigit() else None
    cfgs = _fetch_rtsp_configs(cid)
    chosen: Optional[Dict[str, Any]] = None
    for cfg in cfgs:
        if int(cfg.get("device_id") or 0) != device_id:
            continue
        username = _sanitize(cfg.get("username"))
        password = _sanitize(cfg.get("password"))
        streams = cfg.get("streams") or []
        if not isinstance(streams, list):
            continue
        for s in streams:
            if not s or s.get("enabled") is False:
                continue
            if int(s.get("channel") or 0) != channel:
                continue
            url = _sanitize(s.get("url"))
            if not url:
                continue
            chosen = {
                "url": _build_rtsp_url(url, username, password),
                "transport": _sanitize(s.get("transport") or "tcp"),
            }
            break
        if chosen:
            break

    if not chosen:
        raise HTTPException(status_code=404, detail="Stream not found")

    proc = HlsProcess(device_id=device_id, channel=channel, rtsp_url=chosen["url"], transport=chosen["transport"])
    proc.start()
    with _hls_lock:
        _hls[key] = proc
    return proc


@app.get("/hls/{device_id}/{channel}/index.m3u8")
def hls_playlist(device_id: int, channel: int) -> Response:
    proc = _ensure_hls(device_id, channel)
    playlist = proc.output_dir / "index.m3u8"
    for _ in range(20):
        if playlist.exists() and playlist.stat().st_size > 0:
            break
        time.sleep(0.2)
    if not playlist.exists():
        raise HTTPException(status_code=502, detail="HLS not ready")
    return FileResponse(str(playlist), media_type="application/vnd.apple.mpegurl")


@app.get("/hls/{device_id}/{channel}/{filename}")
def hls_file(device_id: int, channel: int, filename: str) -> Response:
    proc = _ensure_hls(device_id, channel)
    p = (proc.output_dir / filename).resolve()
    if not str(p).startswith(str(proc.output_dir.resolve())):
        raise HTTPException(status_code=404, detail="Not found")
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if filename.endswith(".ts"):
        return FileResponse(str(p), media_type="video/MP2T")
    if filename.endswith(".m3u8"):
        return FileResponse(str(p), media_type="application/vnd.apple.mpegurl")
    return FileResponse(str(p))


def _health_loop() -> None:
    if not COLLECTOR_KEY or HEALTH_INTERVAL_SECONDS <= 0:
        return
    cid = int(CLIENT_ID) if CLIENT_ID and str(CLIENT_ID).isdigit() else None
    next_run: Dict[Tuple[int, int, str], float] = {}
    last_ok: Dict[Tuple[int, int, str], Optional[bool]] = {}
    while True:
        try:
            configs = _fetch_rtsp_configs(cid)
        except Exception:
            time.sleep(5)
            continue
        now = time.time()
        seen = set()
        for cfg in configs:
            device_id = int(cfg.get("device_id") or 0)
            token = _sanitize(cfg.get("token"))
            name = _sanitize(cfg.get("name")) or f"device-{device_id}"
            username = _sanitize(cfg.get("username"))
            password = _sanitize(cfg.get("password"))
            streams = cfg.get("streams") or []
            if not device_id or not token or not isinstance(streams, list):
                continue
            for s in streams:
                if not s or s.get("enabled") is False:
                    continue
                channel = int(s.get("channel") or 0)
                url = _sanitize(s.get("url"))
                if not url:
                    continue
                transport = _sanitize(s.get("transport") or "tcp")
                timeout_seconds = int(s.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
                full_url = _build_rtsp_url(url, username, password)
                k = (device_id, channel, full_url)
                seen.add(k)
                due = next_run.get(k, 0)
                if due > now:
                    continue
                next_run[k] = now + max(5, HEALTH_INTERVAL_SECONDS)
                ok, err = _probe_stream(full_url, transport, timeout_seconds)
                prev = last_ok.get(k)
                last_ok[k] = ok
                if prev is None:
                    continue
                if prev is True and ok is False:
                    desc = f"RTSP sem vídeo (ch={channel})"
                    if err:
                        desc = f"{desc} - {err}"
                    _post_push(token, "videoloss_started", channel, desc, "warn", {"rtsp_url": full_url, "device_name": name})
                elif prev is False and ok is True:
                    desc = f"RTSP voltou (ch={channel})"
                    _post_push(token, "videoloss_stopped", channel, desc, "info", {"rtsp_url": full_url, "device_name": name})
        for k in list(next_run.keys()):
            if k not in seen:
                next_run.pop(k, None)
                last_ok.pop(k, None)
        time.sleep(max(2, HEALTH_INTERVAL_SECONDS))


def _discovery_loop() -> None:
    if DISCOVERY_INTERVAL_SECONDS <= 0:
        return
    while True:
        try:
            discover(run_register=True)
        except Exception:
            pass
        time.sleep(max(5, DISCOVERY_INTERVAL_SECONDS))


@app.on_event("startup")
def _startup() -> None:
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    if HEALTH_INTERVAL_SECONDS > 0:
        t = threading.Thread(target=_health_loop, daemon=True)
        t.start()
    if DISCOVERY_INTERVAL_SECONDS > 0:
        t = threading.Thread(target=_discovery_loop, daemon=True)
        t.start()

