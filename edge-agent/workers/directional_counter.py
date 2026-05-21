"""
ETI SENTINEL — Contador Direcional de Pessoas (Feature #7)
===========================================================
Conta quantas pessoas entram e saem de um ambiente usando uma linha virtual.

Como funciona:
  1. Cada pessoa detectada recebe um "rastro" rastreado pelo centro do corpo.
  2. Quando o rastro cruza a linha virtual, conta como entrada ou saída.
  3. Os contadores persistem em arquivo JSON para sobreviver a reinicializacoes.

Variaveis de ambiente:
  ENABLE_DIRECTIONAL_COUNTER   1 para ativar (padrao: 0)
  AI_DIRECTION_LINE            Linha virtual: "x1,y1,x2,y2" normalizados 0.0-1.0
                               Padrao: "0,0.5,1,0.5" (linha horizontal no meio)
  AI_DIRECTION_ENTER_SIDE      Lado da entrada: "positive" ou "negative"
                               Padrao: "positive" (abaixo/direita da linha)
  AI_DIRECTION_TRACK_RADIUS    Raio de busca para associar rastros, 0.0-1.0 (padrao: 0.12)
  AI_DIRECTION_TRACK_TIMEOUT   Segundos ate descartar rastro sem deteccao (padrao: 3.0)
  AI_DIRECTION_PERSIST_FILE    Caminho do arquivo de persistencia dos contadores
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key) or default)
    except Exception:
        return default


def _parse_line() -> Tuple[float, float, float, float]:
    """Le AI_DIRECTION_LINE e retorna (x1, y1, x2, y2). Padrao: linha horizontal central."""
    raw = (os.getenv("AI_DIRECTION_LINE") or "").strip()
    if raw:
        try:
            parts = [float(p) for p in raw.split(",")]
            if len(parts) == 4:
                return (parts[0], parts[1], parts[2], parts[3])
        except Exception:
            pass
    return (0.0, 0.5, 1.0, 0.5)


def _side_of_line(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Produto vetorial: indica de qual lado da linha o ponto (px, py) esta.
    Positivo = lado direito/abaixo, Negativo = lado esquerdo/acima.
    Zero = exatamente sobre a linha.
    """
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


class _Track:
    """Rastro de uma pessoa entre frames."""

    __slots__ = ("track_id", "cx", "cy", "side", "last_seen")

    def __init__(self, track_id: int, cx: float, cy: float, side: float, now: float) -> None:
        self.track_id = track_id
        self.cx = cx
        self.cy = cy
        self.side = side       # sinal do lado atual (positivo ou negativo)
        self.last_seen = now


