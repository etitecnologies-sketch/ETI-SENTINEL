"""
ETI SENTINEL - Score de Risco em Tempo Real
Calcula um índice 0-100 com base em eventos recentes, horário e tipo de ocorrência.
Usa decaimento exponencial: o score cai pela metade a cada 10 minutos sem eventos.
"""

import math
import threading
import time
from typing import Dict, List, Tuple

# Pontos base por tipo de evento (quanto cada ocorrência contribui ao score)
_EVENT_WEIGHTS: Dict[str, float] = {
    "intrusion_detected":  32.0,
    "ai_zone_intrusion":   28.0,
    "alarm_input":         24.0,
    "ai_line_crossing":    22.0,
    "ai_crowd_alert":      22.0,
    "ai_person_detected":  16.0,
    "motion_detected":     14.0,
    "ai_object_detected":  12.0,
    "videoloss_started":   10.0,
    "edge_stream_offline":  8.0,
    "ai_people_count":      4.0,
}

_SEVERITY_MULTIPLIER: Dict[str, float] = {
    "critical": 1.6,
    "error":    1.3,
    "warn":     1.0,
    "warning":  1.0,
    "info":     0.7,
}

# Score cai para metade em 10 minutos sem eventos
_HALF_LIFE_SECONDS = 600.0


def _time_factor() -> float:
    """Multiplica o peso do evento pelo horário — madrugada/noite vale mais."""
    h = time.localtime().tm_hour
    if h >= 22 or h < 6:
        return 1.5   # madrugada / noite
    if 18 <= h < 22:
        return 1.2   # entardecer
    if 6 <= h < 8:
        return 1.1   # amanhecer
    return 1.0       # horário comercial


def _classify(score: float) -> Tuple[str, str]:
    if score >= 76:
        return "CRÍTICO", "#dc2626"
    if score >= 51:
        return "ELEVADO", "#f97316"
    if score >= 26:
        return "MODERADO", "#f59e0b"
    return "BAIXO", "#00c9a7"


class RiskScorer:
    """
    Score contínuo de risco com decaimento exponencial.
    Thread-safe. Atualizado a cada evento relevante recebido pelo PushRelay.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._score: float = 0.0
        self._last_update: float = time.time()
        self._event_log: List[Tuple[float, str, float]] = []

    def ingest(self, ev: Dict) -> float:
        """Processa evento, atualiza o score e retorna o novo valor."""
        et = str(ev.get("event_type") or "").lower()
        sev = str(ev.get("severity") or "info").lower()

        base = _EVENT_WEIGHTS.get(et, 0.0)
        if base == 0.0:
            for key, val in _EVENT_WEIGHTS.items():
                if key in et:
                    base = val * 0.8
                    break

        if base == 0.0:
            return self.current_score()

        points = base * _SEVERITY_MULTIPLIER.get(sev, 1.0) * _time_factor()

        with self._lock:
            self._apply_decay()
            self._score = min(100.0, self._score + points)
            self._last_update = time.time()
            self._event_log.append((self._last_update, et, round(points, 1)))
            if len(self._event_log) > 200:
                self._event_log = self._event_log[-100:]

        return self._score

    def current_score(self) -> float:
        with self._lock:
            self._apply_decay()
            return round(self._score, 1)

    def snapshot(self) -> Dict:
        """Retorna estado completo para exibição no dashboard."""
        with self._lock:
            self._apply_decay()
            score = round(self._score, 1)
            recent = list(self._event_log[-10:])

        label, color = _classify(score)
        return {
            "score": score,
            "label": label,
            "color": color,
            "time_factor": round(_time_factor(), 2),
            "last_events": [
                {"ts": round(ts, 1), "event_type": et, "points": pts}
                for ts, et, pts in recent
            ],
        }

    def _apply_decay(self) -> None:
        """Decaimento exponencial — deve ser chamado sob self._lock."""
        now = time.time()
        dt = now - self._last_update
        if dt <= 0:
            return
        self._score *= math.exp(-dt * math.log(2) / _HALF_LIFE_SECONDS)
        self._last_update = now
