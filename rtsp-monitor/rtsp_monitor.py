import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv


def _sanitize(s: Any) -> str:
    return str(s or "").strip()


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _post_push(ingest_api_url: str, token: str, device_id: int, event_type: str, channel: int, description: str, severity: str) -> None:
    edge_push = _sanitize(os.getenv("EDGE_PUSH_URL") or "")
    url = edge_push or (ingest_api_url.rstrip("/") + "/push")
    payload: Dict[str, Any] = {
        "token": token,
        "device_id": int(device_id or 0),
        "event_type": event_type,
        "channel": channel,
        "severity": severity,
        "description": description,
    }
    requests.post(url, json=payload, headers={"x-event-source": "rtsp-monitor"}, timeout=8)


def _fetch_rtsp_configs(ingest_api_url: str, collector_key: str, client_id: Optional[int]) -> List[Dict[str, Any]]:
    url = ingest_api_url.rstrip("/") + "/collector/rtsp-config"
    params = {}
    if client_id:
        params["client_id"] = client_id
    r = requests.get(url, headers={"x-collector-key": collector_key}, params=params, timeout=10)
    r.raise_for_status()
    return r.json() or []


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
        kwargs: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": max(3, timeout_seconds + 3), "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                kwargs["startupinfo"] = si
            except Exception:
                pass
        p = subprocess.run(args, **kwargs)
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


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")

    ingest_api_url = os.getenv("INGEST_API_URL") or "http://localhost:3000"
    collector_key = os.getenv("COLLECTOR_KEY") or ""
    client_id = os.getenv("CLIENT_ID")
    client_id_int = int(client_id) if client_id and str(client_id).isdigit() else None
    refresh_seconds = int(os.getenv("REMOTE_REFRESH_SECONDS") or 60)
    default_timeout = int(os.getenv("DEFAULT_TIMEOUT_SECONDS") or 8)
    default_interval = int(os.getenv("DEFAULT_INTERVAL_SECONDS") or 30)
    try:
        dedupe_seconds = float(os.getenv("EDGE_EVENT_DEDUPE_SECONDS") or 60)
    except Exception:
        dedupe_seconds = 60.0
    try:
        min_videoloss_seconds = float(os.getenv("EDGE_VIDEOLOSS_MIN_SECONDS") or 30)
    except Exception:
        min_videoloss_seconds = 30.0

    if not collector_key:
        raise SystemExit("COLLECTOR_KEY obrigatório")

    next_run: Dict[Tuple[int, int, str], float] = {}
    last_ok: Dict[Tuple[int, int, str], Optional[bool]] = {}
    last_sent: Dict[Tuple[str, int, int, str], float] = {}
    started_at: Dict[Tuple[int, int, str], float] = {}

    while True:
        try:
            configs = _fetch_rtsp_configs(ingest_api_url, collector_key, client_id_int)
        except Exception as e:
            logging.error("Falha ao buscar configs RTSP: %s", e)
            time.sleep(5)
            continue

        now = time.time()
        seen_keys = set()

        for cfg in configs:
            device_id = int(cfg.get("device_id") or 0)
            token = _sanitize(cfg.get("token"))
            name = _sanitize(cfg.get("name")) or f"device-{device_id}"
            username = _sanitize(cfg.get("username"))
            password = _sanitize(cfg.get("password"))
            streams = cfg.get("streams") or []
            if not token or not isinstance(streams, list):
                continue

            for s in streams:
                if not s or s.get("enabled") is False:
                    continue
                channel = int(s.get("channel") or 0)
                url = _sanitize(s.get("url"))
                if not url:
                    continue
                transport = _sanitize(s.get("transport") or "tcp")
                timeout_seconds = int(s.get("timeout_seconds") or default_timeout)
                interval_seconds = int(s.get("interval_seconds") or default_interval)
                display = _sanitize(s.get("name")) or f"Canal {channel}" if channel else "Stream"

                full_url = _build_rtsp_url(url, username, password)
                k = (device_id, channel, full_url)
                seen_keys.add(k)

                due = next_run.get(k, 0)
                if due > now:
                    continue
                next_run[k] = now + max(5, interval_seconds)

                ok, err = _probe_stream(full_url, transport, timeout_seconds)
                prev = last_ok.get(k)
                last_ok[k] = ok

                if prev is None:
                    logging.info("[%s] %s status=%s", name, display, "OK" if ok else "FAIL")
                    continue

                if prev is True and ok is False:
                    desc = f"RTSP sem vídeo ({display})"
                    if err:
                        desc = f"{desc} - {err}"
                    now2 = time.time()
                    started_at[k] = now2
                    sig = ("videoloss_started", device_id, channel, full_url)
                    last = float(last_sent.get(sig) or 0)
                    if (not last) or (now2 - last) >= max(1.0, dedupe_seconds):
                        _post_push(ingest_api_url, token, device_id, "videoloss_started", channel, desc, "warn")
                        last_sent[sig] = now2
                    logging.warning("[%s] %s -> OFF (%s)", name, display, err or "fail")
                elif prev is False and ok is True:
                    desc = f"RTSP voltou ({display})"
                    now2 = time.time()
                    st = float(started_at.get(k) or 0)
                    if st and (now2 - st) < max(0.0, min_videoloss_seconds):
                        logging.info("[%s] %s -> ON (ignored short flap %.1fs)", name, display, (now2 - st))
                        started_at.pop(k, None)
                        continue
                    started_at.pop(k, None)
                    sig = ("videoloss_stopped", device_id, channel, full_url)
                    last = float(last_sent.get(sig) or 0)
                    if (not last) or (now2 - last) >= max(1.0, dedupe_seconds):
                        _post_push(ingest_api_url, token, device_id, "videoloss_stopped", channel, desc, "info")
                        last_sent[sig] = now2
                    logging.info("[%s] %s -> ON", name, display)

        for k in list(next_run.keys()):
            if k not in seen_keys:
                next_run.pop(k, None)
                last_ok.pop(k, None)

        time.sleep(max(2, refresh_seconds))


if __name__ == "__main__":
    main()
