"""
ETI SENTINEL — Detecção de Fogo e Fumaça (Feature #11)
=======================================================
Detecta fogo e fumaça em frames de câmera usando análise de cor HSV e
variação temporal entre frames. Não requer modelo IA especializado.

Como funciona:
  FOGO   — pixels HSV com matiz laranja/amarelo/vermelho, alta saturação e
            brilho. Regiões de fogo têm variação temporal (tremulação).
  FUMAÇA — regiões cinzas de baixa saturação em movimento (diferença de frames).
  Ambos  — confirmação por N frames consecutivos evita falsos positivos.

Variáveis de ambiente:
  ENABLE_FIRE_DETECTION        1 para ativar (padrão: 0)
  AI_FIRE_AREA_THRESHOLD       Fração mínima do frame (padrão: 0.012 = 1.2%)
  AI_FIRE_CONFIRM_FRAMES       Frames consecutivos para confirmar (padrão: 4)
  AI_FIRE_ALERT_INTERVAL       Intervalo mínimo entre alertas em s (padrão: 120)
  AI_FIRE_FLICKER_THRESHOLD    Variância mínima de tremulação (padrão: 15.0)
  AI_SMOKE_AREA_THRESHOLD      Fração mínima do frame para fumaça (padrão: 0.05)
  AI_SMOKE_MOTION_THRESHOLD    Pixels em movimento mínimos (padrão: 0.008)
"""

import logging
import os
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key) or default)
    except Exception:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key) or default)
    except Exception:
        return default


class _StreamState:
    __slots__ = (
        "fire_count", "smoke_count",
        "last_fire_alert", "last_smoke_alert",
        "prev_frame_gray", "flicker_history",
    )

    def __init__(self) -> None:
        self.fire_count      = 0
        self.smoke_count     = 0
        self.last_fire_alert = 0.0
        self.last_smoke_alert = 0.0
        self.prev_frame_gray: Optional[Any] = None
        # Últimas N médias de pixel da região de fogo para medir tremulação
        self.flicker_history: deque = deque(maxlen=8)


