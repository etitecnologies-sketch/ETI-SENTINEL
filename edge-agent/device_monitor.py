import concurrent.futures
import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv


def _sanitize(s: Any) -> str:
    return str(s or "").strip().strip("`").strip('"').strip("'").strip()


def _sanitize_base_url(url: str) -> str:
    u = _sanitize(url)
    if not u:
        return u
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _tcp_check(host: str, port: int, timeout_seconds: float) -> Tuple[bool, float]:
    if not host or not port:
        return False, 0.0
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_seconds)
    start = time.time()
    try:
        rc = s.connect_ex((host, int(port)))
        latency_ms = (time.time() - start) * 1000.0
        return rc == 0, float(round(latency_ms, 1))
    except Exception:
        return False, 0.0
    finally:
        try:
            s.close()
        except Exception:
            pass


def _ping(host: str, timeout_ms: int) -> Tuple[bool, float]:
    if not host:
        return False, 0.0
    t0 = time.time()
    try:
        if os.name == "nt":
            args = ["ping", "-n", "1", "-w", str(int(timeout_ms)), host]
        else:
            args = ["ping", "-c", "1", "-W", str(max(1, int(timeout_ms / 1000))), host]
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "timeout": max(2, int(timeout_ms / 1000) + 2),
        }
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
        latency_ms = (time.time() - t0) * 1000.0
        return p.returncode == 0, float(round(latency_ms, 1))
    except Exception:
        return False, 0.0


def _fetch_devices(ingest_api_url: str, collector_key: str, client_id: Optional[int]) -> List[Dict[str, Any]]:
    url = ingest_api_url.rstrip("/") + "/collector/devices"
    params: Dict[str, Any] = {}
    if client_id:
        params["client_id"] = client_id
    r = requests.get(url, headers={"x-collector-key": collector_key}, params=params, timeout=10)
    r.raise_for_status()
    return r.json() or []


def _push_heartbeat(ingest_api_url: str, token: str, latency_ms: float, client_id: Optional[int] = None) -> None:
    edge_push = _sanitize(os.getenv("EDGE_PUSH_URL"))
    url = edge_push or (ingest_api_url.rstrip("/") + "/push")
    payload = {
        "token": token,
        "event_type": "edge_heartbeat",
        "severity": "info",
        "latency": latency_ms
    }
    if client_id:
        payload["client_id"] = client_id
    requests.post(url, json=payload, headers={"x-event-source": "edge-device-monitor"}, timeout=8)


def _check_one(dev: Dict[str, Any], ingest_api_url: str, client_id: Optional[int] = None) -> Tuple[int, str, bool, float]:
    device_id = int(dev.get("device_id") or 0)
    token = _sanitize(dev.get("token"))
    name = _sanitize(dev.get("name")) or f"device-{device_id}"
    ip = _sanitize(dev.get("ip_address"))
    ddns = _sanitize(dev.get("ddns_address"))
    monitor_ping = dev.get("monitor_ping") is True or _bool(dev.get("monitor_ping"))
    monitor_port = int(dev.get("monitor_port") or 0)

    alive = False
    latency_ms = 0.0

    target_host = ddns or ip
    if monitor_port and target_host:
        alive, latency_ms = _tcp_check(target_host, monitor_port, timeout_seconds=3.0)
    elif monitor_ping and ip:
        alive, latency_ms = _ping(ip, timeout_ms=1500)

    if alive and token:
        try:
            _push_heartbeat(ingest_api_url, token, latency_ms, client_id)
        except Exception:
            pass

    return device_id, name, alive, latency_ms


def main() -> None:
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env", override=True)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")

    ingest_api_url = _sanitize_base_url(os.getenv("INGEST_API_URL") or "http://localhost:3000")
    collector_key = _sanitize(os.getenv("COLLECTOR_KEY"))
    client_id = _sanitize(os.getenv("CLIENT_ID"))
    client_id_int = int(client_id) if client_id.isdigit() else None
    interval_seconds = int(os.getenv("DEVICE_INTERVAL_SECONDS") or 10)
    workers = int(os.getenv("DEVICE_WORKERS") or 30)

    if not collector_key:
        raise SystemExit("COLLECTOR_KEY obrigatório")

    while True:
        try:
            devices = _fetch_devices(ingest_api_url, collector_key, client_id_int)
        except Exception as e:
            logging.error("Falha ao buscar devices: %s", e)
            time.sleep(5)
            continue

        if not devices:
            time.sleep(max(2, interval_seconds))
            continue

        ok_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futures = [ex.submit(_check_one, d, ingest_api_url, client_id_int) for d in devices]
            for f in concurrent.futures.as_completed(futures):
                try:
                    device_id, name, alive, latency_ms = f.result()
                    if alive:
                        ok_count += 1
                        logging.info("[%s] ONLINE (%.1fms)", name, latency_ms)
                    else:
                        logging.debug("[%s] OFFLINE", name)
                except Exception:
                    pass

        logging.info("Heartbeat enviado para %d/%d device(s)", ok_count, len(devices))
        time.sleep(max(2, interval_seconds))


if __name__ == "__main__":
    main()
