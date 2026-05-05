import logging
import time
import os
import subprocess
import psutil
from typing import Dict

logger = logging.getLogger(__name__)


class WatchdogWorker:
    def __init__(self, stream_manager) -> None:
        self.manager = stream_manager
        self.running = True

    def stop(self) -> None:
        self.running = False

    def _cleanup_zombies(self):
        """Mata processos FFmpeg órfãos ou travados que não estão no manager"""
        try:
            active_pids = set()
            for stream in self.manager.streams.values():
                if stream.get("process") and stream["process"].poll() is None:
                    active_pids.add(stream["process"].pid)

            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if "ffmpeg" in proc.info['name'].lower():
                        if proc.info['pid'] not in active_pids:
                            # Se o processo tem mais de 5 minutos e não é monitorado, mata
                            create_time = proc.create_time()
                            if (time.time() - create_time) > 300:
                                logger.warning(f"[Watchdog] Limpando FFmpeg zumbi: PID {proc.info['pid']}")
                                proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"[Watchdog] Erro na limpeza de zumbis: {e}")

    def run(self) -> None:
        logger.info("[Watchdog] Started")
        last_cleanup = 0
        while self.running:
            try:
                # Limpeza de zumbis a cada 10 minutos
                if (time.time() - last_cleanup) > 600:
                    self._cleanup_zombies()
                    last_cleanup = time.time()

                for stream_key, stream in list(self.manager.streams.items()):
                    if stream.get("process") and stream["process"].poll() is not None:
                        logger.warning(f"[Watchdog] Stream {stream_key} died. Restarting...")
                        self.manager.restart_stream(stream_key)
            except Exception as e:
                logger.error(f"[Watchdog] Error: {e}")

            time.sleep(10)
        logger.info("[Watchdog] Stopped")