class FireSmokeDetector:
    """
    Detecta fogo e fumaça por análise de cor e movimento em frames BGR.

    Uso típico:
        detector = FireSmokeDetector()
        alerts = detector.process(stream_key, frame_bgr, time.time())
        for a in alerts:
            print(a["type"], a["fire_ratio"], a["smoke_ratio"])
    """

    def __init__(self) -> None:
        self._states: Dict[str, _StreamState] = {}
        logger.info("[FIRE] Detector de fogo e fumaça inicializado.")

    def process(
        self,
        stream_key: str,
        frame: Any,
        now: float,
    ) -> List[Dict]:
        """
        Analisa um frame e retorna alertas de fogo/fumaça.

        Cada alerta:
          {
            "type":        "fire_detected" | "smoke_detected",
            "fire_ratio":  float,   # fração do frame com cor de fogo
            "smoke_ratio": float,   # fração do frame com aspecto de fumaça
            "flicker":     float,   # variância de tremulação (fogo)
            "bbox":        [x1, y1, x2, y2],  # bounding box principal
          }
        """
        try:
            import cv2
        except ImportError:
            return []

        if stream_key not in self._states:
            self._states[stream_key] = _StreamState()

        st = self._states[stream_key]
        alerts: List[Dict] = []

        fire_threshold   = _env_float("AI_FIRE_AREA_THRESHOLD",   0.012)
        smoke_threshold  = _env_float("AI_SMOKE_AREA_THRESHOLD",  0.050)
        motion_threshold = _env_float("AI_SMOKE_MOTION_THRESHOLD", 0.008)
        confirm_frames   = _env_int("AI_FIRE_CONFIRM_FRAMES",      4)
        alert_interval   = _env_float("AI_FIRE_ALERT_INTERVAL",   120.0)
        flicker_thresh   = _env_float("AI_FIRE_FLICKER_THRESHOLD", 15.0)

        h, w = frame.shape[:2]
        total_pixels = max(1, h * w)

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ---- Detecção de FOGO ----
        # Matiz 0-25 (vermelho-laranja) e 155-179 (vermelho superior)
        # Saturação > 100, Valor > 120 — chamas são brilhantes e saturadas
        fire_mask1 = cv2.inRange(hsv, np.array([0,  100, 120]), np.array([25,  255, 255]))
        fire_mask2 = cv2.inRange(hsv, np.array([155, 100, 120]), np.array([179, 255, 255]))
        fire_mask  = cv2.bitwise_or(fire_mask1, fire_mask2)

        # Remove ruído morfológico
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_OPEN,  kernel)
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_CLOSE, kernel)

        fire_pixels = int(np.count_nonzero(fire_mask))
        fire_ratio  = fire_pixels / total_pixels

        # Tremulação: fogo real pisca — mede variância da intensidade na região
        flicker = 0.0
        fire_bbox: Optional[List[int]] = None
        if fire_pixels > 200:
            region_vals = gray[fire_mask > 0]
            mean_val = float(np.mean(region_vals))
            st.flicker_history.append(mean_val)
            if len(st.flicker_history) >= 3:
                flicker = float(np.std(list(st.flicker_history)))

            # Bounding box do maior componente de fogo
            contours, _ = cv2.findContours(fire_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                rx, ry, rw, rh = cv2.boundingRect(largest)
                fire_bbox = [rx, ry, rx + rw, ry + rh]

        fire_confirmed = fire_ratio >= fire_threshold and (flicker >= flicker_thresh or fire_ratio >= fire_threshold * 3)

        if fire_confirmed:
            st.fire_count += 1
        else:
            st.fire_count = max(0, st.fire_count - 1)

        if st.fire_count >= confirm_frames and (now - st.last_fire_alert) >= alert_interval:
            st.last_fire_alert = now
            st.fire_count = 0
            alerts.append({
                "type":        "fire_detected",
                "fire_ratio":  round(fire_ratio, 4),
                "smoke_ratio": 0.0,
                "flicker":     round(flicker, 2),
                "bbox":        fire_bbox or [0, 0, w, h],
            })
            logger.warning(
                f"[FIRE] {stream_key} FOGO DETECTADO "
                f"área={fire_ratio:.2%} tremulação={flicker:.1f}"
            )

        # ---- Detecção de FUMAÇA ----
        # Baixa saturação (cinza), valor médio (não muito escuro nem claro), em movimento
        smoke_mask = cv2.inRange(hsv, np.array([0, 0, 80]), np.array([179, 60, 210]))
        # Fumaça real: deve estar se movendo
        smoke_ratio = 0.0
        if st.prev_frame_gray is not None:
            try:
                prev_resized = cv2.resize(st.prev_frame_gray, (w, h))
                diff = cv2.absdiff(gray, prev_resized)
                _, motion = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
                smoke_moving = cv2.bitwise_and(smoke_mask, motion)
                smoke_moving = cv2.morphologyEx(smoke_moving, cv2.MORPH_OPEN, kernel)

                smoke_pixels = int(np.count_nonzero(smoke_moving))
                motion_pixels = int(np.count_nonzero(motion))
                smoke_ratio  = smoke_pixels / total_pixels
                motion_ratio = motion_pixels / total_pixels

                smoke_confirmed = smoke_ratio >= smoke_threshold and motion_ratio >= motion_threshold

                if smoke_confirmed:
                    st.smoke_count += 1
                else:
                    st.smoke_count = max(0, st.smoke_count - 1)

                if st.smoke_count >= confirm_frames and (now - st.last_smoke_alert) >= alert_interval:
                    st.last_smoke_alert = now
                    st.smoke_count = 0
                    alerts.append({
                        "type":        "smoke_detected",
                        "fire_ratio":  0.0,
                        "smoke_ratio": round(smoke_ratio, 4),
                        "flicker":     0.0,
                        "bbox":        [0, 0, w, h],
                    })
                    logger.warning(
                        f"[FIRE] {stream_key} FUMAÇA DETECTADA "
                        f"área={smoke_ratio:.2%} movimento={motion_ratio:.2%}"
                    )
            except Exception:
                pass

        # Salva frame atual para próxima comparação (reduzido para economizar memória)
        try:
            st.prev_frame_gray = cv2.resize(gray, (w // 2, h // 2))
        except Exception:
            st.prev_frame_gray = gray

        return alerts

    def draw_overlay(self, frame: Any, alerts: List[Dict]) -> Any:
        """Desenha overlay visual de fogo/fumaça no frame (opcional, para debug)."""
        try:
            import cv2

            for a in alerts:
                bbox = a.get("bbox") or []
                if len(bbox) == 4:
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    color = (0, 50, 255) if a["type"] == "fire_detected" else (180, 180, 180)
                    label = "🔥 FOGO" if a["type"] == "fire_detected" else "💨 FUMAÇA"
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                    cv2.putText(frame, label, (x1 + 4, max(y1 - 8, 20)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        except Exception:
            pass
        return frame
