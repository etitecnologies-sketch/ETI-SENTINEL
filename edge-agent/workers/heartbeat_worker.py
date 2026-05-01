import time
import logging
from core.api_client import APIClient
from services.metrics_service import get_metrics


logger = logging.getLogger(__name__)


class HeartbeatWorker:
    def __init__(self, api_client, interval=15):
        self.api = api_client
        self.interval = interval
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        logger.info("[HEARTBEAT] Started")

        while self.running:
            try:
                metrics = get_metrics()
                self.api.heartbeat(metrics)
                logger.debug(f"[HEARTBEAT] Sent: cpu={metrics['cpu_percent']:.1f}% ram={metrics['ram_percent']:.1f}%")
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error: {e}")

            time.sleep(self.interval)

        logger.info("[HEARTBEAT] Stopped")