class DirectionalCounter:
    """
    Rastreia pessoas quadro a quadro e conta entradas/saidas com base em linha virtual.

    Uso tipico:
        counter = DirectionalCounter()
        events = counter.process(stream_key, detections, time.time())
        for ev in events:
            print(ev["type"], ev["enter_total"], ev["exit_total"])
    """

    def __init__(self) -> None:
        # Rastros ativos: stream_key -> {track_id -> _Track}
        self._tracks: Dict[str, Dict[int, _Track]] = {}
        # Proximo ID de rastro por stream
        self._next_id: Dict[str, int] = {}
        # Contadores acumulados: stream_key -> {"enter": N, "exit": N}
        self._counters: Dict[str, Dict[str, int]] = {}

        self._load_persisted()
        logger.info("[DIR-COUNTER] Contador direcional de pessoas inicializado.")

    # ---- Persistencia ----

    def _counter_file(self) -> Optional[Path]:
        raw = (os.getenv("AI_DIRECTION_PERSIST_FILE") or "").strip()
        if raw:
            return Path(raw)
        try:
            base = Path(os.environ.get("PROGRAMDATA", "")) / "ETI-SENTINEL"
            if base.exists():
                return base / "directional_counts.json"
        except Exception:
            pass
        return None

    def _load_persisted(self) -> None:
        f = self._counter_file()
        if not f or not f.exists():
            return
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            for key, v in data.items():
                self._counters[key] = {
                    "enter": int(v.get("enter", 0)),
                    "exit":  int(v.get("exit", 0)),
                }
            logger.info(f"[DIR-COUNTER] Contadores restaurados de {f}")
        except Exception as exc:
            logger.warning(f"[DIR-COUNTER] Falha ao restaurar contadores: {exc}")

    def _persist(self) -> None:
        f = self._counter_file()
        if not f:
            return
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(self._counters, fp)
        except Exception:
            pass

    # ---- Acesso aos contadores ----

    def _get_counters(self, stream_key: str) -> Dict[str, int]:
        if stream_key not in self._counters:
            self._counters[stream_key] = {"enter": 0, "exit": 0}
        return self._counters[stream_key]

    def get_totals(self, stream_key: str) -> Dict[str, int]:
        """Retorna {"enter": N, "exit": N, "occupancy": N} para o stream."""
        c = self._get_counters(stream_key)
        return {
            "enter":     c["enter"],
            "exit":      c["exit"],
            "occupancy": max(0, c["enter"] - c["exit"]),
        }

    def reset(self, stream_key: str) -> None:
        """Zera os contadores de um stream e persiste."""
        self._counters[stream_key] = {"enter": 0, "exit": 0}
        self._persist()
        logger.info(f"[DIR-COUNTER] Contadores zerados para {stream_key}")

    # ---- Processamento de frame ----

    def process(
        self,
        stream_key: str,
        detections: List[Dict],
        now: float,
    ) -> List[Dict]:
        """
        Recebe as deteccoes de um frame e retorna lista de eventos de cruzamento.

        Cada evento retornado:
          {
            "type":         "enter" | "exit",
            "enter_total":  int,
            "exit_total":   int,
            "occupancy":    int,
            "cx":           float,  # posicao normalizada da pessoa
            "cy":           float,
          }
        """
        x1, y1, x2, y2 = _parse_line()
        enter_positive = (os.getenv("AI_DIRECTION_ENTER_SIDE") or "positive").strip().lower() != "negative"
        radius  = _env_float("AI_DIRECTION_TRACK_RADIUS",  0.12)
        timeout = _env_float("AI_DIRECTION_TRACK_TIMEOUT", 3.0)

        # Apenas pessoas contam
        person_dets = [d for d in detections if d["cls_name"] == "person"]

        # Inicializa estruturas para este stream
        if stream_key not in self._tracks:
            self._tracks[stream_key] = {}
        if stream_key not in self._next_id:
            self._next_id[stream_key] = 0

        tracks   = self._tracks[stream_key]
        counters = self._get_counters(stream_key)
        events: List[Dict] = []

        # Remove rastros que sumiram da cena (timeout)
        expired = [tid for tid, tr in tracks.items() if (now - tr.last_seen) > timeout]
        for tid in expired:
            del tracks[tid]

        # Associa cada deteccao ao rastro mais proximo (nearest centroid matching)
        used_tracks: set = set()
        used_dets:   set = set()

        for det_idx, det in enumerate(person_dets):
            cx, cy = det["cx_norm"], det["cy_norm"]
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
                # Atualiza rastro existente
                used_tracks.add(best_tid)
                used_dets.add(det_idx)
                tr = tracks[best_tid]

                prev_side = tr.side
                new_side  = _side_of_line(cx, cy, x1, y1, x2, y2)

                # Detecta mudanca de lado (cruzamento real)
                if prev_side != 0 and new_side != 0 and (prev_side > 0) != (new_side > 0):
                    going_positive = new_side > 0
                    if going_positive == enter_positive:
                        counters["enter"] += 1
                        ev_type = "enter"
                    else:
                        counters["exit"] += 1
                        ev_type = "exit"

                    occupancy = max(0, counters["enter"] - counters["exit"])
                    events.append({
                        "type":        ev_type,
                        "enter_total": counters["enter"],
                        "exit_total":  counters["exit"],
                        "occupancy":   occupancy,
                        "cx":          cx,
                        "cy":          cy,
                    })
                    logger.info(
                        f"[DIR-COUNTER] {stream_key} → {ev_type.upper()} "
                        f"| Entradas: {counters['enter']} | Saidas: {counters['exit']} "
                        f"| Ocupacao: {occupancy}"
                    )
                    self._persist()

                tr.cx        = cx
                tr.cy        = cy
                tr.side      = new_side
                tr.last_seen = now

        # Cria novos rastros para deteccoes sem par
        for det_idx, det in enumerate(person_dets):
            if det_idx in used_dets:
                continue
            cx, cy   = det["cx_norm"], det["cy_norm"]
            side     = _side_of_line(cx, cy, x1, y1, x2, y2)
            new_id   = self._next_id[stream_key]
            self._next_id[stream_key] += 1
            tracks[new_id] = _Track(new_id, cx, cy, side, now)

        return events
