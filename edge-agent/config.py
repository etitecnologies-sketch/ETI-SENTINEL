import os
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))

from dotenv import load_dotenv
load_dotenv(here / ".env", override=True)

API_URL = os.getenv("INGEST_API_URL", "https://eti-sentinel-production.up.railway.app")
TOKEN = os.getenv("COLLECTOR_KEY", "")
CLIENT_ID = int(os.getenv("CLIENT_ID", 1) or 1)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 10))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", 15))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 5))

CACHE_FILE = here / ".state" / "cache.json"

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
MEDIAMTX_PATH = os.getenv("MEDIAMTX_PATH", "")

EDGE_PUSH_URL = os.getenv("EDGE_PUSH_URL", "")
