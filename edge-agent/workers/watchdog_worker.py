import time
import logging
from core.stream_manager import StreamManager


logger = logging.getLogger(__name__)


class WatchdogWorker:
    def __init__(self, stream_manager):
        self.manager = stream_manager
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        logger.info("[WATCHDOG] Started")

        while self.running:
            try:
                streams = self.manager.get_all()

                for key, data in streams.items():
                    proc = data.get("process")
                    config = data.get("config", {})
                    status = data.get("last_status", "unknown")

                    if proc is None:
                        continue

                    poll_result = proc.poll()

                    if poll_result is not None:
                        logger.warning(f"[WATCHDOG] Stream died: {key} (exit code: {poll_result})")
                        self.manager.mark_failed(key)
                        self.manager.remove(key)

                        token = config.get("token")
                        device_id = config.get("device_id")
                        channel = config.get("channel")

                        if token and device_id and channel:
                            from core.api_client import APIClient
                            api = APIClient()
                            api.send_push({
                                "token": token,
                                "device_id": device_id,
                                "event_type": "videoloss_started",
                                "channel": channel,
                                "severity": "warn",
                                "description": f"Stream morreu - watchdog detectou (key: {key})"
                            })

            except Exception as e:
                logger.error(f"[WATCHDOG] Error: {e}")

            time.sleep(5)

        logger.info("[WATCHDOG] Stopped")
