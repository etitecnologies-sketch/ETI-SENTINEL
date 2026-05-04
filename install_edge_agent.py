import os
import platform
import shutil
import subprocess
import sys
import argparse
from pathlib import Path


def _run(cmd, cwd=None, check=True):
    kwargs = {"cwd": cwd, "check": check}
    if os.name == "nt":
        kwargs["stdin"] = subprocess.DEVNULL
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kwargs["startupinfo"] = si
        except Exception:
            pass
    return subprocess.run(cmd, **kwargs)


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _is_root_linux() -> bool:
    try:
        return hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        return False


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


def _get_env_value(env_text: str, key: str) -> str:
    v = ""
    for line in env_text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, vv = line.split("=", 1)
        if k.strip() == key:
            v = vv
    return v


def _merge_env_example(env_path: Path, example_path: Path) -> None:
    if not env_path.exists() or not example_path.exists():
        return
    env_text = _read_text(env_path)
    env_keys = set()
    for line in env_text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        env_keys.add(line.split("=", 1)[0].strip())

    to_append = []
    for line in _read_text(example_path).splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in line:
            continue
        k = line.split("=", 1)[0].strip()
        if k and k not in env_keys:
            to_append.append(line)
            env_keys.add(k)

    if not to_append:
        return
    new_text = env_text
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"
    if new_text and not new_text.endswith("\n\n"):
        new_text += "\n"
    new_text += "\n".join(to_append) + "\n"
    _write_text(env_path, new_text)


def _set_env_kv(env_text: str, key: str, value: str) -> str:
    lines = env_text.splitlines()
    out = []
    found = False
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            out.append(line)
            continue
        k = line.split("=", 1)[0].strip()
        if k == key:
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1] != "":
            out.append("")
        out.append(f"{key}={value}")
    return "\n".join(out) + ("\n" if not env_text.endswith("\n") else "")


def _detect_os() -> str:
    if os.name == "nt":
        return "windows"
    sysname = platform.system().lower()
    if "linux" in sysname:
        return "linux"
    return sysname or "unknown"


def _venv_python(edge_dir: Path) -> Path:
    if os.name == "nt":
        return edge_dir / ".venv" / "Scripts" / "python.exe"
    return edge_dir / ".venv" / "bin" / "python"


def _venv_pythonw(edge_dir: Path) -> Path:
    if os.name == "nt":
        return edge_dir / ".venv" / "Scripts" / "pythonw.exe"
    return _venv_python(edge_dir)


def _ensure_venv(edge_dir: Path) -> None:
    venv_dir = edge_dir / ".venv"
    if venv_dir.exists():
        return
    _run([sys.executable, "-m", "venv", str(venv_dir)])


def _pip_install(edge_dir: Path) -> None:
    py = _venv_python(edge_dir)
    _run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(py), "-m", "pip", "install", "-r", str(edge_dir / "requirements.txt")])


