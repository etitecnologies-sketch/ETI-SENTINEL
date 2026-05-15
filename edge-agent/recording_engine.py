import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from camera_collector import _sanitize as sanitize


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _sanitize_base_url(url: str) -> str:
    u = sanitize(url)
    if not u:
        return u
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def _build_rtsp_url(url: str, username: str, password: str) -> str:
    u = sanitize(url)
    if "{username}" in u or "{password}" in u:
        return u.replace("{username}", sanitize(username)).replace("{password}", sanitize(password))
    return u


def _fetch_rtsp_configs(ingest_api_url: str, collector_key: str, client_id: Optional[int]) -> List[Dict[str, Any]]:
    url = ingest_api_url.rstrip("/") + "/collector/rtsp-config"
    params = {}
    if client_id:
        params["client_id"] = int(client_id)
    r = requests.get(url, headers={"x-collector-key": collector_key}, params=params, timeout=(5, 18))
    r.raise_for_status()
    return r.json() or []


def _key(device_id: int, channel: int, url: str) -> Tuple[int, int, str]:
    return int(device_id), int(channel), sanitize(url)


def _spawn_record(rtsp_url: str, transport: str, out_pattern: str, log_path: Path) -> subprocess.Popen:
    t = (transport or "tcp").lower()
    if t not in {"tcp", "udp"}:
        t = "tcp"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        t,
        "-i",
        rtsp_url,
        "-c",
        "copy",
        "-f",
        "segment",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        "-strftime_mkdir",   # <-- CORRECAO: ffmpeg cria os subdiretorios com tokens de data
        "1",
        "-segment_time",
        str(int(os.getenv("RECORD_SEGMENT_SECONDS") or 10)),
        out_pattern,
    ]
    with log_path.open("a", encoding="utf-8") as lf:
        kwargs = {"stdout": lf, "stderr": lf, "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                kwargs["startupinfo"] = si
            except Exception:
                pass
        return subprocess.Popen(args, **kwargs)


def main() -> None:
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env", override=True)
    env = os.environ.copy()

    if not _bool(env.get("ENABLE_RECORDING") or "0"):
        raise SystemExit("ENABLE_RECORDING=0")

    ingest_api_url = _sanitize_base_url(env.get("INGEST_API_URL") or "")
    collector_key = sanitize(env.get("COLLECTOR_KEY") or "")
    client_id = sanitize(env.get("CLIENT_ID") or "")
    client_id_int = int(client_id) if client_id.isdigit() else None
    base_dir = Path(sanitize(env.get("RECORD_BASE_DIR") or str(here / ".recordings"))).resolve()
    refresh_seconds = int(env.get("RECORD_REFRESH_SECONDS") or 60)

    if not ingest_api_url or not collector_key:
        raise SystemExit("INGEST_API_URL e COLLECTOR_KEY obrigatórios")

    procs: Dict[Tuple[int, int, str], subprocess.Popen] = {}

    while True:
        try:
            cfgs = _fetch_rtsp_configs(ingest_api_url, collector_key, client_id_int)
        except Exception:
            time.sleep(5)
            continue

        seen = set()
        for cfg in cfgs:
            device_id = int(cfg.get("device_id") or 0)
            name = sanitize(cfg.get("name") or f"device-{device_id}")
            username = sanitize(cfg.get("username") or "")
            password = sanitize(cfg.get("password") or "")
            streams = cfg.get("streams") or []
            if not isinstance(streams, list):
                continue
            for s in streams:
                try:
                    if not isinstance(s, dict):
                        continue
                    if _bool(s.get("enabled")) is False:
                        continue
                    ch = int(s.get("channel") or 0)
                    url = sanitize(s.get("url") or "")
                    if not device_id or not url:
                        continue
                    transport = sanitize(s.get("transport") or "tcp")
                    rtsp_url = _build_rtsp_url(url, username, password)

                    # CORRECAO: nao criar diretorios com tokens strftime (%Y%m%d, %H)
                    # O ffmpeg resolve esses tokens em tempo de execucao via -strftime_mkdir
                    base_out_dir = base_dir / f"device_{device_id}" / f"ch_{ch}"
                    base_out_dir.mkdir(parents=True, exist_ok=True)
                    out_pattern = str(base_out_dir / "%Y%m%d" / "%H" / "seg_%Y%m%d_%H%M%S.mp4")
                    log_path = base_dir / f"device_{device_id}" / f"ch_{ch}" / "ffmpeg.log"

                    k = _key(device_id, ch, rtsp_url)
                    seen.add(k)
                    p = procs.get(k)
                    if p is None or p.poll() is not None:
                        procs[k] = _spawn_record(rtsp_url, transport, out_pattern, log_path)
                except Exception:
                    continue

        for k, p in list(procs.items()):
            if k in seen:
                continue
            try:
                p.terminate()
            except Exception:
                pass
            procs.pop(k, None)

        time.sleep(max(5, refresh_seconds))


if __name__ == "__main__":
    main()
