"""
ETI SENTINEL — Detecção de Permanência Prolongada (Feature #8)
==============================================================
Detecta quando uma pessoa permanece numa area por tempo acima do limite,
indicando possivel comportamento suspeito (loitering).

Como funciona:
  1. Cada pessoa detectada recebe um rastro com cronometro.
  2. Se a pessoa permanecer na area por mais de AI_LOITER_SECONDS,
     um alerta e disparado.
  3. O alerta se repete a cada AI_LOITER_ALERT_INTERVAL segundos enquanto
     a pessoa permanecer — sem spam, mas sem silencio.
  4. Quando a pessoa some da cena, o rastro e descartado.

Variaveis de ambiente:
  ENABLE_LOITERING           1 para ativar (padrao: 0)
  AI_LOITER_SECONDS          Tempo em segundos ate o primeiro alerta (padrao: 60)
  AI_LOITER_ALERT_INTERVAL   Intervalo entre alertas repetidos em segundos (padrao: 120)
  AI_LOITER_ZONE             Zona de monitoramento "x1,y1,x2,y2" normalizados 0.0-1.0
                             Padrao: frame inteiro (0,0,1,1)
  AI_LOITER_TRACK_RADIUS     Raio de associacao de rastros 0.0-1.0 (padrao: 0.15)
  AI_LOITER_TRACK_TIMEOUT    Segundos sem deteccao para descartar rastro (padrao: 5.0)
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key) or default)
    except Exception:
        return default


def _parse_zone() -> Optional[Tuple[float, float, float, float]]:
    """Le AI_LOITER_ZONE. Retorna (x1, y1, x2, y2) ou None para frame inteiro."""
    raw = (os.getenv("AI_LOITER_ZONE") or "").strip()
    if not raw:
        return None
    try:
        parts = [float(p) for p in raw.split(",")]
        if len(parts) == 4:
            return (parts[0], parts[1], parts[2], parts[3])
    except Exception:
        pass
    return None


def _in_zone(cx: float, cy: float, zone: Optional[Tuple]) -> bool:
    """Verifica se o centroide esta dentro da zona monitorada."""
    if zone is None:
        return True  # sem zona definida = frame inteiro
    x1, y1, x2, y2 = zone
    return x1 <= cx <= x2 and y1 <= cy <= y2


def _fmt_duration(seconds: float) -> str:
    """Formata duracao em texto legivel: '1m30s', '45s', etc."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s" if s else f"{m}min"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}min"


class _LoiterTrack:
    """Rastro de permanencia de uma pessoa."""

    __slots__ = ("track_id", "cx", "cy", "first_seen", "last_seen", "last_alert_ts", "alerted")

    def __init__(self, track_id: int, cx: float, cy: float, now: float) -> None:
        self.track_id    = track_id
        self.cx          = cx
        self.cy          = cy
        self.first_seen  = now   # quando a pessoa apareceu pela primeira vez
        self.last_seen   = now   # ultima vez que foi detectada
        self.last_alert_ts = 0.0 # ultima vez que um alerta foi disparado
        self.alerted     = False  # ja alertou ao menos uma vez


class LoiteringDetector:
    """
    Rastreia pessoas e dispara alertas de permanencia prolongada.

    Uso tipico:
        detector = LoiteringDetector()
        alerts = detector.process(stream_key, detections, time.time())
        for a in alerts:
            print(a["duration_seconds"], a["cx"], a["cy"])
    """

    def __init__(self) -> None:
        # Rastros por stream: stream_key -> {track_id -> _LoiterTrack}
        self._tracks: Dict[str, Dict[int, _LoiterTrack]] = {}
        self._next_id: Dict[str, int] = {}
        logger.info("[LOITERING] Detector de permanencia prolongada inicializado.")

    def process(
        self,
        stream_key: str,
        detections: List[Dict],
        now: float,
    ) -> List[Dict]:
        """
        Processa deteccoes de um frame e retorna alertas de permanencia.

        Cada alerta retornado:
          {
            "track_id":         int,
            "duration_seconds": float,   # total de tempo na area
            "duration_str":     str,     # ex: "1m30s"
            "cx":               float,
            "cy":               float,
            "first_alert":      bool,    # True = primeiro alerta deste rastro
          }
        """
        loiter_s       = _env_float("AI_LOITER_SECONDS",        60.0)
        alert_interval = _env_float("AI_LOITER_ALERT_INTERVAL", 120.0)
        radius         = _env_float("AI_LOITER_TRACK_RADIUS",   0.15)
        timeout        = _env_float("AI_LOITER_TRACK_TIMEOUT",  5.0)
        zone           = _parse_zone()

        # Apenas pessoas
        person_dets = [d for d in detections if d["cls_name"] == "person"]

        if stream_key not in self._tracks:
            self._tracks[stream_key] = {}
        if stream_key not in self._next_id:
            self._next_id[stream_key] = 0

        tracks = self._tracks[stream_key]
        alerts: List[Dict] = []

        # Remove rastros expirados (pessoa saiu da cena)
        expired = [tid for tid, tr in tracks.items() if (now - tr.last_seen) > timeout]
        for tid in expired:
            tr = tracks.pop(tid)
            if tr.alerted:
                logger.info(
                    f"[LOITERING] {stream_key} rastro #{tid} encerrado "
                    f"apos {_fmt_duration(tr.last_seen - tr.first_seen)} na area."
                )

        # Associa deteccoes a rastros existentes (nearest centroid)
        used_tracks: set = set()
        used_dets:   set = set()

        for det_idx, det in enumerate(person_dets):
            cx, cy = det["cx_norm"], det["cy_norm"]

            # So considera pessoas dentro da zona monitorada
            if not _in_zone(cx, cy, zone):
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
                tr.cx        = cx
                tr.cy        = cy
                tr.last_seen = now

                duration = now - tr.first_seen

                # Verifica se deve disparar alerta
                tempo_desde_ultimo_alerta = now - tr.last_alert_ts
                deve_alertar = (
                    duration >= loiter_s
                    and (not tr.alerted or tempo_desde_ultimo_alerta >= alert_interval)
                )

                if deve_alertar:
                    first_alert = not tr.alerted
                    tr.alerted      = True
                    tr.last_alert_ts = now
                    alerts.append({
                        "track_id":         best_tid,
                        "duration_seconds": duration,
                        "duration_str":     _fmt_duration(duration),
                        "cx":               cx,
                        "cy":               cy,
                        "first_alert":      first_alert,
                    })
                    logger.info(
                        f"[LOITERING] {stream_key} ALERTA rastro #{best_tid} "
                        f"• {_fmt_duration(duration)} na area"
                        f"{'  (primeiro alerta)' if first_alert else ''}"
                    )

        # Cria novos rastros para deteccoes nao associadas que estao na zona
        for det_idx, det in enumerate(person_dets):
            if det_idx in used_dets:
                continue
            cx, cy = det["cx_norm"], det["cy_norm"]
            if not _in_zone(cx, cy, zone):
                continue
            new_id = self._next_id[stream_key]
            self._next_id[stream_key] += 1
            tracks[new_id] = _LoiterTrack(new_id, cx, cy, now)

        return alerts
