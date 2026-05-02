import subprocess
import os
from pathlib import Path


def find_mediamtx():
    possible_paths = [
        Path(os.environ.get("PROGRAMDATA", "")) / "ETI-SENTINEL" / "bin" / "mediamtx.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "ETI-SENTINEL" / "bin" / "mediamtx.exe",
        Path(__file__).resolve().parent.parent.parent / "bin" / "mediamtx.exe",
        Path(__file__).resolve().parent.parent / "bin" / "mediamtx.exe",
    ]

    for p in possible_paths:
        if p.exists():
            return str(p)

    return ""


def start_mediamtx(mediamtx_path=None):
    if mediamtx_path is None:
        mediamtx_path = find_mediamtx()

    if not mediamtx_path or not Path(mediamtx_path).exists():
        return None

    env = os.environ.copy()
    env["MTX_PATHS_ALL_SOURCE"] = "publisher"
    env["MTX_WEBRTC"] = "yes"
    env["MTX_HLS"] = "yes"

    kwargs = {
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL
    }

    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kwargs["startupinfo"] = si
        except Exception:
            pass

    proc = subprocess.Popen([mediamtx_path], **kwargs)
    return proc
