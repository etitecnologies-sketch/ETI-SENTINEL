import os
import platform
import subprocess
import sys
import time
import threading
import logging
import ctypes
import socket
import struct
from pathlib import Path

from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import shutil
import json

try:
    import psutil
except Exception:
    psutil = None


def get_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session

def _bool(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _proc_name(args):
    try:
        return Path(args[-1]).name
    except Exception:
        return "process"


def _spawn(args, env):
    kwargs = {"env": env, "cwd": str(Path(args[-1]).resolve().parent)}
    if os.name == "nt":
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW
        creationflags |= 0x00000008
        kwargs["creationflags"] = creationflags
        kwargs["stdin"] = subprocess.DEVNULL
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    return subprocess.Popen(args, **kwargs)


def _kill_stale_processes(match: str) -> None:
    if not psutil:
        return
    me = os.getpid()
    for p in psutil.process_iter(attrs=["pid", "cmdline"]):
        try:
            pid = int(p.info.get("pid") or 0)
            if not pid or pid == me:
                continue
            cmdline = p.info.get("cmdline") or []
            cmd = " ".join(str(x or "") for x in cmdline)
            if match not in cmd:
                continue
            try:
                psutil.Process(pid).terminate()
            except Exception:
                pass
        except Exception:
            continue


def _cleanup_orphans(here: Path, env: dict) -> None:
    if not psutil:
        return
    port = int(_sanitize(env.get("AGENT_API_PORT") or "8808") or 8808)
    for c in psutil.net_connections(kind="tcp"):
        try:
            if c.status != psutil.CONN_LISTEN:
                continue
            if not c.laddr or int(c.laddr.port) != port:
                continue
            pid = int(c.pid or 0)
            if not pid or pid == os.getpid():
                continue
            proc = psutil.Process(pid)
            cmd = " ".join(proc.cmdline() or [])
            if "agent_api.py" in cmd:
                try:
                    proc.terminate()
                except Exception:
                    pass
        except Exception:
            continue

    _kill_stale_processes(str(here / "agent_api.py"))


def _sanitize(s) -> str:
    v = str(s or "").strip()
    v = (
        v.replace("`", "")
        .replace("´", "")
        .replace("“", "")
        .replace("”", "")
        .replace("‘", "")
        .replace("’", "")
        .replace('"', "")
        .replace("'", "")
        .strip()
    )
    return v


def _sanitize_base_url(url: str) -> str:
    u = _sanitize(url)
    if not u:
        return u
    # Remove backticks, quotes and other common copy-paste trash
    u = u.replace("`", "").replace("'", "").replace("\"", "").strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def _short_body(text: str, limit: int = 240) -> str:
    t = (text or "").strip().replace("\r", " ").replace("\n", " ")
    if len(t) <= limit:
        return t
    return t[:limit] + "..."


def _redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in {"password", "password_enc", "token", "jwt", "secret", "collector_key"}:
                out[k] = "***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def run_check(here: Path, env: dict) -> int:
    timeout = float(env.get("CHECK_TIMEOUT_SECONDS") or 6)
    ingest_api_url = _sanitize_base_url(env.get("INGEST_API_URL") or "")
    collector_key = _sanitize(env.get("COLLECTOR_KEY") or "")
    client_id = _sanitize(env.get("CLIENT_ID") or "")
    agent_api_port = int(_sanitize(env.get("AGENT_API_PORT") or "8808") or 8808)

    print("ETI SENTINEL Edge Agent - Diagnóstico")
    print(f"OS: {platform.system()} ({os.name})")
    print(f"Python: {sys.executable}")
    print(f"Edge dir: {here}")
    print(f"INGEST_API_URL: {ingest_api_url or '(vazio)'}")
    print(f"COLLECTOR_KEY: {'OK' if collector_key else '(vazio)'}")
    print(f"CLIENT_ID: {client_id or '(vazio)'}")

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        # Tenta no diretório bin da instalação
        p = here.parent / "bin" / "ffmpeg.exe"
        if p.exists(): ffmpeg_path = str(p)
    
    print(f"ffmpeg: {'OK (' + ffmpeg_path + ')' if ffmpeg_path else 'NÃO ENCONTRADO'}")

    # Check MediaMTX
    mtx_bin = None
    possible_mtx = [
        here.parent / "bin" / "mediamtx.exe",
        Path(os.environ.get("PROGRAMDATA", "")) / "ETI-SENTINEL" / "bin" / "mediamtx.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "ETI-SENTINEL" / "bin" / "mediamtx.exe",
        here / "mediamtx.exe",
    ]
    for p in possible_mtx:
        if p.exists():
            mtx_bin = p
            break
    print(f"mediamtx: {'OK (' + str(mtx_bin) + ')' if mtx_bin else 'NÃO ENCONTRADO'}")

    enable_streaming = _bool(env.get("ENABLE_STREAMING", "1"))
    if enable_streaming and not ffmpeg_path:
        print("ERRO: ffmpeg é obrigatório quando ENABLE_STREAMING=1")
        return 1
    if enable_streaming and not mtx_bin:
        print("ERRO: mediamtx é obrigatório quando ENABLE_STREAMING=1")
        return 1

    # Exporta os caminhos encontrados para serem usados no main()
    os.environ["INTERNAL_FFMPEG_PATH"] = ffmpeg_path or "ffmpeg"
    os.environ["INTERNAL_MEDIAMTX_PATH"] = str(mtx_bin) if mtx_bin else ""

    if not ingest_api_url:
        print("ERRO: INGEST_API_URL não configurado")
        return 1

    sess = get_session()

    def get(path: str, headers=None, params=None):
        url = ingest_api_url + path
        last = None
        for attempt in range(3):
            try:
                r = sess.get(url, headers=headers or {}, params=params or {}, timeout=(10, 60))
                ct = str(r.headers.get("content-type") or "")
                if "application/json" in ct:
                    try:
                        data = r.json()
                        return r.status_code, json.dumps(_redact(data), ensure_ascii=False)[:240]
                    except Exception:
                        return r.status_code, _short_body(r.text)
                return r.status_code, _short_body(r.text)
            except Exception as e:
                last = e
                time.sleep(0.4)
        return 0, _short_body(str(last))

    code, body = (0, "")
    try:
        r = requests.get(f"http://127.0.0.1:{agent_api_port}/health", timeout=2)
        code = r.status_code
        body = _short_body(r.text)
    except Exception as e:
        code = 0
        body = _short_body(str(e))
    print(f"GET local /health -> {code} | {body}")

    code, body = get("/ready")
    print(f"GET /ready -> {code} | {body}")
    base_ok = code == 200

    code, body = get("/health")
    print(f"GET /health -> {code} | {body}")

    if collector_key:
        headers = {"x-collector-key": collector_key}
        params = {"client_id": client_id} if client_id and client_id.isdigit() else {}

        code, body = get("/collector/devices", headers=headers, params=params)
        print(f"GET /collector/devices -> {code} | {body}")

        code, body = get("/collector/rtsp-config", headers=headers, params=params)
        print(f"GET /collector/rtsp-config -> {code} | {body}")

        code, body = get("/collector/onvif-config", headers=headers, params=params)
        print(f"GET /collector/onvif-config -> {code} | {body}")
    else:
        print("INFO: COLLECTOR_KEY vazio, pulando /collector/*")

    if not base_ok:
        return 1
    return 0



def get_gateway_ip():
    """Detecta o gateway da rede automaticamente ou usa o definido no .env"""
    manual_gw = os.getenv("MANUAL_GATEWAY_IP")
    if manual_gw:
        return manual_gw
    
    try:
        if os.name == 'nt': # Windows
            import subprocess
            cmd = "route print 0.0.0.0 | findstr 0.0.0.0"
            out = subprocess.check_output(cmd, shell=True).decode()
            parts = out.split()
            if len(parts) >= 3:
                return parts[2]
        else: # Linux/Mac
            with open("/proc/net/route") as fh:
                for line in fh:
                    fields = line.strip().split()
                    if fields[1] == '00000000':
                        return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except:
        pass
    return "127.0.0.1"


def run_speedtest():
    """Executa um teste de velocidade real usando speedtest-cli"""
    try:
        import speedtest
        s = speedtest.Speedtest()
        s.get_best_server()
        download = s.download() / 1_000_000 # Mbps
        upload = s.upload() / 1_000_000 # Mbps
        ping = s.results.ping
        return {"download": round(download, 2), "upload": round(upload, 2), "ping": round(ping, 2)}
    except Exception as e:
        logging.error(f"Erro no SpeedTest: {e}")
        return {"download": 0, "upload": 0, "ping": 0}


def main() -> None:
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env", override=True)
    env = os.environ.copy()

    gateway_ip = get_gateway_ip()
    logging.info(f"Gateway Detectado: {gateway_ip}")
    os.environ["INTERNAL_GATEWAY_IP"] = gateway_ip

    # Executa o diagnóstico interno antes de subir os serviços para mapear os binários
    check_rc = run_check(here, env)
    
    ffmpeg_exe = os.environ.get("INTERNAL_FFMPEG_PATH", "ffmpeg")
    mtx_exe = os.environ.get("INTERNAL_MEDIAMTX_PATH", "")

    if "--check" in sys.argv or "check" in sys.argv:
        raise SystemExit(int(check_rc))

    if os.name == "nt":
        try:
            mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ETI_SENTINEL_EDGE_AGENT_SINGLETON")
            if ctypes.windll.kernel32.GetLastError() == 183:
                raise SystemExit("Edge Agent já está em execução.")
        except Exception:
            pass

    repo_root = here.parent
    python = sys.executable
    if os.name == "nt":
        try:
            use_pw = str(env.get("EDGE_USE_PYTHONW") or "1").strip().lower() not in {"0", "false", "no", "off"}
            if use_pw:
                p = str(python or "")
                if p.lower().endswith("\\python.exe"):
                    pw = p[:-len("\\python.exe")] + "\\pythonw.exe"
                    if Path(pw).exists():
                        python = pw
        except Exception:
            pass

    enable_device = _bool(env.get("ENABLE_DEVICE_MONITOR", "1"))
    enable_streaming = _bool(env.get("ENABLE_STREAMING", "1"))
    enable_onvif = _bool(env.get("ENABLE_ONVIF_COLLECTOR", "1"))
    enable_discovery = _bool(env.get("ENABLE_DISCOVERY", "1"))
    enable_api = _bool(env.get("ENABLE_AGENT_API", "1"))
    enable_tray = _bool(env.get("ENABLE_TRAY", "0"))
    enable_recording = _bool(env.get("ENABLE_RECORDING", "0"))
    manage_mediamtx = _bool(env.get("EDGE_START_MEDIAMTX", "1"))

    _cleanup_orphans(here, env)

    specs = []
    agent_api_port = int(_sanitize(env.get("AGENT_API_PORT") or "8808") or 8808)
    env.setdefault("EDGE_PUSH_URL", f"http://127.0.0.1:{agent_api_port}/api/push")
    if enable_api:
        try:
            import agent_api

            bind = _sanitize(env.get("AGENT_API_BIND") or "0.0.0.0") or "0.0.0.0"
            store = agent_api.JobStore(here / ".state" / "agent_api.json")
            log_path = here / ".state" / "agent_api.log"
            httpd = agent_api.Server((bind, agent_api_port), agent_api.Handler, env, store, log_path)
            
            # Handler para comandos do WebSocket (como rodar Speed Test)
            def on_websocket_message(msg):
                try:
                    data = json.loads(msg)
                    if data.get("type") == "COMMAND" and data.get("action") == "RUN_SPEEDTEST":
                        logging.info("Comando Speed Test recebido via WebSocket")
                        res = run_speedtest()
                        # Envia o resultado de volta para a API
                        ingest_url = _sanitize_base_url(os.getenv("INGEST_API_URL"))
                        requests.post(f"{ingest_url}/speedtest", json={
                            "download": res["download"],
                            "upload": res["upload"],
                            "ping": res["ping"],
                            "client_id": os.getenv("CLIENT_ID")
                        }, headers={"x-collector-key": os.getenv("COLLECTOR_KEY")})
                except Exception as e:
                    logging.error(f"Erro ao processar comando WebSocket: {e}")

            httpd.relay.start()
            # Se você tiver uma implementação de WebSocket Client no agente, ela deve chamar on_websocket_message
            
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            print(f"[INFO] Agent API (relay) iniciado em {bind}:{agent_api_port}")
            os.environ.setdefault("EDGE_PUSH_URL", f"http://127.0.0.1:{agent_api_port}/api/push")
        except Exception as e:
            print(f"[WARN] Falha ao iniciar Agent API (relay): {e}")
    if enable_device:
        specs.append([python, str(here / "device_monitor.py")])
    if enable_streaming:
        try:
            from services.mediamtx_service import start_mediamtx
            from core.api_client import APIClient
            from core.stream_manager import StreamManager
            from core.state_cache import StateCache
            from workers.stream_worker import StreamWorker
            from workers.watchdog_worker import WatchdogWorker
            from workers.heartbeat_worker import HeartbeatWorker
            from workers.ai_worker import AIWorker

            try:
                (here / ".state").mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            log_file = _sanitize(env.get("EDGE_LOG_FILE") or str(here / ".state" / "edge_agent.log"))
            level = os.getenv("LOG_LEVEL", "INFO").upper()
            fmt = "%(asctime)s %(levelname)s %(message)s"
            root = logging.getLogger()
            try:
                want_file = Path(log_file).resolve()
            except Exception:
                want_file = None
            try:
                if want_file:
                    want_file.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            try:
                has_file_handler = False
                for h in list(root.handlers or []):
                    try:
                        fn = getattr(h, "baseFilename", None)
                        if fn and want_file and Path(str(fn)).resolve() == want_file:
                            has_file_handler = True
                            break
                    except Exception:
                        continue
                if not has_file_handler and want_file:
                    fh = logging.FileHandler(str(want_file), encoding="utf-8")
                    fh.setFormatter(logging.Formatter(fmt))
                    root.addHandler(fh)
            except Exception:
                pass

            try:
                has_stream_handler = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in (root.handlers or []))
                if not has_stream_handler:
                    sh = logging.StreamHandler()
                    sh.setFormatter(logging.Formatter(fmt))
                    root.addHandler(sh)
            except Exception:
                pass

            try:
                root.setLevel(level)
            except Exception:
                pass

            if manage_mediamtx and mtx_exe:
                proc = start_mediamtx(mtx_exe)
                if proc:
                    print(f"[INFO] MediaMTX (WebRTC/HLS) iniciado a partir de: {mtx_exe}")
            api = APIClient()
            manager = StreamManager(max_retries=int(_sanitize(env.get("STREAM_MAX_RETRIES") or "0") or 0))
            cache = StateCache(cache_file=_sanitize(env.get("CACHE_FILE") or str(here / ".state" / "rtsp_cache.json")))

            stream_worker = StreamWorker(api, manager, cache)
            watchdog_worker = WatchdogWorker(manager)
            heartbeat_worker = HeartbeatWorker(api, interval=int(_sanitize(env.get("HEARTBEAT_INTERVAL") or "15") or 15))
            ai_worker = AIWorker(manager)

            threading.Thread(target=stream_worker.run, daemon=True).start()
            threading.Thread(target=watchdog_worker.run, daemon=True).start()
            threading.Thread(target=heartbeat_worker.run, daemon=True).start()
            threading.Thread(target=ai_worker.run, daemon=True).start()
        except Exception as e:
            print(f"[ERROR] Falha ao iniciar streaming PRO: {e}")
    if enable_onvif:
        env.setdefault("ONVIF_REMOTE", "1")
        specs.append([python, str(repo_root / "onvif-collector" / "onvif_collector.py")])
    if enable_discovery:
        specs.append([python, str(here / "discovery_agent.py")])
    if enable_recording:
        specs.append([python, str(here / "recording_engine.py")])
    if enable_tray:
        specs.append([python, str(here / "tray_app.py")])

    if not specs and not enable_streaming and not enable_api:
        raise SystemExit("Nenhum módulo habilitado")

    procs = {}
    for args in specs:
        procs[_proc_name(args)] = _spawn(args, env)

    try:
        while True:
            time.sleep(2)
            for name, p in list(procs.items()):
                rc = p.poll()
                if rc is None:
                    continue
                time.sleep(2)
                for args in specs:
                    if _proc_name(args) == name:
                        procs[name] = _spawn(args, env)
                        break
    except KeyboardInterrupt:
        for p in list(procs.values()):
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
