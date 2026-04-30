import os, time, logging, requests, subprocess, socket

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('ETI-SENTINEL-ETITECNOLOGIES')

INGEST_URL   = os.getenv('INGEST_URL', 'https://monitoring-system-production-1e5a.up.railway.app/metrics')
DEVICE_TOKEN = os.getenv('DEVICE_TOKEN', '')
INTERVAL     = 10

def get_hostname():
    return socket.gethostname()

def ping_device(ip):
    try:
        param = '-n' if os.name == 'nt' else '-c'
        command = ['ping', param, '1', '-w', '3000', ip]
        start = time.time()
        kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'stdin': subprocess.DEVNULL}
        if os.name == 'nt':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = getattr(subprocess, 'SW_HIDE', 0)
                kwargs['startupinfo'] = si
            except Exception:
                pass
        result = subprocess.run(command, **kwargs)
        latency = round((time.time() - start) * 1000, 2)
        return result.returncode == 0, latency
    except:
        return False, 0

def collect_metrics(devices):
    metrics = {'host': get_hostname(), 'cpu': 0, 'memory': 0, 'disk_percent': 0, 'uptime_seconds': 0, 'latency_ms': 0}
    try:
        import psutil
        metrics['cpu']            = psutil.cpu_percent(interval=1)
        metrics['memory']         = psutil.virtual_memory().percent
        metrics['disk_percent']   = psutil.disk_usage('/').percent
        metrics['uptime_seconds'] = int(time.time() - psutil.boot_time())
    except ImportError:
        pass
    for dev in devices:
        alive, lat = False, 0
        if dev.get('ip_address') and dev.get('monitor_ping'):
            alive, lat = ping_device(dev['ip_address'])
        safe = dev.get('ip_address','').replace('.','_')
        send({'host': f'DEVICE_{safe}', 'device_id': dev['id'], 'latency_ms': lat,
              'status': 'online' if alive else 'offline', 'cpu': 0, 'memory': 0})
        logger.info(f"{'checkmark' if alive else 'X'} {dev['name']} {'ONLINE' if alive else 'OFFLINE'} ({lat}ms)")
    return metrics

def send(data):
    try:
        headers = {'Content-Type': 'application/json', 'X-Device-Token': DEVICE_TOKEN}
        requests.post(INGEST_URL, json=data, headers=headers, timeout=5)
    except:
        pass

def fetch_devices():
    try:
        base = INGEST_URL.split('/metrics')[0]
        r = requests.get(f'{base}/agent/devices', headers={'X-Device-Token': DEVICE_TOKEN}, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []

def run():
    if not DEVICE_TOKEN:
        logger.error('DEVICE_TOKEN não definido. Configure a variável de ambiente DEVICE_TOKEN.')
        return
    logger.info(f'ETI SENTINEL Agent iniciado — {get_hostname()}')
    logger.info(f'Servidor: {INGEST_URL}')
    while True:
        try:
            devices = fetch_devices()
            metrics = collect_metrics(devices)
            headers = {'Content-Type': 'application/json', 'X-Device-Token': DEVICE_TOKEN}
            r = requests.post(INGEST_URL, json=metrics, headers=headers, timeout=10)
            if r.status_code in [200, 201]:
                logger.info(f"OK CPU:{metrics['cpu']}% MEM:{metrics['memory']}% DISCO:{metrics['disk_percent']}%")
            else:
                logger.error(f'Erro API: {r.status_code}')
        except requests.exceptions.ConnectionError:
            logger.error('Sem conexao com o servidor')
        except Exception as e:
            logger.error(f'Erro: {e}')
        time.sleep(INTERVAL)

if __name__ == '__main__':
    run()
