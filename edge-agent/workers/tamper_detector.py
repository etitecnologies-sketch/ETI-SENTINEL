"""
ETI SENTINEL — Detecção de Sabotagem de Câmera / Camera Tamper (Feature #12)
==============================================================================
Detecta quando a câmera é coberta, virada, desfocada ou obstruída.

Como funciona:
  1. Aprende o "perfil normal" da câmera nos primeiros AI_TAMPER_BASELINE_FRAMES
     frames estáveis (histograma de luminosidade e densidade de bordas).
  2. A cada frame novo, compara com o perfil:
     • Câmera coberta   → frame quase uniforme (desvio padrão muito baixo)
     • Câmera pintada   → histograma completamente diferente do baseline
     • Câmera virada    → queda grande na correlação com o baseline
     • Câmera desfocada → queda na densidade de bordas Canny
  3. Qualquer das condições acima por TAMPER_CONFIRM_FRAMES frames seguidos
     dispara alerta "ai_camera_tampered".

Variáveis de ambiente:
  ENABLE_TAMPER_DETECTION      1 para ativar (padrão: 0)
  AI_TAMPER_BASELINE_FRAMES    Frames para aprender baseline (padrão: 60)
  AI_TAMPER_CONFIRM_FRAMES     Frames consecutivos para confirmar (padrão: 8)
  AI_TAMPER_ALERT_INTERVAL     Intervalo mínimo entre alertas em s (padrão: 180)
  AI_TAMPER_HIST_CORR_THRESH   Correlação mínima com baseline (padrão: 0.40)
  AI_TAMPER_STD_THRESH         Desvio padrão mínimo de luminosidade (padrão: 8.0)
  AI_TAMPER_EDGE_RATIO_THRESH  Queda máxima aceitável na densidade de bordas (padrão: 0.20)
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

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


class _CameraProfile:
    """Perfil normal de uma câmera aprendido durante o baseline."""

    __slots__ = (
        "baseline_hist", "baseline_edge_density",
        "baseline_frames", "tamper_count",
        "last_alert_ts", "alerted",
    )

    def __init__(self) -> None:
        self.baseline_hist: Optional[Any]   = None   # numpy array (256,)
        self.baseline_edge_density: float   = 0.0
        self.baseline_frames: int           = 0
        self.tamper_count: int              = 0
        self.last_alert_ts: float           = 0.0
        self.alerted: bool                  = False


class TamperDetector:
    """
    Detecta sabotagem de câmera por análise de histograma e bordas.

    Uso típico:
        detector = TamperDetector()
        alerts = detector.process(stream_key, frame_bgr, time.time())
        for a in alerts:
            print(a["reason"])
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, _CameraProfile] = {}
        logger.info("[TAMPER] Detector de sabotagem de câmera inicializado.")

    def reset_baseline(self, stream_key: str) -> None:
        """Força reaprendizado do baseline (use quando câmera for reposicionada intencionalmente)."""
        if stream_key in self._profiles:
            del self._profiles[stream_key]
        logger.info(f"[TAMPER] {stream_key} baseline resetado.")

    def process(
        self,
        stream_key: str,
        frame: Any,
        now: float,
    ) -> List[Dict]:
        """
        Analisa o frame e retorna alertas de sabotagem.

        Cada alerta:
          {
            "type":         "ai_camera_tampered",
            "reason":       str,     # "coberta" | "virada" | "desfocada" | "obstruida"
            "hist_corr":    float,   # correlação com baseline (0=diferente, 1=igual)
            "frame_std":    float,   # desvio padrão de luminosidade
            "edge_density": float,   # proporção de pixels de borda
          }
        """
        try:
            import cv2
        except ImportError:
            return []

        if stream_key not in self._profiles:
            self._profiles[stream_key] = _CameraProfile()

        prof = self._profiles[stream_key]
        baseline_target = _env_int("AI_TAMPER_BASELINE_FRAMES",   60)
        confirm_frames  = _env_int("AI_TAMPER_CONFIRM_FRAMES",     8)
        alert_interval  = _env_float("AI_TAMPER_ALERT_INTERVAL",  180.0)
        hist_thresh     = _env_float("AI_TAMPER_HIST_CORR_THRESH", 0.40)
        std_thresh      = _env_float("AI_TAMPER_STD_THRESH",       8.0)
        edge_ratio_thresh = _env_float("AI_TAMPER_EDGE_RATIO_THRESH", 0.20)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Calcula histograma e densidade de bordas do frame atual
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.count_nonzero(edges)) / max(1, h * w)
        frame_std    = float(np.std(gray))

        # ---- Fase de aprendizado do baseline ----
        if prof.baseline_frames < baseline_target:
            if prof.baseline_hist is None:
                prof.baseline_hist = hist.copy()
                prof.baseline_edge_density = edge_density
            else:
                # Média incremental do histograma e densidade de bordas
                alpha = 1.0 / (prof.baseline_frames + 1)
                prof.baseline_hist = (1 - alpha) * prof.baseline_hist + alpha * hist
                prof.baseline_edge_density = (
                    (1 - alpha) * prof.baseline_edge_density + alpha * edge_density
                )
            prof.baseline_frames += 1

            if prof.baseline_frames == baseline_target:
                logger.info(
                    f"[TAMPER] {stream_key} baseline aprendido "
                    f"(edge_density={prof.baseline_edge_density:.4f})"
                )
            return []

        # ---- Detecção ----
        reason: Optional[str] = None
        hist_corr = 0.0

        # 1. Câmera coberta: desvio padrão muito baixo (imagem quase uniforme)
        if frame_std < std_thresh:
            reason = "coberta"

        # 2. Histograma muito diferente do baseline
        if reason is None and prof.baseline_hist is not None:
            hist_corr = float(cv2.compareHist(
                hist.reshape(-1, 1).astype(np.float32),
                prof.baseline_hist.reshape(-1, 1).astype(np.float32),
                cv2.HISTCMP_CORREL,
            ))
            if hist_corr < hist_thresh:
                reason = "virada" if edge_density > 0.01 else "obstruida"

        # 3. Câmera desfocada: borda caiu muito em relação ao baseline
        if reason is None and prof.baseline_edge_density > 0.001:
            edge_ratio = edge_density / prof.baseline_edge_density
            if edge_ratio < edge_ratio_thresh:
                reason = "desfocada"

        if reason:
            prof.tamper_count += 1
        else:
            prof.tamper_count = max(0, prof.tamper_count - 2)

        alerts: List[Dict] = []
        if prof.tamper_count >= confirm_frames and (now - prof.last_alert_ts) >= alert_interval:
            prof.last_alert_ts = now
            prof.tamper_count  = 0
            alerts.append({
                "type":         "ai_camera_tampered",
                "reason":       reason or "desconhecido",
                "hist_corr":    round(hist_corr, 3),
                "frame_std":    round(frame_std, 2),
                "edge_density": round(edge_density, 5),
            })
            logger.warning(
                f"[TAMPER] {stream_key} CÂMERA SABOTADA "
                f"motivo={reason} std={frame_std:.1f} corr={hist_corr:.2f}"
            )

        return alerts
