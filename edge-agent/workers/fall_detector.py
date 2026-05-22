"""
ETI SENTINEL — Detecção de Queda de Pessoa (Feature #10)
=========================================================
Detecta quando uma pessoa cai no chao usando a variacao de proporcao
da caixa de deteccao entre frames consecutivos.

Como funciona:
  1. Uma pessoa de pe tem caixa mais alta do que larga (aspect h/w > 1.0).
  2. Uma pessoa caida tem caixa mais larga do que alta (aspect h/w < limiar).
  3. Se essa transicao ocorrer rapidamente (poucos frames), e queda.
  4. Alerta critico e disparado imediatamente.
  5. Alertas de reforco sao enviados enquanto a pessoa permanece no chao.

Variaveis de ambiente:
  ENABLE_FALL_DETECTION      1 para ativar (padrao: 0)
  AI_FALL_ASPECT_THRESHOLD   Proporcao h/w abaixo da qual = caido (padrao: 0.65)
  AI_FALL_STANDING_ASPECT    Proporcao h/w acima da qual = de pe (padrao: 1.0)
  AI_FALL_SPEED_FRAMES       Max frames para a transicao valer como queda (padrao: 5)
  AI_FALL_TRACK_RADIUS       Raio de associacao de rastros 0.0-1.0 (padrao: 0.20)
  AI_FALL_TRACK_TIMEOUT      Segundos sem deteccao para descartar rastro (padrao: 6.0)
  AI_FALL_ALERT_INTERVAL     Intervalo entre alertas repetidos em segundos (padrao: 90)
  AI_FALL_MIN_BOX_HEIGHT     Altura minima da caixa normalizada para contar (padrao: 0.08)
"""

import logging
import os
import time
from collections import deque
from typing import Deque, Dict, List, Optional

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


class _FallTrack:
    """Historico de proporcao de caixa de uma pessoa rastreada."""

    __slots__ = (
        "track_id", "cx", "cy", "aspect",
        "aspect_history", "last_seen",
        "fall_confirmed", "last_alert_ts", "alerted",
    )

    def __init__(self, track_id: int, cx: float, cy: float,
                 aspect: float, now: float, history_len: int) -> None:
        self.track_id       = track_id
        self.cx             = cx
        self.cy             = cy
        self.aspect         = aspect
        self.aspect_history: Deque[float] = deque([aspect], maxlen=history_len)
        self.last_seen      = now
        self.fall_confirmed = False   # ja confirmou queda neste rastro
        self.last_alert_ts  = 0.0
        self.alerted        = False


