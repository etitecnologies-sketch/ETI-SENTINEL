import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import load_dotenv


def _sanitize(s) -> str:
    return str(s or "").strip().replace("`", "").replace("´", "").replace("“", "").replace("”", "").strip()


def _bool(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _base_url(url: str) -> str:
    u = _sanitize(url)
    if not u:
        return ""
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def _load_icon_image(here: Path):
    try:
        import PIL.Image
        import PIL.ImageDraw
        import PIL.ImageFont
    except Exception:
        return None

    candidates = [
        here / "tray_logo.png",
        here / "assets" / "tray_logo.png",
        here / ".state" / "tray_logo.png",
    ]
    for p in candidates:
        try:
            if p.exists():
                return PIL.Image.open(str(p)).convert("RGBA")
        except Exception:
            continue

    img = PIL.Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = PIL.ImageDraw.Draw(img)
    d.rounded_rectangle((28, 24, 228, 232), radius=44, outline=(59, 158, 255, 255), width=10, fill=(8, 18, 30, 255))
    d.ellipse((78, 92, 178, 192), outline=(59, 158, 255, 255), width=10)
    d.ellipse((112, 126, 144, 158), fill=(59, 158, 255, 255))
    return img


def main() -> None:
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env")
    env = os.environ.copy()

    try:
        import pystray
    except Exception:
        raise SystemExit("pystray não instalado (rode install_edge_agent.py novamente)")

    icon_image = _load_icon_image(here)
    if icon_image is None:
        raise SystemExit("Pillow não instalado (rode install_edge_agent.py novamente)")

    api_port = int(_sanitize(env.get("AGENT_API_PORT") or "8808") or 8808)
    local_url = f"http://127.0.0.1:{api_port}"
    cloud_url = _base_url(env.get("INGEST_API_URL") or "")

    state = {"running": True}

    def open_local():
        webbrowser.open(local_url)

    def open_cloud():
        if cloud_url:
            webbrowser.open(cloud_url)

    def quit_app(icon, item):
        state["running"] = False
        try:
            icon.stop()
        except Exception:
            pass

    def update_title(icon):
        while state["running"]:
            icon.title = "ETI SENTINEL"
            time.sleep(5)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir Painel Local", lambda: open_local()),
        pystray.MenuItem("Abrir Painel Cloud", lambda: open_cloud(), default=False, visible=lambda item: bool(cloud_url)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", quit_app),
    )

    icon = pystray.Icon("ETI_SENTINEL", icon_image, "ETI SENTINEL", menu)
    threading.Thread(target=update_title, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
