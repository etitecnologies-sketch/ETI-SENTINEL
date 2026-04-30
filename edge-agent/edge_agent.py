import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import requests
import shutil
import json

try:
    import psutil
except Exception:
    psutil = None

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

    ffmpeg_ok = shutil.which("ffmpeg") is not None
    print(f"ffmpeg: {'OK' if ffmpeg_ok else 'NÃO ENCONTRADO'}")

    if not ingest_api_url:
        print("ERRO: INGEST_API_URL não configurado")
        return 1

    sess = requests.Session()

    def get(path: str, headers=None, params=None):
        url = ingest_api_url + path
        last = None
        for attempt in range(2):
            try:
                r = sess.get(url, headers=headers or {}, params=params or {}, timeout=(3, timeout))
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



def main() -> None:
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env", override=True)
    env = os.environ.copy()

    if "--check" in sys.argv or "check" in sys.argv:
        raise SystemExit(run_check(here, env))

    repo_root = here.parent
    python = sys.executable
    if os.name == "nt":
        try:
            p = str(python or "")
            if p.lower().endswith("\\python.exe"):
                pw = p[:-len("\\python.exe")] + "\\pythonw.exe"
                if Path(pw).exists():
                    python = pw
        except Exception:
            pass

    enable_device = _bool(env.get("ENABLE_DEVICE_MONITOR", "1"))
    enable_rtsp = _bool(env.get("ENABLE_RTSP_MONITOR", "1"))
    enable_onvif = _bool(env.get("ENABLE_ONVIF_COLLECTOR", "1"))
    enable_discovery = _bool(env.get("ENABLE_DISCOVERY", "1"))
    enable_api = _bool(env.get("ENABLE_AGENT_API", "1"))
    enable_tray = _bool(env.get("ENABLE_TRAY", "0"))
    enable_recording = _bool(env.get("ENABLE_RECORDING", "0"))

    _cleanup_orphans(here, env)

    specs = []
    agent_api_port = int(_sanitize(env.get("AGENT_API_PORT") or "8808") or 8808)
    env.setdefault("EDGE_PUSH_URL", f"http://127.0.0.1:{agent_api_port}/api/push")
    if enable_api:
        specs.append([python, str(here / "agent_api.py")])
    if enable_device:
        specs.append([python, str(here / "device_monitor.py")])
    if enable_rtsp:
        # Inicia servidor HLS simples para servir os fragmentos de vídeo
        try:
            from http.server import SimpleHTTPRequestHandler, HTTPServer
            import threading

            class CORSRequestHandler(SimpleHTTPRequestHandler):
                def end_headers(self):
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Access-Control-Allow-Methods', 'GET')
                    self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                    return super().end_headers()

            def run_hls_server():
                hls_dir = here / "hls"
                os.makedirs(hls_dir, exist_ok=True)
                # Salva o diretório atual para voltar depois
                old_cwd = os.getcwd()
                try:
                    os.chdir(hls_dir)
                    httpd = HTTPServer(('0.0.0.0', 8000), CORSRequestHandler)
                    print("[INFO] Servidor HLS ativo na porta 8000")
                    httpd.serve_forever()
                finally:
                    os.chdir(old_cwd)

            threading.Thread(target=run_hls_server, daemon=True).start()
        except Exception as e:
            print(f"[ERROR] Falha ao iniciar servidor HLS: {e}")

        specs.append([python, str(repo_root / "rtsp-monitor" / "rtsp_monitor.py")])
    if enable_onvif:
        env.setdefault("ONVIF_REMOTE", "1")
        specs.append([python, str(repo_root / "onvif-collector" / "onvif_collector.py")])
    if enable_discovery:
        specs.append([python, str(here / "discovery_agent.py")])
    if enable_recording:
        specs.append([python, str(here / "recording_engine.py")])
    if enable_tray:
        specs.append([python, str(here / "tray_app.py")])

    if not specs:
        raise SystemExit("Nenhum módulo habilitado")

    procs = {}
    for args in specs:
        procs[_proc_name(args)] = _spawn(args, env)

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


if __name__ == "__main__":
    main()