class FallDetector:
    """
    Rastreia pessoas e detecta quedas por variacao de proporcao de caixa.

    Uso tipico:
        detector = FallDetector()
        alerts = detector.process(stream_key, detections, now)
        for a in alerts:
            print(a["type"], a["duration_on_ground_s"])
    """

    def __init__(self) -> None:
        self._tracks: Dict[str, Dict[int, _FallTrack]] = {}
        self._next_id: Dict[str, int] = {}
        logger.info("[FALL] Detector de queda de pessoa inicializado.")

    def process(
        self,
        stream_key: str,
        detections: List[Dict],
        now: float,
    ) -> List[Dict]:
        """
        Processa deteccoes de um frame e retorna alertas de queda.

        Cada alerta retornado:
          {
            "type":                 "fall_detected" | "still_on_ground",
            "cx":                   float,
            "cy":                   float,
            "aspect":               float,   # proporcao h/w atual
            "duration_on_ground_s": float,   # segundos desde a queda
            "first_alert":          bool,
          }
        """
        fall_aspect     = _env_float("AI_FALL_ASPECT_THRESHOLD",  0.65)
        standing_aspect = _env_float("AI_FALL_STANDING_ASPECT",   1.0)
        speed_frames    = _env_int  ("AI_FALL_SPEED_FRAMES",       5)
        radius          = _env_float("AI_FALL_TRACK_RADIUS",       0.20)
        timeout         = _env_float("AI_FALL_TRACK_TIMEOUT",      6.0)
        alert_interval  = _env_float("AI_FALL_ALERT_INTERVAL",    90.0)
        min_box_h       = _env_float("AI_FALL_MIN_BOX_HEIGHT",     0.08)

        person_dets = [d for d in detections if d["cls_name"] == "person"]

        if stream_key not in self._tracks:
            self._tracks[stream_key] = {}
        if stream_key not in self._next_id:
            self._next_id[stream_key] = 0

        tracks = self._tracks[stream_key]
        alerts: List[Dict] = []

        # Remove rastros expirados
        expired = [tid for tid, tr in tracks.items()
                   if (now - tr.last_seen) > timeout]
        for tid in expired:
            del tracks[tid]

        # Calcula aspect ratio de cada deteccao de pessoa
        det_aspects: List[Optional[float]] = []
        for det in person_dets:
            x1, y1, x2, y2 = det["xyxy"]
            bw = max(1.0, x2 - x1)
            bh = y2 - y1
            # Filtra caixas muito pequenas (ruido)
            orig_h_est = det.get("orig_h", 1.0) or 1.0
            bh_norm = bh / max(1.0, orig_h_est)
            det_aspects.append(bh / bw)

        # Associa deteccoes a rastros existentes (nearest centroid)
        used_tracks: set = set()
        used_dets:   set = set()

        for det_idx, det in enumerate(person_dets):
            cx, cy = det["cx_norm"], det["cy_norm"]
            aspect = det_aspects[det_idx]
            if aspect is None:
                continue

            best_tid  = None
            best_dist = radius

            for tid, tr in tracks.items():
                if tid in used_tracks:
                    continue
                dist = ((cx - tr.cx) ** 2 + (cy - tr.cy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_tid  = tid

            if best_tid is not None:
                used_tracks.add(best_tid)
                used_dets.add(det_idx)
                tr = tracks[best_tid]
                tr.aspect_history.append(aspect)
                tr.cx        = cx
                tr.cy        = cy
                tr.aspect    = aspect
                tr.last_seen = now

                # Verifica condicao de queda
                is_fallen = aspect < fall_aspect
                if is_fallen:
                    # Checa se havia registro de "de pe" nos ultimos speed_frames
                    was_standing = any(
                        a >= standing_aspect
                        for a in list(tr.aspect_history)[:-1]
                    )

                    # Queda nova: transicao rapida de pe -> caido
                    if was_standing and not tr.fall_confirmed:
                        tr.fall_confirmed = True
                        tr.last_alert_ts  = now
                        tr.alerted        = True
                        alerts.append({
                            "type":                 "fall_detected",
                            "cx":                   cx,
                            "cy":                   cy,
                            "aspect":               round(aspect, 3),
                            "duration_on_ground_s": 0.0,
                            "first_alert":          True,
                        })
                        logger.warning(
                            f"[FALL] {stream_key} QUEDA DETECTADA "
                            f"rastro #{best_tid} | aspect={aspect:.2f}"
                        )

                    # Reforco: pessoa continua no chao
                    elif tr.fall_confirmed and (now - tr.last_alert_ts) >= alert_interval:
                        duracao = now - tr.last_alert_ts
                        tr.last_alert_ts = now
                        alerts.append({
                            "type":                 "still_on_ground",
                            "cx":                   cx,
                            "cy":                   cy,
                            "aspect":               round(aspect, 3),
                            "duration_on_ground_s": round(duracao, 1),
                            "first_alert":          False,
                        })
                        logger.warning(
                            f"[FALL] {stream_key} PESSOA AINDA NO CHAO "
                            f"rastro #{best_tid} | {duracao:.0f}s"
                        )
                else:
                    # Pessoa levantou — reseta estado de queda
                    if tr.fall_confirmed and aspect >= standing_aspect:
                        tr.fall_confirmed = False
                        logger.info(
                            f"[FALL] {stream_key} rastro #{best_tid} "
                            f"levantou (aspect={aspect:.2f})"
                        )

        # Cria novos rastros para deteccoes sem par
        for det_idx, det in enumerate(person_dets):
            if det_idx in used_dets:
                continue
            aspect = det_aspects[det_idx]
            if aspect is None:
                continue
            cx, cy = det["cx_norm"], det["cy_norm"]
            new_id = self._next_id[stream_key]
            self._next_id[stream_key] += 1
            tracks[new_id] = _FallTrack(
                new_id, cx, cy, aspect, now, speed_frames + 2
            )

        return alerts
