import time
import logging
import os
from core.api_client import APIClient
from core.stream_manager import StreamManager
from core.state_cache import StateCache
from services.ffmpeg_service import start_ffmpeg


logger = logging.getLogger(__name__)


class StreamWorker:
    def __init__(self, api_client, stream_manager, cache):
        self.api = api_client
        self.manager = stream_manager
        self.cache = cache
        self.running = True

    def stop(self):
        self.running = False

    def _build_stream_key(self, device_id, channel):
        return f"{device_id}_ch{channel}"

    def _build_rtsp_url(self, url_template, username, password):
        if not url_template:
            return ""
        return url_template.replace("{username}", username).replace("{password}", password)

    def run(self):
        logger.info("[STREAM-WORKER] Started")
        cached_configs = self.cache.load()
        try:
            cooldown_seconds = float(os.getenv("STREAM_RESTART_COOLDOWN_SECONDS") or 20)
        except Exception:
            cooldown_seconds = 20.0
        force_transcode = str(os.getenv("STREAM_FORCE_TRANSCODE") or "").strip().lower() in {"1", "true", "yes", "on"}

        while self.running:
            try:
                try:
                    configs = self.api.get_rtsp_config()
                    self.cache.save(configs)
                except Exception as e:
                    logger.warning(f"[STREAM-WORKER] API failed, using cache: {e}")
                    configs = cached_configs

                if not configs:
                    time.sleep(10)
                    continue

                for device in configs:
                    device_id = int(device.get("device_id") or 0)
                    username = device.get("username") or ""
                    password = device.get("password") or ""
                    token = device.get("token") or ""
                    streams = device.get("streams") or []

                    for s in streams:
                        if not s.get("enabled"):
                            continue

                        channel = int(s.get("channel") or 0)
                        url_template = s.get("url") or ""
                        transport = s.get("transport", "tcp")
                        stream_name = s.get("name") or f"Channel {channel}"

                        if not url_template:
                            continue

                        stream_key = self._build_stream_key(device_id, channel)

                        if self.manager.is_running(stream_key):
                            continue

                        if not self.manager.can_retry(stream_key):
                            if stream_key in self.manager.get_all():
                                continue
                            logger.warning(f"[STREAM-WORKER] Max retries for {stream_key}, cleaning up")
                            self.manager.remove(stream_key)
                            continue
                        if not self.manager.can_start_now(stream_key, cooldown_seconds):
                            continue

                        rtsp_url = self._build_rtsp_url(url_template, username, password)
                        if not rtsp_url:
                            continue

                        logger.info(f"[STREAM-WORKER] Starting {stream_key} ({stream_name})")

                        try:
                            proc = start_ffmpeg(rtsp_url, stream_key, transcode=force_transcode)
                            time.sleep(2)

                            if proc.poll() is not None:
                                err = ""
                                try:
                                    if proc.stderr:
                                        raw = proc.stderr.read(2000) or b""
                                        err = raw.decode("utf-8", errors="replace").strip()
                                except Exception:
                                    err = ""
                                logger.error(f"[STREAM-WORKER] FFmpeg died immediately for {stream_key}")
                                if err:
                                    logger.error(f"[STREAM-WORKER] FFmpeg stderr: {err}")
                                try:
                                    proc = start_ffmpeg(rtsp_url, stream_key, transcode=True)
                                    time.sleep(2)
                                except Exception as e:
                                    logger.error(f"[STREAM-WORKER] FFmpeg fallback transcode failed for {stream_key}: {e}")
                                    self.manager.register(stream_key, proc, {
                                        "device_id": device_id,
                                        "channel": channel,
                                        "token": token,
                                        "name": stream_name,
                                        "transport": transport
                                    })
                                    self.manager.mark_failed(stream_key)
                                    continue
                                if proc.poll() is not None:
                                    err2 = ""
                                    try:
                                        if proc.stderr:
                                            raw2 = proc.stderr.read(2000) or b""
                                            err2 = raw2.decode("utf-8", errors="replace").strip()
                                    except Exception:
                                        err2 = ""
                                    logger.error(f"[STREAM-WORKER] FFmpeg died immediately (transcode) for {stream_key}")
                                    if err2:
                                        logger.error(f"[STREAM-WORKER] FFmpeg stderr (transcode): {err2}")
                                    self.manager.register(stream_key, proc, {
                                        "device_id": device_id,
                                        "channel": channel,
                                        "token": token,
                                        "name": stream_name,
                                        "transport": transport
                                    })
                                    self.manager.mark_failed(stream_key)
                                    continue

                            self.manager.register(stream_key, proc, {
                                "device_id": device_id,
                                "channel": channel,
                                "token": token,
                                "name": stream_name,
                                "transport": transport
                            })
                            self.manager.mark_running(stream_key)

                            if token:
                                self.api.send_push({
                                    "token": token,
                                    "device_id": device_id,
                                    "event_type": "videoloss_stopped",
                                    "channel": channel,
                                    "severity": "info",
                                    "description": f"Stream ativo ({stream_key})"
                                })
                                self.manager.mark_reported_online(stream_key)
                                logger.info(f"[STREAM-WORKER] Status reported ONLINE for {stream_key}")

                        except Exception as e:
                            logger.error(f"[STREAM-WORKER] Failed to start {stream_key}: {e}")

            except Exception as e:
                logger.error(f"[STREAM-WORKER] Loop error: {e}")

            time.sleep(10)

        logger.info("[STREAM-WORKER] Stopped")
