import time
import logging
from threading import Lock
import os


logger = logging.getLogger(__name__)


class StreamManager:
    def __init__(self, max_retries=5):
        self.streams = {}
        self.max_retries = max_retries
        self._lock = Lock()
        self._retry_counts = {}
        self._last_fail_ts = {}

    def register(self, key, process, config):
        with self._lock:
            retries = int(self._retry_counts.get(key, 0) or 0)
            self.streams[key] = {
                "process": process,
                "config": config,
                "retries": retries,
                "last_start": time.time(),
                "last_status": "starting",
                "reported_online": False,
            }
        logger.info(f"[STREAM] Registered: {key}")

    def is_running(self, key):
        with self._lock:
            if key not in self.streams:
                return False
            proc = self.streams[key]["process"]
            return proc.poll() is None

    def mark_failed(self, key):
        with self._lock:
            n = int(self._retry_counts.get(key, 0) or 0) + 1
            self._retry_counts[key] = n
            self._last_fail_ts[key] = time.time()
            if key in self.streams:
                self.streams[key]["retries"] = n
                self.streams[key]["last_status"] = "failed"
            logger.warning(f"[STREAM] Failed {key} (retry {n})")

    def mark_running(self, key):
        with self._lock:
            if key in self.streams:
                self.streams[key]["last_status"] = "running"
                self.streams[key]["last_start"] = time.time()

    def mark_reported_online(self, key):
        with self._lock:
            if key in self.streams:
                self.streams[key]["reported_online"] = True

    def can_retry(self, key):
        with self._lock:
            mr = int(self.max_retries or 0)
            if mr <= 0:
                return True
            return int(self._retry_counts.get(key, 0) or 0) < mr

    def can_start_now(self, key, cooldown_seconds: float) -> bool:
        with self._lock:
            last = float(self._last_fail_ts.get(key) or 0)
            retries = int(self._retry_counts.get(key, 0) or 0)
        if not last:
            return True
        try:
            max_backoff = float(os.getenv("STREAM_RETRY_MAX_BACKOFF_SECONDS") or 60)
        except Exception:
            max_backoff = 60.0
        backoff = min(float(max_backoff), float(2 ** min(16, max(0, retries))))
        wait_s = max(float(cooldown_seconds or 0), float(backoff))
        return (time.time() - last) >= max(0.0, wait_s)

    def remove(self, key):
        with self._lock:
            if key in self.streams:
                try:
                    proc = self.streams[key]["process"]
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=3)
                except Exception:
                    pass
                del self.streams[key]
                logger.info(f"[STREAM] Removed: {key}")

    def get_all(self):
        with self._lock:
            return dict(self.streams)

    def get_configs(self):
        with self._lock:
            return {k: v["config"] for k, v in self.streams.items()}

    def cleanup_dead(self):
        with self._lock:
            dead = [k for k, v in self.streams.items() if v["process"].poll() is not None]
            for k in dead:
                del self.streams[k]
        return dead
