import requests
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.backoff import retry
from config import API_URL, TOKEN, CLIENT_ID


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


class APIClient:
    def __init__(self):
        self.session = get_session()
        self.headers = {"x-collector-key": TOKEN}
        self.params = {"client_id": CLIENT_ID}

    @retry(max_retries=3)
    def get_rtsp_config(self):
        r = self.session.get(
            f"{API_URL}/collector/rtsp-config",
            headers=self.headers,
            params=self.params,
            timeout=(10, 60)
        )
        r.raise_for_status()
        return r.json() or []

    @retry(max_retries=3)
    def get_devices(self):
        r = self.session.get(
            f"{API_URL}/collector/devices",
            headers=self.headers,
            params=self.params,
            timeout=(10, 60)
        )
        r.raise_for_status()
        return r.json() or []

    def send_push(self, payload):
        try:
            edge_push = (os.getenv("EDGE_PUSH_URL") or "").strip()
            url = edge_push or f"{API_URL}/push"
            r = self.session.post(
                url,
                json=payload,
                headers={"x-event-source": "edge-agent"},
                timeout=(5, 12)
            )
            return r.status_code == 200
        except Exception:
            return False

    def heartbeat(self, metrics):
        try:
            payload = {
                "client_id": CLIENT_ID,
                "metrics": metrics,
                "streams_active": []
            }
            self.session.post(
                f"{API_URL}/collector/heartbeat",
                json=payload,
                headers=self.headers,
                timeout=5
            )
        except Exception:
            pass
