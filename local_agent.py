import os, time, logging, requests, subprocess, socket

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LocalAgent")

# ── CONFIGURAÇÃO ──────────────────────────────────────────────
INGEST_URL = os.getenv("INGEST_URL", "https://monitoring-system-production-1e5a.up.railway.app/metrics")
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "")
INTERVAL     = 10

def get_hostname():
    return socket.gethostname()

def check_port(host, port):
    try:
        try:
            socket.gethostbyname(host)
        except socket.gaierror:
            return False, 0, "DNS_ERROR"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        start = time.time()
        result = s.connect_ex((host, int(port)))
        latency = round((time.time() - start) * 1000, 2)
        s.close()
        if result == 10061:   error_type = "REFUSED"
        elif result == 10060: error_type = "TIMEOUT"
        elif result != 0:     error_type = f"ERR_{result}"
        else:                 error_type = None
        return result == 0, latency, error_type
    except Exception as e:
        return False, 0, str(e)

def ping_device(ip):
    try:
        param = "-n" if os.name == "nt" else "-c"
        command = ["ping", param, "1", "-w", "3000", ip]
        start = time.time()
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                kwargs["startupinfo"] = si
            except Exception:
                pass
        result = subprocess.run(command, **kwargs)
        latency = round((time.time() - start) * 1000, 2)
        return result.returncode == 0, latency
    except:
        return False, 0

def collect_local_metrics(devices_to_check):
    metrics = {
        "host": get_hostname(),
        "cpu": 0, "memory": 0, "disk_percent": 0,
        "uptime_seconds": 0, "latency_ms": 0
    }
    try:
        import psutil
        metrics["cpu"]            = psutil.cpu_percent(interval=1)
        metrics["memory"]         = psutil.virtual_memory().percent
        metrics["disk_percent"]   = psutil.disk_usage('/').percent
        metrics["uptime_seconds"] = int(time.time() - psutil.boot_time())
    except ImportError:
        logger.warning("psutil nao instalado. Rode: pip install psutil")

    for dev in devices_to_check:
        alive  = False
        lat    = 0
        method = "UNKNOWN"
        target = "N/A"
        error_detail = ""

        if dev.get("ddns_address") and dev.get("monitor_port"):
            target = dev["ddns_address"]
            port   = dev["monitor_port"]
            alive, lat, err = check_port(target, port)
            method = f"TCP:{port}"
            if not alive:
                error_detail = f" (Erro: {err})" if err else ""
                logger.warning(f"DDNS {target}:{port} falhou{error_detail}")

        if not alive and dev.get("ip_address") and dev.get("monitor_ping"):
            target = dev["ip_address"]
            alive, lat = ping_device(target)
            method = "PING"

        if not target or target == "N/A":
            continue

        safe_host_id = target.replace(".", "_").replace("-", "_")
        status_data = {
            "host":       f"DEVICE_{safe_host_id}",
            "device_id":  dev["id"],
            "latency_ms": lat,
            "status":     "online" if alive else "offline",
            "cpu": 0, "memory": 0
        }

        if alive:
            logger.info(f"✓ {dev['name']} ({target}) [{method}] ONLINE ({lat}ms)")
        elif method != "UNKNOWN":
            logger.warning(f"✗ {dev['name']} ({target}) [{method}] OFFLINE{error_detail}")

        send_to_api(status_data)

    return metrics

def send_to_api(data):
    try:
        headers = {"Content-Type": "application/json", "X-Device-Token": DEVICE_TOKEN}
        requests.post(INGEST_URL, json=data, headers=headers, timeout=5)
    except:
        pass

def fetch_devices():
    try:
        base_url = INGEST_URL.split("/metrics")[0]
        headers  = {"X-Device-Token": DEVICE_TOKEN}
        r = requests.get(f"{base_url}/agent/devices", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"Erro ao buscar dispositivos: {e}")
    return []

def run_agent():
    if not DEVICE_TOKEN:
        logger.error("✗ DEVICE_TOKEN não definido. Configure a variável de ambiente DEVICE_TOKEN.")
        return
    logger.info(f"ETI SENTINEL Agent iniciado — {get_hostname()}")
    logger.info(f"Enviando para: {INGEST_URL}")
    logger.info(f"Intervalo: {INTERVAL}s")

    while True:
        try:
            devices = fetch_devices()
            if devices:
                logger.info(f"Monitorando {len(devices)} dispositivo(s)")

            metrics = collect_local_metrics(devices)

            headers  = {"Content-Type": "application/json", "X-Device-Token": DEVICE_TOKEN}
            response = requests.post(INGEST_URL, json=metrics, headers=headers, timeout=10)

            if response.status_code in [200, 201]:
                logger.info(f"✓ CPU:{metrics['cpu']}% MEM:{metrics['memory']}% DISCO:{metrics['disk_percent']}%")
            elif response.status_code == 401:
                logger.error("✗ Token invalido!")
            elif response.status_code == 404:
                logger.error(f"✗ URL nao encontrada: {INGEST_URL}")
            else:
                logger.error(f"✗ Erro API: {response.status_code}")

        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Sem conexao com {INGEST_URL}")
        except Exception as e:
            logger.error(f"✗ Erro: {e}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
