"""
ETI SENTINEL - Modulo de Analiticos de Video
Linha virtual, zona de intrusao, contagem de pessoas.

Configuracao via variaveis de ambiente:
  AI_ZONES            JSON: [[x1,y1,x2,y2], ...]  (coord. 0.0-1.0, relativo ao frame)
  AI_CROSSING_LINES   JSON: [[x1,y1,x2,y2], ...]  (coord. 0.0-1.0)
  AI_PEOPLE_MAX_COUNT Numero maximo de pessoas antes de alertar (padrao: 0 = desabilitado)
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de geometria
# ---------------------------------------------------------------------------

def _cross_sign(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    """Produto vetorial de (B-A) x (P-A). Positivo = esquerda da linha AB."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def _centroid(xyxy: List[float], fw: int, fh: int) -> Optional[Tuple[float, float]]:
    """Retorna (cx_norm, cy_norm) em coordenadas normalizadas 0.0-1.0."""
    if len(xyxy) < 4 or fw <= 0 or fh <= 0:
        return None
    x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
    cx = ((x1 + x2) / 2.0) / float(fw)
    cy = ((y1 + y2) / 2.0) / float(fh)
    return (max(0.0, min(1.0, cx)), max(0.0, min(1.0, cy)))


# ---------------------------------------------------------------------------
# Parser de configuracao
# ---------------------------------------------------------------------------

