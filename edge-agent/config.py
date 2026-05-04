import os
import sys
from pathlib import Path
from urllib.parse import urlparse

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))

from dotenv import load_dotenv
load_dotenv(here / ".env", override=True)

def _sanitize_value(v: str) -> str:
    s = (v or "").strip()
    return s.strip("`").strip('"').strip("'").strip()


def _sanitize_base_url(v: str) -> str:
    s = _sanitize_value(v)
    if not s:
        return s
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "https://" + s
    s = s.rstrip("/")
    p = urlparse(s)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise ValueError("INGEST_API_URL inválido")
    return s


def _safe_int(v: str, default: int) -> int:
    try:
        return int(_sanitize_value(v) or default)
    except Exception:
        return default


API_URL = _sanitize_base_url(os.getenv("INGEST_API_URL", "https://eti-sentinel-production.up.railway.app"))
TOKEN = _sanitize_value(os.getenv("COLLECTOR_KEY", ""))
CLIENT_ID = _safe_int(os.getenv("CLIENT_ID", ""), 1)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 10))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", 15))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 5))

CACHE_FILE = here / ".state" / "cache.json"

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
MEDIAMTX_PATH = os.getenv("MEDIAMTX_PATH", "")

EDGE_PUSH_URL = os.getenv("EDGE_PUSH_URL", "")