def _ensure_ffmpeg_windows() -> bool:
    if _which("ffmpeg"):
        return True
    if not _which("winget"):
        return False
    r = _run(
        [
            "winget",
            "install",
            "--id",
            "Gyan.FFmpeg",
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        check=False,
    )
    if r.returncode != 0:
        return False
    return _which("ffmpeg")


def _ensure_ffmpeg_linux() -> bool:
    if _which("ffmpeg"):
        return True

    def run_pkg(cmd: list) -> int:
        return _run(cmd, check=False).returncode

    use_sudo = (not _is_root_linux()) and _which("sudo")
    prefix = ["sudo"] if use_sudo else []

    if _which("apt-get"):
        run_pkg(prefix + ["apt-get", "update"])
        rc = run_pkg(prefix + ["apt-get", "install", "-y", "ffmpeg"])
        if rc == 0:
            return _which("ffmpeg")
        return False

    if _which("dnf"):
        rc = run_pkg(prefix + ["dnf", "install", "-y", "ffmpeg"])
        if rc == 0:
            return _which("ffmpeg")
        return False

    if _which("yum"):
        rc = run_pkg(prefix + ["yum", "install", "-y", "ffmpeg"])
        if rc == 0:
            return _which("ffmpeg")
        return False

    if _which("pacman"):
        rc = run_pkg(prefix + ["pacman", "-Sy", "--noconfirm", "ffmpeg"])
        if rc == 0:
            return _which("ffmpeg")
        return False

    return False


def _ensure_ffmpeg() -> bool:
    if os.name == "nt":
        return _ensure_ffmpeg_windows()
    return _ensure_ffmpeg_linux()


def _ensure_env(edge_dir: Path) -> Path:
    env_path = edge_dir / ".env"
    example = edge_dir / ".env.example"
    if not example.exists():
        raise SystemExit("edge-agent/.env.example não encontrado")
    if not env_path.exists():
        shutil.copy(example, env_path)
        return env_path
    _merge_env_example(env_path, example)
    return env_path


def _configure_env(
    env_path: Path,
    ingest_arg: str | None,
    key_arg: str | None,
    cid_arg: str | None,
    non_interactive: bool,
) -> None:
    def sanitize_value(s: str) -> str:
        v = (s or "").strip()
        v = v.strip("`").strip('"').strip("'").strip()
        return v

    def sanitize_url(s: str) -> str:
        v = sanitize_value(s)
        if not v:
            return v
        if not v.startswith("http://") and not v.startswith("https://"):
            v = "https://" + v
        return v.rstrip("/")

    txt = _read_text(env_path)
    default_ingest = sanitize_url(_get_env_value(txt, "INGEST_API_URL"))
    if not default_ingest:
        default_ingest = "https://eti-sentinel-production.up.railway.app"
    default_key = sanitize_value(_get_env_value(txt, "COLLECTOR_KEY"))
    default_cid = sanitize_value(_get_env_value(txt, "CLIENT_ID"))

    ingest = sanitize_url(ingest_arg or "")
    key = sanitize_value(key_arg or "")
    cid = sanitize_value(cid_arg or "")

    if non_interactive:
        if not ingest:
            ingest = default_ingest
        if not key:
            key = default_key
        if not cid:
            cid = default_cid
    else:
        if not ingest:
            ingest_in = input(f"INGEST_API_URL (Enter = {default_ingest}): ").strip()
            ingest = sanitize_url(ingest_in) or default_ingest
        if not key:
            key_in = input("COLLECTOR_KEY (Enter mantém o atual): ").strip()
            key = sanitize_value(key_in) or default_key
        if not cid:
            cid_in = input("CLIENT_ID (opcional, Enter mantém o atual): ").strip()
            cid = sanitize_value(cid_in) or default_cid

    if not key:
        raise SystemExit("COLLECTOR_KEY é obrigatório (não foi encontrado nem informado).")

    if ingest:
        txt = _set_env_kv(txt, "INGEST_API_URL", ingest)
    if key:
        txt = _set_env_kv(txt, "COLLECTOR_KEY", key)
    if cid:
        txt = _set_env_kv(txt, "CLIENT_ID", cid)
    _write_text(env_path, txt)


def _install_windows_task(edge_dir: Path) -> None:
    task_name = "ETI_SENTINEL_EDGE"
    pyw = _venv_pythonw(edge_dir)
    if not pyw.exists():
        pyw = _venv_python(edge_dir)
    script = edge_dir / "edge_agent.py"
    cmd = f'"{pyw}" "{script}"'
    _run(["schtasks", "/create", "/tn", task_name, "/tr", cmd, "/sc", "onstart", "/ru", "SYSTEM", "/rl", "HIGHEST", "/f"], check=False)
    _run(["schtasks", "/run", "/tn", task_name], check=False)


def _install_linux_systemd_user(edge_dir: Path) -> None:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "eti-sentinel-edge.service"

    py = _venv_python(edge_dir)
    script = edge_dir / "edge_agent.py"
    env_file = edge_dir / ".env"

    unit = "\n".join(
        [
            "[Unit]",
            "Description=ETI SENTINEL Edge Agent",
            "",
            "[Service]",
            f"WorkingDirectory={edge_dir}",
            f"EnvironmentFile={env_file}",
            f"ExecStart={py} {script}",
            "Restart=always",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    _write_text(unit_path, unit)

    if _which("systemctl"):
        _run(["systemctl", "--user", "daemon-reload"], check=False)
        _run(["systemctl", "--user", "enable", "--now", "eti-sentinel-edge.service"], check=False)


def main() -> None:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--ingest-api-url", dest="ingest", default=None)
    ap.add_argument("--collector-key", dest="collector_key", default=None)
    ap.add_argument("--client-id", dest="client_id", default=None)
    ap.add_argument("--non-interactive", action="store_true")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent
    edge_dir = repo_root / "edge-agent"
    if not edge_dir.exists():
        raise SystemExit("Pasta edge-agent não encontrada")

    print(f"Sistema detectado: {_detect_os()}")

    _ensure_venv(edge_dir)
    _pip_install(edge_dir)

    print("Verificando dependências nativas (ffmpeg)...")
    ffmpeg_ok = _ensure_ffmpeg()
    if ffmpeg_ok:
        print("✓ ffmpeg OK")
    else:
        print("⚠ ffmpeg não instalado automaticamente.")
        if os.name == "nt":
            print("  Instale manualmente e reabra o terminal:")
            print("  winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements")
        else:
            print("  Instale manualmente (ex.: apt-get install -y ffmpeg) e reexecute o diagnóstico.")

    env_path = _ensure_env(edge_dir)
    _configure_env(env_path, args.ingest, args.collector_key, args.client_id, args.non_interactive)

    if os.name == "nt":
        _install_windows_task(edge_dir)
        print("Instalado no Windows (Scheduled Task: ETI_SENTINEL_EDGE)")
    else:
        _install_linux_systemd_user(edge_dir)
        print("Instalado no Linux (systemd --user: eti-sentinel-edge.service)")

    py = _venv_python(edge_dir)
    entry = edge_dir / "edge_agent.py"
    print("Executando diagnóstico agora (edge_agent.py --check)...")
    rc = _run([str(py), str(entry), "--check"], cwd=edge_dir, check=False).returncode
    if rc != 0:
        raise SystemExit("Diagnóstico falhou. Verifique conectividade/INGEST_API_URL/COLLECTOR_KEY e logs do serviço.")

    print("Pronto. Logs ficam no terminal do serviço e nos logs do systemd/schtasks.")
    print()
    print("OK. Diagnóstico passou.")


if __name__ == "__main__":
    main()
