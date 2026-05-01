import subprocess
import os
import shutil
import time
import socket
from pathlib import Path


def find_ffmpeg():
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    possible_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "ETI-SENTINEL" / "bin" / "ffmpeg.exe",
        Path(__file__).resolve().parent.parent / "bin" / "ffmpeg.exe",
        Path("C:/Users") / os.environ.get("USERNAME", "") / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
    ]

    for p in possible_paths:
        if p.exists():
            return str(p)

    return "ffmpeg"


def wait_for_mediamtx(host="localhost", port=8554, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def start_ffmpeg(rtsp_url, stream_key, ffmpeg_path=None, transcode: bool = False):
    if ffmpeg_path is None:
        ffmpeg_path = find_ffmpeg()

    if not wait_for_mediamtx():
        raise Exception("MediaMTX not ready at localhost:8554")

    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
    ]

    if transcode:
        cmd += [
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-g", "30",
            "-keyint_min", "30",
            "-sc_threshold", "0",
        ]
    else:
        cmd += [
            "-an",
            "-c", "copy",
        ]

    cmd += [
        "-f", "rtsp",
        f"rtsp://localhost:8554/{stream_key}"
    ]

    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
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

    return subprocess.Popen(cmd, **kwargs)