def _parse_json_list(env_var: str) -> List[Any]:
    raw = (os.getenv(env_var) or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        logger.warning(f"[AI-Analytics] Erro ao parsear {env_var}: valor invalido")
    return []


def load_zones() -> List[Tuple[float, float, float, float]]:
    """
    Lê AI_ZONES: lista de retangulos [x1,y1,x2,y2] em coords normalizadas.
    Exemplo: AI_ZONES=[[0.1,0.1,0.5,0.9],[0.6,0.0,1.0,0.5]]
    """
    zones = []
    for item in _parse_json_list("AI_ZONES"):
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 4:
                x1, y1, x2, y2 = float(item[0]), float(item[1]), float(item[2]), float(item[3])
                zones.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
            elif isinstance(item, dict):
                x1 = float(item.get("x1", 0))
                y1 = float(item.get("y1", 0))
                x2 = float(item.get("x2", 1))
                y2 = float(item.get("y2", 1))
                zones.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
        except Exception:
            continue
    return zones


def load_crossing_lines() -> List[Tuple[float, float, float, float]]:
    """
    Lê AI_CROSSING_LINES: lista de linhas [x1,y1,x2,y2] em coords normalizadas.
    Exemplo: AI_CROSSING_LINES=[[0.5,0.0,0.5,1.0]]  (linha vertical no meio)
    """
    lines = []
    for item in _parse_json_list("AI_CROSSING_LINES"):
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 4:
                lines.append((float(item[0]), float(item[1]), float(item[2]), float(item[3])))
            elif isinstance(item, dict):
                lines.append((
                    float(item.get("x1", 0)),
                    float(item.get("y1", 0)),
                    float(item.get("x2", 1)),
                    float(item.get("y2", 1)),
                ))
        except Exception:
            continue
    return lines


# ---------------------------------------------------------------------------
# Detector de Zona de Intrusao
# ---------------------------------------------------------------------------

class ZoneIntrusionDetector:
    """
    Verifica se o centroide de um objeto esta dentro de uma zona retangular.
    Quando um objeto entra na zona, dispara o evento 'ai_zone_intrusion'.
    """

    def __init__(self) -> None:
        self._zones: List[Tuple[float, float, float, float]] = []
        self._last_reload: float = 0.0
        self._reload_interval: float = 30.0
        self._inside_state: Dict[str, bool] = {}

    def _maybe_reload(self) -> None:
        now = time.time()
        if (now - self._last_reload) >= self._reload_interval:
            self._zones = load_zones()
            self._last_reload = now

    def check(
        self,
        stream_key: str,
        cls_name: str,
        cx_norm: float,
        cy_norm: float,
    ) -> bool:
        """
        Retorna True se o objeto cruzou para DENTRO de uma zona.
        Rastreia estado (dentro/fora) para evitar disparos repetidos enquanto
        o objeto permanece na zona.
        """
        self._maybe_reload()
        if not self._zones:
            return False

        in_any = any(
            x1 <= cx_norm <= x2 and y1 <= cy_norm <= y2
            for (x1, y1, x2, y2) in self._zones
        )

        state_key = f"{stream_key}:{cls_name}"
        was_inside = self._inside_state.get(state_key, False)
        self._inside_state[state_key] = in_any

        if in_any and not was_inside:
            logger.info(f"[AI-Zone] {cls_name} entrou na zona em {stream_key} cx={cx_norm:.2f} cy={cy_norm:.2f}")
            return True
        return False

    def reset(self, stream_key: str) -> None:
        keys = [k for k in self._inside_state if k.startswith(f"{stream_key}:")]
        for k in keys:
            del self._inside_state[k]


# ---------------------------------------------------------------------------
# Detector de Cruzamento de Linha Virtual
# ---------------------------------------------------------------------------

class LineCrossingDetector:
    """
    Detecta quando um objeto cruza uma linha virtual definida por dois pontos.
    Dispara o evento 'ai_line_crossing' apenas na transicao de lado.
    """

    def __init__(self) -> None:
        self._lines: List[Tuple[float, float, float, float]] = []
        self._last_reload: float = 0.0
        self._reload_interval: float = 30.0
        self._side_history: Dict[str, Optional[float]] = {}

    def _maybe_reload(self) -> None:
        now = time.time()
        if (now - self._last_reload) >= self._reload_interval:
            self._lines = load_crossing_lines()
            self._last_reload = now

    def check(
        self,
        stream_key: str,
        cls_name: str,
        cx_norm: float,
        cy_norm: float,
        line_idx: int,
        line: Tuple[float, float, float, float],
    ) -> bool:
        """
        Retorna True se o objeto cruzou a linha (mudou de lado).
        line_idx distingue multiplas linhas por stream.
        """
        x1, y1, x2, y2 = line
        sign = _cross_sign(x1, y1, x2, y2, cx_norm, cy_norm)
        state_key = f"{stream_key}:{cls_name}:{line_idx}"
        prev_sign = self._side_history.get(state_key)

        self._side_history[state_key] = sign

        if prev_sign is None:
            return False

        if sign == 0.0:
            return False

        if (prev_sign > 0) != (sign > 0):
            direction = "entrada" if sign < 0 else "saida"
            logger.info(
                f"[AI-Line] {cls_name} cruzou linha {line_idx} em {stream_key} "
                f"({direction}) cx={cx_norm:.2f} cy={cy_norm:.2f}"
            )
            return True
        return False

    def check_all_lines(
        self,
        stream_key: str,
        cls_name: str,
        cx_norm: float,
        cy_norm: float,
    ) -> bool:
        """Verifica todas as linhas configuradas. Retorna True se cruzou alguma."""
        self._maybe_reload()
        if not self._lines:
            return False
        crossed = False
        for idx, line in enumerate(self._lines):
            if self.check(stream_key, cls_name, cx_norm, cy_norm, idx, line):
                crossed = True
        return crossed

    def reset(self, stream_key: str) -> None:
        keys = [k for k in self._side_history if k.startswith(f"{stream_key}:")]
        for k in keys:
            del self._side_history[k]


# ---------------------------------------------------------------------------
# Contador de Pessoas
# ---------------------------------------------------------------------------

class PeopleCounter:
    """
    Conta o numero de pessoas (classe 'person') detectadas no frame.
    Dispara 'ai_crowd_alert' quando supera AI_PEOPLE_MAX_COUNT.
    Tambem envia contagem periodica como metrica via 'ai_people_count'.
    """

    def __init__(self) -> None:
        self._last_count: Dict[str, int] = {}
        self._last_metric_ts: Dict[str, float] = {}
        self._metric_interval: float = 30.0

    def process(
        self,
        stream_key: str,
        person_count: int,
    ) -> Tuple[bool, bool]:
        """
        Retorna (crowd_alert, should_send_metric).
        crowd_alert = True se superar o limite configurado.
        should_send_metric = True se for hora de enviar contagem periodica.
        """
        try:
            max_count = int(os.getenv("AI_PEOPLE_MAX_COUNT") or 0)
        except Exception:
            max_count = 0

        crowd_alert = False
        if max_count > 0 and person_count >= max_count:
            prev = self._last_count.get(stream_key, 0)
            if person_count > prev or prev < max_count:
                crowd_alert = True
                logger.info(
                    f"[AI-Count] Alerta de lotacao em {stream_key}: "
                    f"{person_count} pessoas (limite: {max_count})"
                )

        self._last_count[stream_key] = person_count

        now = time.time()
        last_metric = self._last_metric_ts.get(stream_key, 0.0)
        send_metric = (now - last_metric) >= self._metric_interval
        if send_metric:
            self._last_metric_ts[stream_key] = now

        return crowd_alert, send_metric


# ---------------------------------------------------------------------------
# Extrator de bounding boxes
# ---------------------------------------------------------------------------

def extract_detections(
    boxes: Any,
    names: Dict[int, str],
    fw: int,
    fh: int,
    allowed_classes: Optional[set] = None,
    conf_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Extrai lista de detecções do resultado YOLO com centroide normalizado.
    Cada item: {cls_name, conf, cx_norm, cy_norm, xyxy}
    """
    detections = []
    if boxes is None:
        return detections

    try:
        for b in boxes:
            try:
                cls_idx = int(b.cls[0]) if hasattr(b, "cls") else int(getattr(b, "cls", 0))
                conf = float(b.conf[0]) if hasattr(b, "conf") else float(getattr(b, "conf", 0.0))
                cls_name = str(names.get(cls_idx) or str(cls_idx)).strip().lower()

                if conf < conf_threshold:
                    continue
                if allowed_classes and cls_name not in allowed_classes:
                    continue

                xyxy_raw = getattr(b, "xyxy", None)
                if xyxy_raw is None:
                    continue
                if hasattr(xyxy_raw, "tolist"):
                    xy = xyxy_raw[0].tolist() if hasattr(xyxy_raw, "__len__") else xyxy_raw.tolist()
                else:
                    xy = list(xyxy_raw[0]) if hasattr(xyxy_raw, "__len__") else list(xyxy_raw)

                if len(xy) < 4:
                    continue

                centroid = _centroid(xy, fw, fh)
                if centroid is None:
                    continue

                detections.append({
                    "cls_name": cls_name,
                    "conf": conf,
                    "cx_norm": centroid[0],
                    "cy_norm": centroid[1],
                    "xyxy": xy,
                })
            except Exception:
                continue
    except Exception:
        pass

    return detections
