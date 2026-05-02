import base64
import logging
import os
import time
from typing import Any, Dict, Optional, Set, Tuple

import requests


logger = logging.getLogger(__name__)


def _sanitize(s: Any) -> str:
    return str(s or "").strip()


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        n = int(v)
        return n
    except Exception:
        return None


def _parse_csv_set(s: str) -> Set[str]:
    raw = _sanitize(s)
    if not raw:
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


class AIWorker:
    def __init__(self, stream_manager) -> None:
        self.manager = stream_manager
        self.running = True
        self._caps: Dict[str, Any] = {}
        self._cap_fail_ts: Dict[str, float] = {}
        self._last_frame_ts: Dict[str, float] = {}
        self._last_event_ts: Dict[Tuple[int, int, str], float] = {}
        self._last_debug_ts: Dict[str, float] = {}
        self._sess = requests.Session()

        self._model = None
        self._cv2 = None

    def stop(self) -> None:
        self.running = False

    def _ensure_deps(self) -> bool:
        if self._cv2 is None:
            try:
                import cv2  # type: ignore

                self._cv2 = cv2
            except Exception as e:
                logger.warning(f"[AI] OpenCV (cv2) not available: {e}")
                return False
        if self._model is None:
            try:
                from ultralytics import YOLO  # type: ignore

                model_name = _sanitize(os.getenv("AI_MODEL") or "yolov8n.pt")
                self._model = YOLO(model_name)
            except Exception as e:
                logger.warning(f"[AI] ultralytics/YOLO not available: {e}")
                return False
        return True

    def _source_url(self, stream_key: str) -> str:
        tmpl = _sanitize(os.getenv("AI_SOURCE_URL_TEMPLATE") or "rtsp://127.0.0.1:8554/{stream_key}")
        return tmpl.replace("{stream_key}", stream_key)

    def _should_analyze(self, stream_key: str, now: float) -> bool:
        try:
            every_s = float(os.getenv("AI_FRAME_EVERY_SECONDS") or 1.0)
        except Exception:
            every_s = 1.0
        last = float(self._last_frame_ts.get(stream_key) or 0.0)
        if last and (now - last) < max(0.1, every_s):
            return False
        self._last_frame_ts[stream_key] = now
        return True

    def _cap(self, stream_key: str):
        cv2 = self._cv2
        if cv2 is None:
            return None
        cap = self._caps.get(stream_key)
        if cap is not None:
            return cap
        now = time.time()
        last_fail = float(self._cap_fail_ts.get(stream_key) or 0.0)
        try:
            backoff_s = float(os.getenv("AI_RECONNECT_BACKOFF_SECONDS") or 5)
        except Exception:
            backoff_s = 5.0
        if last_fail and (now - last_fail) < max(1.0, backoff_s):
            return None
        url = self._source_url(stream_key)
        try:
            cap = cv2.VideoCapture(url)
        except Exception:
            cap = None
        if not cap or not cap.isOpened():
            self._cap_fail_ts[stream_key] = now
            try:
                if cap:
                    cap.release()
            except Exception:
                pass
            return None
        self._caps[stream_key] = cap
        return cap

    def _release_cap(self, stream_key: str) -> None:
        cap = self._caps.pop(stream_key, None)
        try:
            if cap:
                cap.release()
        except Exception:
            pass

    def _encode_snapshot_b64(self, frame: Any) -> str:
        if not _bool(os.getenv("AI_SEND_SNAPSHOT") or "0"):
            return ""
        cv2 = self._cv2
        if cv2 is None or frame is None:
            return ""
        try:
            max_w = int(os.getenv("AI_SNAPSHOT_MAX_WIDTH") or 640)
        except Exception:
            max_w = 640
        try:
            q0 = int(os.getenv("AI_SNAPSHOT_JPEG_QUALITY") or 75)
        except Exception:
            q0 = 75
        try:
            max_bytes = int(os.getenv("AI_SNAPSHOT_MAX_BYTES") or 400000)
        except Exception:
            max_bytes = 400000

        try:
            h, w = frame.shape[:2]
            if max_w > 0 and w > max_w:
                scale = float(max_w) / float(w)
                nh = max(1, int(h * scale))
                frame = cv2.resize(frame, (int(max_w), nh))
        except Exception:
            pass

        for q in [q0, 60, 45]:
            try:
                ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(q)])
                if not ok:
                    continue
                b = buf.tobytes()
                if not b:
                    continue
                if max_bytes > 0 and len(b) > max_bytes:
                    continue
                return base64.b64encode(b).decode("ascii")
            except Exception:
                continue
        return ""

    def _push_event(
        self,
        token: str,
        device_id: int,
        channel: int,
        event_type: str,
        severity: str,
        description: str,
        snapshot_jpg_b64: str = "",
    ) -> bool:
        url = _sanitize(os.getenv("EDGE_PUSH_URL") or "http://127.0.0.1:8808/api/push")
        if not url:
            return False
        payload: Dict[str, Any] = {
            "token": token or "x",
            "device_id": int(device_id),
            "channel": int(channel),
            "event_type": _sanitize(event_type),
            "severity": _sanitize(severity) or "info",
        }
        if description:
            payload["description"] = _sanitize(description)[:400]
        if snapshot_jpg_b64:
            payload["snapshot_jpg_b64"] = snapshot_jpg_b64
        try:
            r = self._sess.post(url, json=payload, headers={"x-event-source": "ai"}, timeout=(3, 8))
            return r.status_code == 200
        except Exception:
            return False

    def _cooldown_ok(self, device_id: int, channel: int, cls_name: str, now: float) -> bool:
        try:
            cooldown_s = float(os.getenv("AI_EVENT_COOLDOWN_SECONDS") or 120)
        except Exception:
            cooldown_s = 120.0
        k = (int(device_id), int(channel), cls_name)
        last = float(self._last_event_ts.get(k) or 0.0)
        if last and (now - last) < max(1.0, cooldown_s):
            return False
        self._last_event_ts[k] = now
        return True

    def _class_to_event(self, cls_name: str) -> str:
        prefix = _sanitize(os.getenv("AI_EVENT_PREFIX") or "ai_")
        suffix = _sanitize(os.getenv("AI_EVENT_SUFFIX") or "_detected")
        safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in cls_name.strip().lower())
        safe = "_".join([p for p in safe.split("_") if p])
        return f"{prefix}{safe}{suffix}"

    def _severity_for(self, cls_name: str) -> str:
        raw = _sanitize(os.getenv("AI_SEVERITY_MAP") or "person=warn,car=info,motorcycle=info,bus=info,truck=info")
        for part in raw.split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k.strip().lower() == cls_name.strip().lower():
                return v.strip().lower() or "info"
        return "info"

    def _allowed_device(self, device_id: int) -> bool:
        allowed = _parse_csv_set(os.getenv("AI_DEVICE_IDS") or "")
        if not allowed:
            return True
        return str(int(device_id)) in allowed

    def _allowed_class(self, cls_name: str) -> bool:
        allowed = _parse_csv_set(os.getenv("AI_CLASSES") or "person,car,motorcycle")
        if not allowed:
            return True
        return cls_name.strip().lower() in allowed

    def run(self) -> None:
        if not _bool(os.getenv("ENABLE_AI_ANALYTICS") or "0"):
            return
        if not self._ensure_deps():
            return

        logger.info("[AI] Started")
        debug = _bool(os.getenv("AI_DEBUG_LOG") or "0")

        try:
            conf_th = float(os.getenv("AI_CONF_THRESHOLD") or 0.6)
        except Exception:
            conf_th = 0.6
        try:
            yolo_conf = float(os.getenv("AI_YOLO_CONF") or 0.15)
        except Exception:
            yolo_conf = 0.15
        try:
            yolo_iou = float(os.getenv("AI_YOLO_IOU") or 0.45)
        except Exception:
            yolo_iou = 0.45
        try:
            img_size = int(os.getenv("AI_IMAGE_SIZE") or 640)
        except Exception:
            img_size = 640
        try:
            dbg_every = float(os.getenv("AI_DEBUG_EVERY_SECONDS") or 10)
        except Exception:
            dbg_every = 10.0

        cv2 = self._cv2
        model = self._model
        if cv2 is None or model is None:
            return

        while self.running:
            try:
                active = self.manager.get_configs() or {}
                active_keys = set(active.keys())
                for k in list(self._caps.keys()):
                    if k not in active_keys:
                        self._release_cap(k)

                now = time.time()
                for stream_key, cfg in active.items():
                    try:
                        did = _as_int(cfg.get("device_id")) or 0
                        ch = _as_int(cfg.get("channel")) or 0
                        token = _sanitize(cfg.get("token") or "")
                        if did <= 0:
                            continue
                        if not self._allowed_device(did):
                            continue
                        if not self._should_analyze(stream_key, now):
                            continue

                        cap = self._cap(stream_key)
                        if cap is None:
                            if debug:
                                last_dbg = float(self._last_debug_ts.get(stream_key) or 0.0)
                                if (now - last_dbg) >= max(1.0, dbg_every):
                                    self._last_debug_ts[stream_key] = now
                                    logger.info(f"[AI] {stream_key} cap not ready (backoff)")
                                    try:
                                        self._push_event(
                                            "x",
                                            did,
                                            ch,
                                            "ai_debug",
                                            "info",
                                            f"stream={stream_key} cap_not_ready backoff",
                                            snapshot_jpg_b64="",
                                        )
                                    except Exception:
                                        pass
                            continue
                        ok, frame = cap.read()
                        if not ok or frame is None:
                            self._release_cap(stream_key)
                            self._cap_fail_ts[stream_key] = time.time()
                            if debug:
                                last_dbg = float(self._last_debug_ts.get(stream_key) or 0.0)
                                now2 = time.time()
                                if (now2 - last_dbg) >= max(1.0, dbg_every):
                                    self._last_debug_ts[stream_key] = now2
                                    logger.info(f"[AI] {stream_key} frame read failed, reconnecting")
                                    try:
                                        self._push_event(
                                            "x",
                                            did,
                                            ch,
                                            "ai_debug",
                                            "info",
                                            f"stream={stream_key} frame_read_failed reconnecting",
                                            snapshot_jpg_b64="",
                                        )
                                    except Exception:
                                        pass
                            continue

                        try:
                            res = model.predict(frame, imgsz=img_size, conf=yolo_conf, iou=yolo_iou, verbose=False)
                        except Exception as e:
                            if debug:
                                logger.warning(f"[AI] {stream_key} model.predict failed: {e}")
                            continue
                        if not res:
                            continue
                        r0 = res[0]
                        names = getattr(r0, "names", {}) or {}
                        boxes = getattr(r0, "boxes", None)
                        if boxes is None:
                            continue

                        any_fired = False
                        det_total = 0
                        det_pass = 0
                        best_conf = 0.0
                        best_cls = ""
                        det_conf_ok = 0
                        det_class_ok = 0
                        try:
                            for b in boxes:
                                det_total += 1
                                try:
                                    cls_idx = int(b.cls[0]) if hasattr(b, "cls") else int(getattr(b, "cls", 0))
                                except Exception:
                                    continue
                                try:
                                    conf = float(b.conf[0]) if hasattr(b, "conf") else float(getattr(b, "conf", 0.0))
                                except Exception:
                                    conf = 0.0
                                try:
                                    if conf > float(best_conf):
                                        best_conf = float(conf)
                                        best_cls = _sanitize(names.get(cls_idx) or str(cls_idx))
                                except Exception:
                                    pass
                                if conf < max(0.0, min(1.0, conf_th)):
                                    continue
                                det_conf_ok += 1
                                cls_name = _sanitize(names.get(cls_idx) or str(cls_idx))
                                if not cls_name:
                                    continue
                                if not self._allowed_class(cls_name):
                                    continue
                                det_class_ok += 1
                                det_pass += 1
                                now_evt = time.time()
                                if not self._cooldown_ok(did, ch, cls_name.lower(), now_evt):
                                    continue
                                ev_type = self._class_to_event(cls_name)
                                sev = self._severity_for(cls_name)
                                desc = f"{cls_name} conf={conf:.2f} stream={stream_key}"
                                snap = self._encode_snapshot_b64(frame)
                                ok_push = self._push_event(token, did, ch, ev_type, sev, desc, snapshot_jpg_b64=snap)
                                any_fired = any_fired or ok_push
                        except Exception:
                            any_fired = False

                        if debug:
                            last_dbg = float(self._last_debug_ts.get(stream_key) or 0.0)
                            now2 = time.time()
                            if any_fired:
                                logger.info(f"[AI] Fired events for {stream_key} (det_total={det_total} conf_ok={det_conf_ok} class_ok={det_class_ok} pass={det_pass} conf_th={conf_th} yolo_conf={yolo_conf} best={best_cls}:{best_conf:.2f})")
                                self._last_debug_ts[stream_key] = now2
                            elif (now2 - last_dbg) >= max(1.0, dbg_every):
                                self._last_debug_ts[stream_key] = now2
                                logger.info(f"[AI] {stream_key} analyzed (det_total={det_total} conf_ok={det_conf_ok} class_ok={det_class_ok} pass={det_pass} conf_th={conf_th} yolo_conf={yolo_conf} best={best_cls}:{best_conf:.2f})")
                            try:
                                if (now2 - last_dbg) >= max(1.0, dbg_every):
                                    self._push_event(
                                        "x",
                                        did,
                                        ch,
                                        "ai_debug",
                                        "info",
                                        f"stream={stream_key} det_total={det_total} conf_ok={det_conf_ok} class_ok={det_class_ok} pass={det_pass} conf_th={conf_th} yolo_conf={yolo_conf} best={best_cls}:{best_conf:.2f}",
                                        snapshot_jpg_b64="",
                                    )
                            except Exception:
                                pass

                    except Exception:
                        if debug:
                            logger.warning(f"[AI] {stream_key} loop error", exc_info=True)
                        continue

            except Exception:
                pass

            try:
                sleep_s = float(os.getenv("AI_LOOP_SLEEP_SECONDS") or 0.2)
            except Exception:
                sleep_s = 0.2
            time.sleep(max(0.05, sleep_s))

        for k in list(self._caps.keys()):
            self._release_cap(k)
        logger.info("[AI] Stopped")
