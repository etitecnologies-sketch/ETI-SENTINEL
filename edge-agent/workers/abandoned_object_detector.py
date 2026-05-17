"""
ETI SENTINEL - Detecção de Abandono de Objeto
Detecta quando um objeto (mochila, mala, pacote) fica sem dono após uma pessoa se afastar.
Rastreamento por centroide entre frames — sem GPU extra, funciona sobre as detecções ONNX existentes.

Configuração via .env:
  AI_ABANDON_SECONDS        Tempo sem dono antes de alertar (padrão: 30)
  AI_ABANDON_CLASSES        Classes monitoradas, separadas por vírgula (padrão: ver abaixo)
  AI_ABANDON_PERSON_RADIUS  Raio de "dono presente" em coordenadas normalizadas (padrão: 0.25)
  ENABLE_AI_ABANDON         1 para ativar (padrão: 0, ativado junto com ENABLE_AI_ANALYTICS)
"""

import os
import time
from typing import Any, Dict, List, Optional

# Classes COCO que podem ser "abandonadas" por alguém
_DEFAULT_ABANDON_CLASSES = frozenset({
    "backpack", "suitcase", "handbag", "umbrella",
    "sports ball", "bottle", "cup", "bowl", "book",
})

_MATCH_RADIUS     = 0.12   # centroide moveu < 12% da largura → mesmo objeto
_PERSON_RADIUS    = 0.25   # pessoa dentro desse raio → objeto tem dono
_ABANDON_DEFAULT  = 30.0   # segundos sem dono
_STALE_SECONDS    = 6.0    # objeto some do rastreamento após N seg sem aparecer


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


# ---------------------------------------------------------------------------
# Rastreador por stream
# ---------------------------------------------------------------------------

class AbandonedObjectDetector:
    """
    Mantém estado de rastreamento de objetos para uma única câmera/stream.
    Não é thread-safe — chamado sequencialmente pelo AI worker.
    """

    def __init__(self, stream_key: str, abandon_seconds: float = _ABANDON_DEFAULT) -> None:
        self._stream_key = stream_key
        self._abandon_seconds = abandon_seconds
        self._tracked: Dict[int, Dict] = {}
        self._next_id = 0

    def process(
        self,
        detections: List[Dict[str, Any]],
        abandon_classes: frozenset,
        person_radius: float,
        now: float,
    ) -> List[Dict[str, Any]]:
        """
        Retorna lista de eventos disparados neste frame.
        Cada evento: {cls_name, cx_norm, cy_norm, duration_seconds, xyxy}
        """
        persons = [d for d in detections if d["cls_name"] == "person"]
        objects = [d for d in detections if d["cls_name"] in abandon_classes]

        # Associa objetos detectados a objetos rastreados por proximidade
        matched_ids = set()
        for obj in objects:
            cx, cy = obj["cx_norm"], obj["cy_norm"]
            best_id, best_dist = None, _MATCH_RADIUS
            for tid, tobj in self._tracked.items():
                d = _dist(cx, cy, tobj["cx"], tobj["cy"])
                if d < best_dist:
                    best_dist = d
                    best_id = tid

            if best_id is not None:
                matched_ids.add(best_id)
                t = self._tracked[best_id]
                t["cx"] = cx
                t["cy"] = cy
                t["last_seen"] = now
                t["xyxy"] = obj.get("xyxy") or t["xyxy"]
            else:
                tid = self._next_id
                self._next_id += 1
                self._tracked[tid] = {
                    "cx": cx,
                    "cy": cy,
                    "cls_name": obj["cls_name"],
                    "first_unattended": None,
                    "last_seen": now,
                    "xyxy": obj.get("xyxy") or [],
                    "alerted": False,
                }

        # Remove objetos que não aparecem há mais de _STALE_SECONDS
        stale = [k for k, v in self._tracked.items() if (now - v["last_seen"]) > _STALE_SECONDS]
        for k in stale:
            del self._tracked[k]

        # Verifica abandono: existe pessoa perto?
        events = []
        for tobj in self._tracked.values():
            cx, cy = tobj["cx"], tobj["cy"]
            has_owner = any(
                _dist(cx, cy, p["cx_norm"], p["cy_norm"]) < person_radius
                for p in persons
            )

            if has_owner:
                tobj["first_unattended"] = None
                tobj["alerted"] = False
            else:
                if tobj["first_unattended"] is None:
                    tobj["first_unattended"] = now
                elif not tobj["alerted"]:
                    duration = now - tobj["first_unattended"]
                    if duration >= self._abandon_seconds:
                        tobj["alerted"] = True
                        events.append({
                            "cls_name": tobj["cls_name"],
                            "cx_norm": cx,
                            "cy_norm": cy,
                            "duration_seconds": round(duration, 1),
                            "xyxy": list(tobj["xyxy"]),
                        })

        return events

    def reset(self) -> None:
        self._tracked.clear()


# ---------------------------------------------------------------------------
# Gerenciador global (uma instância por stream)
# ---------------------------------------------------------------------------

class AbandonedObjectManager:
    """
    Cria e mantém um AbandonedObjectDetector por stream_key.
    Recarrega configuração do .env a cada 30s.
    """

    def __init__(self) -> None:
        self._detectors: Dict[str, AbandonedObjectDetector] = {}
        self._last_reload = 0.0
        self._abandon_seconds = _ABANDON_DEFAULT
        self._abandon_classes: frozenset = _DEFAULT_ABANDON_CLASSES
        self._person_radius = _PERSON_RADIUS

    def _maybe_reload(self) -> None:
        now = time.time()
        if (now - self._last_reload) < 30.0:
            return
        self._last_reload = now
        try:
            self._abandon_seconds = float(os.getenv("AI_ABANDON_SECONDS") or _ABANDON_DEFAULT)
        except Exception:
            self._abandon_seconds = _ABANDON_DEFAULT
        try:
            self._person_radius = float(os.getenv("AI_ABANDON_PERSON_RADIUS") or _PERSON_RADIUS)
        except Exception:
            self._person_radius = _PERSON_RADIUS
        raw = (os.getenv("AI_ABANDON_CLASSES") or "").strip()
        if raw:
            self._abandon_classes = frozenset(c.strip().lower() for c in raw.split(",") if c.strip())
        else:
            self._abandon_classes = _DEFAULT_ABANDON_CLASSES

    def process(
        self,
        stream_key: str,
        detections: List[Dict[str, Any]],
        now: float,
    ) -> List[Dict[str, Any]]:
        """Processa frame e retorna lista de eventos de abandono."""
        self._maybe_reload()
        if not self._abandon_classes:
            return []
        if stream_key not in self._detectors:
            self._detectors[stream_key] = AbandonedObjectDetector(stream_key, self._abandon_seconds)
        return self._detectors[stream_key].process(
            detections, self._abandon_classes, self._person_radius, now
        )

    def reset(self, stream_key: str) -> None:
        det = self._detectors.pop(stream_key, None)
        if det:
            det.reset()
