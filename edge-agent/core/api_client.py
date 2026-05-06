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


import time

# Compartilhado entre workers e API local para diagnostico
_LAST_HEARTBEAT_TS = 0.0

class APIClient:
    def __init__(self):
        self.session = get_session()
        self.headers = {"x-collector-key": TOKEN}
        self.params = {"client_id": CLIENT_ID}

    @staticmethod
    def get_last_heartbeat():
        return _LAST_HEARTBEAT_TS

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
        global _LAST_HEARTBEAT_TS
        # Heartbeat com retry local simples e timeout maior
        for attempt in range(2):
            try:
                payload = {
                    "client_id": CLIENT_ID,
                    "metrics": metrics,
                    "streams_active": [],
                    "gateway_ip": os.getenv("INTERNAL_GATEWAY_IP") or "127.0.0.1"
                }
                r = self.session.post(
                    f"{API_URL}/collector/heartbeat",
                    json=payload,
                    headers=self.headers,
                    timeout=15  # Aumentado de 5 para 15
                )
                if r.status_code == 200:
                    _LAST_HEARTBEAT_TS = time.time()
                    import logging
                    logging.info(f"[CLOUD] Sinal de vida (Heartbeat) aceito pela Railway.")
                    return True
                else:
                    import logging
                    logging.error(f"[CLOUD] Falha no sinal de vida: {r.status_code} - {r.text}")
            except Exception as e:
                import logging
                if attempt == 0:
                    logging.warning(f"[CLOUD] Retentativa de heartbeat após erro: {e}")
                    time.sleep(1)
                    continue
                logging.error(f"[CLOUD] Erro de conexão com a Railway (heartbeat): {e}")
        return False
