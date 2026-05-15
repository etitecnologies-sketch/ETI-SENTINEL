import base64
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, Optional, Set, Tuple

import requests

try:
    from workers.ai_analytics import (
        ZoneIntrusionDetector,
        LineCrossingDetector,
        PeopleCounter,
        extract_detections,
    )
    _ANALYTICS_AVAILABLE = True
except ImportError:
    try:
        from ai_analytics import (
            ZoneIntrusionDetector,
            LineCrossingDetector,
            PeopleCounter,
            extract_detections,
        )
        _ANALYTICS_AVAILABLE = True
    except ImportError:
        _ANALYTICS_AVAILABLE = False


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
        self._confirm_state: Dict[Tuple[int, int, str], Dict[str, Any]] = {}
        self._sess = requests.Session()

        self._model = None
        self._cv2 = None

        if _ANALYTICS_AVAILABLE:
            self._zone_detector = ZoneIntrusionDetector()
            self._line_detector = LineCrossingDetector()
            self._people_counter = PeopleCounter()
        else:
            self._zone_detector = None
            self._line_detector = None
            self._people_counter = None

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

                model_name = _sanitize(os.getenv("AI_MODEL") or "yolov8s.pt")
                self._model = YOLO(model_name)
                
                # Tenta habilitar aceleração de hardware automaticamente
                try:
                    import torch
                    if torch.cuda.is_available():
                        self._model.to('cuda')
                        logger.info("[AI] Aceleração NVIDIA CUDA habilitada.")
                    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                        self._model.to('mps')
                        logger.info("[AI] Aceleração Apple M-Series (MPS) habilitada.")
                except Exception:
                    logger.info("[AI] Rodando em modo CPU (Padrão).")
                    
            except Exception as e:
                logger.warning(f"[AI] ultralytics/YOLO not available: {e}")
                return False
        return True

    def _source_url(self, stream_key: str) -> str:
        tmpl = _sanitize(os.getenv("AI_SOURCE_URL_TEMPLATE") or "rtsp://127.0.0.1:8554/{stream_key}")
        return tmpl.replace("{stream_key}", stream_key)

    def _should_analyze(self, stream_key: str, now: float) -> bool:
        try:
            every_s = float(os.getenv("AI_FRAME_EVERY_SECONDS") or 0.5)
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
            if hasattr(cv2, "CAP_FFMPEG"):
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            else:
                cap = cv2.VideoCapture(url)
            try:
                if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
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

    def _encode_snapshot_b64(self, frame: Any, stream_key: str = "") -> str:
        if not _bool(os.getenv("AI_SEND_SNAPSHOT") or "0"):
            return ""

        mode = _sanitize(os.getenv("AI_SNAPSHOT_MODE") or "").strip().lower()
        if not mode:
            ff = _sanitize(os.getenv("INTERNAL_FFMPEG_PATH") or "").strip()
            if ff and (shutil.which(ff) or os.path.exists(ff)):
                mode = "ffmpeg"
            else:
                mode = "opencv"

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

        if mode in {"ffmpeg", "ffmpeg_only"}:
            return self._encode_snapshot_ffmpeg_b64(stream_key=stream_key, max_w=max_w, max_bytes=max_bytes, quality=q0)

        if mode in {"ffmpeg_fallback", "fallback", "opencv_fallback"}:
            b64 = self._encode_snapshot_opencv_b64(frame=frame, max_w=max_w, max_bytes=max_bytes, quality=q0)
            if b64:
                return b64
            return self._encode_snapshot_ffmpeg_b64(stream_key=stream_key, max_w=max_w, max_bytes=max_bytes, quality=q0)

        return self._encode_snapshot_opencv_b64(frame=frame, max_w=max_w, max_bytes=max_bytes, quality=q0)

    def _encode_snapshot_opencv_b64(self, frame: Any, max_w: int, max_bytes: int, quality: int) -> str:
        cv2 = self._cv2
        if cv2 is None or frame is None:
            return ""

        try:
            h, w = frame.shape[:2]
            if max_w > 0 and w > max_w:
                scale = float(max_w) / float(w)
                nh = max(1, int(h * scale))
                frame = cv2.resize(frame, (int(max_w), nh))
        except Exception:
            pass

        for q in [quality, 60, 45]:
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

    def _encode_snapshot_ffmpeg_b64(self, stream_key: str, max_w: int, max_bytes: int, quality: int) -> str:
        url = self._source_url(stream_key)
        if not url:
            return ""

        ffmpeg = _sanitize(os.getenv("INTERNAL_FFMPEG_PATH") or "ffmpeg")
        ffmpeg_ok = shutil.which(ffmpeg) or os.path.exists(ffmpeg)
        if not ffmpeg_ok:
            return ""

        try:
            timeout_s = float(os.getenv("AI_SNAPSHOT_FFMPEG_TIMEOUT_SECONDS") or 4)
        except Exception:
            timeout_s = 4.0
        try:
            stimeout_ms = int(os.getenv("AI_SNAPSHOT_FFMPEG_STIMEOUT_MS") or 2000)
        except Exception:
            stimeout_ms = 2000

        q = max(2, min(31, int((100 - max(1, min(100, int(quality)))) / 4) + 2))
        vf = None
        if max_w and int(max_w) > 0:
            vf = f"scale=min({int(max_w)}\\,iw):-2"

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-stimeout",
            str(max(1, int(stimeout_ms)) * 1000),
            "-i",
            url,
        ]
        if vf:
            cmd += ["-vf", vf]
        cmd += [
            "-an",
            "-sn",
            "-dn",
            "-frames:v",
            "1",
            "-q:v",
            str(q),
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]

        try:
            p = subprocess.run(cmd, capture_output=True, timeout=max(1.0, float(timeout_s)))
            if p.returncode != 0:
                return ""
            b = p.stdout or b""
            if not b:
                return ""
            if max_bytes > 0 and len(b) > int(max_bytes):
                return ""
            return base64.b64encode(b).decode("ascii")
        except Exception:
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
        extra: Optional[Dict[str, Any]] = None,
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
            if isinstance(extra, dict):
                for k, v in extra.items():
                    kk = _sanitize(k)
                    if not kk:
                        continue
                    if kk in payload:
                        continue
                    if isinstance(v, (int, float)):
                        payload[kk] = v
                    elif isinstance(v, str) and v:
                        payload[kk] = _sanitize(v)[:200]
                    elif kk.lower() == "tags" and isinstance(v, list):
                        tags = []
                        for t in v:
                            if isinstance(t, str) and t.strip():
                                tags.append(t.strip())
                        if tags:
                            payload["tags"] = tags[:20]
        except Exception:
            pass
        try:
            r = self._sess.post(url, json=payload, headers={"x-event-source": "ai"}, timeout=(3, 8))
            return r.status_code == 200
        except Exception:
            return False

    def _cooldown_ok(self, device_id: int, channel: int, cls_name: str, now: float) -> bool:
        try:
            cooldown_s = float(os.getenv("AI_EVENT_COOLDOWN_SECONDS") or 45)
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

    def _group_for_class(self, cls_name: str) -> str:
        human = _parse_csv_set(os.getenv("AI_GROUP_HUMAN_CLASSES") or "person")
        vehicle = _parse_csv_set(os.getenv("AI_GROUP_VEHICLE_CLASSES") or "car,motorcycle,bus,truck")
        key = cls_name.strip().lower()
        if key in human:
            return "human"
        if key in vehicle:
            return "vehicle"
        return ""

    def _event_for(self, cls_name: str) -> str:
        group = self._group_for_class(cls_name)
        if group == "human":
            return "ai_human_detected"
        if group == "vehicle":
            return "ai_vehicle_detected"
        return self._class_to_event(cls_name)

    def _severity_for(self, cls_name: str) -> str:
        group = self._group_for_class(cls_name)
        if group == "human":
            return "warn"
        if group == "vehicle":
            return "info"
        raw = _sanitize(os.getenv("AI_SEVERITY_MAP") or "person=warn,car=info,motorcycle=info,bus=info,truck=info")
        for part in raw.split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k.strip().lower() == cls_name.strip().lower():
                return v.strip().lower() or "info"
        return "info"

    def _confirm_ok(self, device_id: int, channel: int, key: str, now: float) -> bool:
        try:
            need = int(os.getenv("AI_CONFIRM_FRAMES") or 1)
        except Exception:
            need = 2
        try:
            win = float(os.getenv("AI_CONFIRM_WINDOW_SECONDS") or 1.0)
        except Exception:
            win = 2.0
        need = max(1, int(need))
        win = max(0.2, float(win))

        k = (int(device_id), int(channel), key)
        st = self._confirm_state.get(k)
        if not st:
            self._confirm_state[k] = {"first_ts": now, "count": 1}
            return need <= 1
        first_ts = float(st.get("first_ts") or 0.0)
        if first_ts and (now - first_ts) > win:
            self._confirm_state[k] = {"first_ts": now, "count": 1}
            return need <= 1
        st["count"] = int(st.get("count") or 0) + 1
        self._confirm_state[k] = st
        if int(st["count"]) >= need:
            self._confirm_state.pop(k, None)
            return True
        return False

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

    def _parse_kv_float_map(self, raw: str) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for part in str(raw or "").split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            k = k.strip().lower()
            if not k:
                continue
            try:
                out[k] = float(v.strip())
            except Exception:
                continue
        return out

    def _conf_threshold_for(self, cls_name: str, base: float) -> float:
        c = cls_name.strip().lower()
        raw = os.getenv("AI_CLASS_THRESHOLDS") or ""
        m = self._parse_kv_float_map(raw)
        if c in m:
            return max(0.0, min(1.0, float(m[c])))
        g = self._group_for_class(c)
        if g == "human":
            try:
                return max(0.0, min(1.0, float(os.getenv("AI_PERSON_CONF_THRESHOLD") or base)))
            except Exception:
                return max(0.0, min(1.0, float(base)))
        if g == "vehicle":
            try:
                return max(0.0, min(1.0, float(os.getenv("AI_VEHICLE_CONF_THRESHOLD") or base)))
            except Exception:
                return max(0.0, min(1.0, float(base)))
        return max(0.0, min(1.0, float(base)))

    def _min_area_ratio_for(self, cls_name: str) -> float:
        c = cls_name.strip().lower()
        raw = os.getenv("AI_CLASS_MIN_AREA_RATIO") or ""
        m = self._parse_kv_float_map(raw)
        if c in m:
            return max(0.0, float(m[c]))
        try:
            return max(0.0, float(os.getenv("AI_MIN_AREA_RATIO") or 0.0))
        except Exception:
            return 0.0

    def _run_analytics(
        self,
        stream_key: str,
        token: str,
        device_id: int,
        channel: int,
        cfg: Dict[str, Any],
        boxes: Any,
        names: Dict[int, str],
        frame: Any,
        fw: int,
        fh: int,
        conf_th: float,
    ) -> None:
        """Roda analiticos avancados: zona de intrusao, linha virtual e contagem."""
        if not _ANALYTICS_AVAILABLE:
            return

        try:
            allowed = _parse_csv_set(os.getenv("AI_CLASSES") or "person,car,motorcycle")
            detections = extract_detections(boxes, names, fw, fh, allowed or None, conf_th * 0.8)
        except Exception:
            return

        tags = list(cfg.get("tags") or [])
        now = time.time()

        # ---- Zona de Intrusao ----------------------------------------
        if self._zone_detector and bool(os.getenv("AI_ZONES")):
            for det in detections:
                cls_name = det["cls_name"]
                try:
                    if self._zone_detector.check(stream_key, cls_name, det["cx_norm"], det["cy_norm"]):
                        cooldown_ok = self._cooldown_ok(device_id, channel, "ai_zone_intrusion:" + cls_name, now)
                        if cooldown_ok:
                            snap = self._encode_snapshot_b64(frame, stream_key=stream_key)
                            self._push_event(
                                token, device_id, channel,
                                "ai_zone_intrusion",
                                "warn",
                                f"{cls_name} entrou na zona monitorada (conf={det['conf']:.2f})",
                                snapshot_jpg_b64=snap,
                                extra={
                                    "ai_class": cls_name,
                                    "ai_conf": det["conf"],
                                    "ai_cx": det["cx_norm"],
                                    "ai_cy": det["cy_norm"],
                                    "tags": tags + ["ai_zone"],
                                    "device_type": cfg.get("device_type") or "",
                                },
                            )
                except Exception:
                    continue

        # ---- Cruzamento de Linha Virtual ------------------------------
        if self._line_detector and bool(os.getenv("AI_CROSSING_LINES")):
            for det in detections:
                cls_name = det["cls_name"]
                try:
                    if self._line_detector.check_all_lines(stream_key, cls_name, det["cx_norm"], det["cy_norm"]):
                        cooldown_ok = self._cooldown_ok(device_id, channel, "ai_line_crossing:" + cls_name, now)
                        if cooldown_ok:
                            snap = self._encode_snapshot_b64(frame, stream_key=stream_key)
                            self._push_event(
                                token, device_id, channel,
                                "ai_line_crossing",
                                "warn",
                                f"{cls_name} cruzou linha virtual (conf={det['conf']:.2f})",
                                snapshot_jpg_b64=snap,
                                extra={
                                    "ai_class": cls_name,
                                    "ai_conf": det["conf"],
                                    "ai_cx": det["cx_norm"],
                                    "ai_cy": det["cy_norm"],
                                    "tags": tags + ["ai_line"],
                                    "device_type": cfg.get("device_type") or "",
                                },
                            )
                except Exception:
                    continue

        # ---- Contagem de Pessoas --------------------------------------
        if self._people_counter:
            person_count = sum(1 for d in detections if d["cls_name"] == "person")
            try:
                crowd_alert, send_metric = self._people_counter.process(stream_key, person_count)
                if crowd_alert:
                    max_count = int(os.getenv("AI_PEOPLE_MAX_COUNT") or 0)
                    self._push_event(
                        token, device_id, channel,
                        "ai_crowd_alert",
                        "warn",
                        f"Lotacao detectada: {person_count} pessoas (limite: {max_count})",
                        snapshot_jpg_b64=self._encode_snapshot_b64(frame, stream_key=stream_key),
                        extra={
                            "ai_people_count": person_count,
                            "ai_people_limit": max_count,
                            "tags": tags + ["ai_count"],
                            "device_type": cfg.get("device_type") or "",
                        },
                    )
                if send_metric and person_count > 0:
                    self._push_event(
                        token, device_id, channel,
                        "ai_people_count",
                        "info",
                        f"Contagem periodica: {person_count} pessoa(s) em cena",
                        extra={
                            "ai_people_count": person_count,
                            "tags": tags,
                            "device_type": cfg.get("device_type") or "",
                        },
                    )
            except Exception:
                pass

    def run(self) -> None:
        if not _bool(os.getenv("ENABLE_AI_ANALYTICS") or "0"):
            return
        if not self._ensure_deps():
            return

        logger.info("[AI] Started")
        debug = _bool(os.getenv("AI_DEBUG_LOG") or "0")

        try:
            conf_th = float(os.getenv("AI_CONF_THRESHOLD") or 0.55)
        except Exception:
            conf_th = 0.6
        try:
            yolo_conf = float(os.getenv("AI_YOLO_CONF") or 0.2)
        except Exception:
            yolo_conf = 0.15
        try:
            yolo_iou = float(os.getenv("AI_YOLO_IOU") or 0.45)
        except Exception:
            yolo_iou = 0.45
        try:
            img_size = int(os.getenv("AI_IMAGE_SIZE") or 768)
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

                        frame_area = 0.0
                        try:
                            fh, fw = frame.shape[:2]
                            if fw and fh:
                                frame_area = float(int(fw) * int(fh))
                        except Exception:
                            frame_area = 0.0

                        any_fired = False
                        det_total = 0
                        det_pass = 0
                        best_conf = 0.0
                        best_cls = ""
                        det_conf_ok = 0
                        det_class_ok = 0
                        best_by_event: Dict[str, Tuple[float, str]] = {}
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
                                cls_name = _sanitize(names.get(cls_idx) or str(cls_idx))
                                if not cls_name:
                                    continue
                                thr = self._conf_threshold_for(cls_name, conf_th)
                                if conf < float(thr):
                                    continue
                                det_conf_ok += 1
                                if not self._allowed_class(cls_name):
                                    continue
                                min_area_ratio = float(self._min_area_ratio_for(cls_name) or 0.0)
                                if frame_area > 0.0 and min_area_ratio > 0.0:
                                    try:
                                        xyxy = getattr(b, "xyxy", None)
                                        if xyxy is not None:
                                            if hasattr(xyxy, "tolist"):
                                                xy = xyxy[0].tolist() if hasattr(xyxy, "__len__") else xyxy.tolist()
                                            else:
                                                xy = list(xyxy[0]) if hasattr(xyxy, "__len__") else list(xyxy)
                                            if len(xy) >= 4:
                                                x1, y1, x2, y2 = float(xy[0]), float(xy[1]), float(xy[2]), float(xy[3])
                                                area = max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))
                                                if (area / frame_area) < min_area_ratio:
                                                    continue
                                    except Exception:
                                        pass
                                det_class_ok += 1
                                det_pass += 1
                                ev_type = self._event_for(cls_name)
                                prev = best_by_event.get(ev_type)
                                if prev is None or conf > float(prev[0]):
                                    best_by_event[ev_type] = (float(conf), cls_name)
                        except Exception:
                            any_fired = False

                        if best_by_event:
                            tags = cfg.get("tags") or []
                            if not isinstance(tags, list):
                                tags = []
                            tagset = {str(t).strip().lower() for t in tags if isinstance(t, str)}
                            if cfg.get("ai_enabled") is True and "ai_enabled" not in tagset:
                                tags = list(tags) + ["ai_enabled"]

                            for ev_type, (conf, cls_name) in best_by_event.items():
                                now_evt = time.time()
                                cooldown_key = ev_type.strip().lower()
                                if not self._confirm_ok(did, ch, cooldown_key, now_evt):
                                    continue
                                if not self._cooldown_ok(did, ch, cooldown_key, now_evt):
                                    continue
                                sev = self._severity_for(cls_name)
                                grp = self._group_for_class(cls_name)
                                if grp:
                                    gtag = f"ai_{grp}".lower()
                                    if gtag not in tagset:
                                        tags = list(tags) + [gtag]
                                        tagset.add(gtag)
                                desc = f"{cls_name} conf={float(conf):.2f} stream={stream_key}"
                                snap = self._encode_snapshot_b64(frame, stream_key=stream_key)
                                extra = {
                                    "device_type": cfg.get("device_type") or "",
                                    "tags": tags,
                                    "ai_class": cls_name,
                                    "ai_group": grp,
                                    "ai_conf": float(conf),
                                    "ai_stream": stream_key,
                                }
                                ok_push = self._push_event(token, did, ch, ev_type, sev, desc, snapshot_jpg_b64=snap, extra=extra)
                                any_fired = any_fired or ok_push

                        # ---- Analiticos avancados (zona, linha, contagem) ----
                        try:
                            self._run_analytics(
                                stream_key=stream_key,
                                token=token,
                                device_id=did,
                                channel=ch,
                                cfg=cfg,
                                boxes=boxes,
                                names=names,
                                frame=frame,
                                fw=fw if frame_area > 0 else 640,
                                fh=fh if frame_area > 0 else 480,
                                conf_th=conf_th,
                            )
                        except Exception:
                            pass

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
                                        extra={"device_type": cfg.get("device_type") or "", "tags": tags},
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
