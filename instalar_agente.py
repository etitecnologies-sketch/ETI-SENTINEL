"""
ETI SENTINEL Agent - Instalador Automatico
Execute com: python instalar_agente.py
"""
import os, sys, subprocess

SERVER_URL = "https://monitoring-system-production-1e5a.up.railway.app/metrics"

def print_header():
    print("=" * 50)
    print("  ETI SENTINEL Agent - Instalador")
    print("=" * 50)
    print()

def install_deps():
    print("Instalando dependencias...")
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "psutil", "-q"])
    print("Dependencias instaladas!")
    print()

def create_agent(cliente, token, url):
    code = (
        "import os, time, logging, requests, subprocess, socket\n\n"
        "logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')\n"
        "logger = logging.getLogger('ETI-SENTINEL-" + cliente + "')\n\n"
        "INGEST_URL   = '" + url + "'\n"
        "DEVICE_TOKEN = '" + token + "'\n"
        "INTERVAL     = 10\n\n"
        "def get_hostname():\n"
        "    return socket.gethostname()\n\n"
        "def ping_device(ip):\n"
        "    try:\n"
        "        param = '-n' if os.name == 'nt' else '-c'\n"
        "        command = ['ping', param, '1', '-w', '3000', ip]\n"
        "        start = time.time()\n"
        "        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "        latency = round((time.time() - start) * 1000, 2)\n"
        "        return result.returncode == 0, latency\n"
        "    except:\n"
        "        return False, 0\n\n"
        "def collect_metrics(devices):\n"
        "    metrics = {'host': get_hostname(), 'cpu': 0, 'memory': 0, 'disk_percent': 0, 'uptime_seconds': 0, 'latency_ms': 0}\n"
        "    try:\n"
        "        import psutil\n"
        "        metrics['cpu']            = psutil.cpu_percent(interval=1)\n"
        "        metrics['memory']         = psutil.virtual_memory().percent\n"
        "        metrics['disk_percent']   = psutil.disk_usage('/').percent\n"
        "        metrics['uptime_seconds'] = int(time.time() - psutil.boot_time())\n"
        "    except ImportError:\n"
        "        pass\n"
        "    for dev in devices:\n"
        "        alive, lat = False, 0\n"
        "        if dev.get('ip_address') and dev.get('monitor_ping'):\n"
        "            alive, lat = ping_device(dev['ip_address'])\n"
        "        safe = dev.get('ip_address','').replace('.','_')\n"
        "        send({'host': f'DEVICE_{safe}', 'device_id': dev['id'], 'latency_ms': lat,\n"
        "              'status': 'online' if alive else 'offline', 'cpu': 0, 'memory': 0})\n"
        "        logger.info(f\"{'checkmark' if alive else 'X'} {dev['name']} {'ONLINE' if alive else 'OFFLINE'} ({lat}ms)\")\n"
        "    return metrics\n\n"
        "def send(data):\n"
        "    try:\n"
        "        headers = {'Content-Type': 'application/json', 'X-Device-Token': DEVICE_TOKEN}\n"
        "        requests.post(INGEST_URL, json=data, headers=headers, timeout=5)\n"
        "    except:\n"
        "        pass\n\n"
        "def fetch_devices():\n"
        "    try:\n"
        "        base = INGEST_URL.split('/metrics')[0]\n"
        "        r = requests.get(f'{base}/agent/devices', headers={'X-Device-Token': DEVICE_TOKEN}, timeout=10)\n"
        "        if r.status_code == 200:\n"
        "            return r.json()\n"
        "    except:\n"
        "        pass\n"
        "    return []\n\n"
        "def run():\n"
        "    logger.info(f'ETI SENTINEL Agent iniciado — {get_hostname()}')\n"
        "    logger.info(f'Servidor: {INGEST_URL}')\n"
        "    while True:\n"
        "        try:\n"
        "            devices = fetch_devices()\n"
        "            metrics = collect_metrics(devices)\n"
        "            headers = {'Content-Type': 'application/json', 'X-Device-Token': DEVICE_TOKEN}\n"
        "            r = requests.post(INGEST_URL, json=metrics, headers=headers, timeout=10)\n"
        "            if r.status_code in [200, 201]:\n"
        "                logger.info(f\"OK CPU:{metrics['cpu']}% MEM:{metrics['memory']}% DISCO:{metrics['disk_percent']}%\")\n"
        "            else:\n"
        "                logger.error(f'Erro API: {r.status_code}')\n"
        "        except requests.exceptions.ConnectionError:\n"
        "            logger.error('Sem conexao com o servidor')\n"
        "        except Exception as e:\n"
        "            logger.error(f'Erro: {e}')\n"
        "        time.sleep(INTERVAL)\n\n"
        "if __name__ == '__main__':\n"
        "    run()\n"
    )
    filename = f"agent_{cliente.replace(' ','_')}.py"
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"Agente criado: {filename}")
    return filepath

def create_task(cliente, agent_path):
    task_name = f"ETI_SENTINEL_{cliente.replace(' ','_')}"
    python_path = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(python_path):
        python_path = sys.executable
    cmd = [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", f'"{python_path}" "{agent_path}"',
        "/sc", "onstart",
        "/ru", "SYSTEM",
        "/f"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Tarefa criada: {task_name}")
        subprocess.run(["schtasks", "/run", "/tn", task_name])
        print("Agente iniciado em segundo plano!")
        return True
    else:
        print("ERRO ao criar tarefa. Execute como Administrador!")
        print(result.stderr)
        return False

def main():
    print_header()
    cliente = input("Nome do cliente: ").strip()
    if not cliente:
        print("Nome nao pode ser vazio!")
        return
    token = input("Token do device (copie do painel): ").strip()
    if not token:
        print("Token nao pode ser vazio!")
        return
    url_input = input("URL do servidor (Enter para usar padrao): ").strip()
    url = url_input if url_input else SERVER_URL
    print()
    print(f"Cliente : {cliente}")
    print(f"Servidor: {url}")
    print(f"Token   : {token[:10]}...")
    print()
    confirm = input("Confirmar instalacao? (s/n): ").strip().lower()
    if confirm != "s":
        print("Cancelado.")
        return
    print()
    install_deps()
    agent_path = create_agent(cliente, token, url)
    success = create_task(cliente, agent_path)
    print()
    print("=" * 50)
    if success:
        print(f"  Agente instalado para: {cliente}")
        print("  Inicia automaticamente com o Windows!")
    else:
        print("  Agente criado mas execute como Administrador")
        print(f"  para instalar como servico.")
    print("=" * 50)
    input("\nPressione Enter para fechar...")

if __name__ == "__main__":
    main()
