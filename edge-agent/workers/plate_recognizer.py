"""
ETI SENTINEL - Reconhecimento de Placa Veicular Offline
Detecta região da placa via morfologia OpenCV (sem modelo extra).
Lê o texto da placa com easyocr se instalado (pip install easyocr).
Suporte a whitelist/blacklist configurável.

Modo básico  (sem easyocr): reporta "placa detectada" + foto da região
Modo enhanced (com easyocr): lê texto, valida formato, checa whitelist/blacklist

Configuração via .env:
  ENABLE_PLATE_RECOGNITION=1
  AI_PLATE_WHITELIST=ABC1234,XYZ5678    placas autorizadas (vazio = todas)
  AI_PLATE_BLACKLIST=BAD0000,EVL0001    placas bloqueadas (vazio = nenhuma)
  AI_PLATE_EVENT_COOLDOWN_SECONDS=120  cooldown por veículo
  AI_PLATE_MIN_CONF=0.4                confiança mínima OCR (0-1)
"""

import base64
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Aspect ratio de placas (largura / altura)
_PLATE_RATIO_MIN = 1.8
_PLATE_RATIO_MAX = 6.5
_PLATE_MIN_AREA  = 800   # pixels²

# Formato brasileiro: ABC-1234 (antigo) ou ABC1A23 (Mercosul)
_RE_PLATE_BR = re.compile(r"^[A-Z]{3}[\s\-]?\d{4}$|^[A-Z]{3}\d[A-Z]\d{2}$")

_OCR_READER = None   # instância lazy de easyocr.Reader


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_list(env_key: str) -> set:
    raw = str(os.getenv(env_key) or "").strip()
    if not raw:
        return set()
    return {p.strip().upper().replace("-", "").replace(" ", "") for p in raw.split(",") if p.strip()}


def _normalize_plate(text: str) -> str:
    """Remove espaços, hifens e coloca em maiúsculo."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _is_valid_plate(text: str) -> bool:
    norm = _normalize_plate(text)
    return bool(_RE_PLATE_BR.match(norm))


def _get_ocr_reader():
    global _OCR_READER
    if _OCR_READER is not None:
        return _OCR_READER
    try:
        import easyocr
        _OCR_READER = easyocr.Reader(
            ["en"],
            gpu=False,       # evita dependência de CUDA no edge
            verbose=False,
        )
        logger.info("[Plate] easyocr carregado com sucesso.")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[Plate] easyocr não disponível: {e}")
    return _OCR_READER


# ---------------------------------------------------------------------------
# Detecção da região da placa
# ---------------------------------------------------------------------------

def _find_plate_region(vehicle_crop: "np.ndarray") -> Optional["np.ndarray"]:
    """
    Localiza a região mais provável de placa dentro do crop do veículo.
    Retorna subimagem da placa ou None se não encontrar candidato válido.
    """
    try:
        import cv2
        import numpy as np

        h, w = vehicle_crop.shape[:2]
        if h < 30 or w < 60:
            return None

        # Usa apenas a metade inferior do veículo (frente/traseira)
        lower = vehicle_crop[h // 2:, :]

        gray = cv2.cvtColor(lower, cv2.COLOR_BGR2GRAY)
        blur = cv2.bilateralFilter(gray, 9, 75, 75)
        edges = cv2.Canny(blur, 50, 150)

        # Fechamento morfológico para unir caracteres da placa
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_area = 0
        lh, lw = lower.shape[:2]

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if ch < 8 or cw < 20:
                continue
            area = cw * ch
            if area < _PLATE_MIN_AREA:
                continue
            ratio = cw / float(ch)
            if not (_PLATE_RATIO_MIN <= ratio <= _PLATE_RATIO_MAX):
                continue
            # Não deve ocupar mais que 80% da largura (filtra bordas falsas)
            if cw > lw * 0.80:
                continue
            if area > best_area:
                best_area = area
                best = (x, y, cw, ch)

        if best is None:
            return None

        x, y, cw, ch = best
        pad = 4
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(lw, x + cw + pad)
        y2 = min(lh, y + ch + pad)
        plate_crop = lower[y1:y2, x1:x2]

        if plate_crop.size == 0:
            return None

        # Normaliza tamanho para OCR
        target_h = 60
        scale = target_h / float(plate_crop.shape[0])
        plate_resized = cv2.resize(
            plate_crop,
            (max(1, int(plate_crop.shape[1] * scale)), target_h),
            interpolation=cv2.INTER_CUBIC,
        )
        return plate_resized

    except Exception:
        return None


# ---------------------------------------------------------------------------
# OCR sobre a região da placa
# ---------------------------------------------------------------------------

def _read_plate_text(plate_img: "np.ndarray") -> Tuple[str, float]:
    """
    Tenta ler o texto da placa. Retorna (texto_normalizado, confiança).
    Retorna ("", 0.0) se não conseguir.
    """
    reader = _get_ocr_reader()
    if reader is None:
        return "", 0.0

    try:
        import numpy as np
        results = reader.readtext(plate_img, detail=1, paragraph=False)
        if not results:
            return "", 0.0

        # Concatena todos os tokens lidos com confiança mínima
        min_conf = float(os.getenv("AI_PLATE_MIN_CONF") or "0.4")
        parts = []
        confs = []
        for _bbox, text, conf in results:
            if conf >= min_conf:
                parts.append(text)
                confs.append(conf)

        if not parts:
            return "", 0.0

        full = "".join(parts)
        norm = _normalize_plate(full)
        avg_conf = float(sum(confs) / len(confs))
        return norm, avg_conf

    except Exception:
        return "", 0.0


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class PlateRecognizer:
    """
    Detecta e lê placas de veículos em frames de câmera.
    Integrado no ONNXAIWorker via _run_analytics.
    """

    VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

    def __init__(self) -> None:
        self._whitelist: set = set()
        self._blacklist: set = set()
        self._last_reload = 0.0

    def _maybe_reload(self) -> None:
        now = time.time()
        if (now - self._last_reload) < 30.0:
            return
        self._last_reload = now
        self._whitelist = _load_list("AI_PLATE_WHITELIST")
        self._blacklist = _load_list("AI_PLATE_BLACKLIST")

    def process(
        self,
        frame: "np.ndarray",
        detection: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Processa um veículo detectado e tenta ler sua placa.
        Retorna dict de resultado ou None se não houver placa detectada.
        """
        if detection.get("cls_name") not in self.VEHICLE_CLASSES:
            return None

        try:
            import cv2
            import numpy as np

            h, w = frame.shape[:2]
            x1, y1, x2, y2 = [int(v) for v in detection["xyxy"]]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)

            if (x2 - x1) < 40 or (y2 - y1) < 30:
                return None

            vehicle_crop = frame[y1:y2, x1:x2]
            plate_img = _find_plate_region(vehicle_crop)

            if plate_img is None:
                return None

            # Tenta OCR
            text, conf = _read_plate_text(plate_img)
            valid = _is_valid_plate(text) if text else False

            self._maybe_reload()

            # Gera snapshot da placa (base64)
            snap_b64 = ""
            try:
                ok, buf = cv2.imencode(".jpg", plate_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if ok:
                    snap_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            except Exception:
                pass

            return {
                "plate_text":  text,
                "plate_valid": valid,
                "plate_conf":  round(conf, 3),
                "snap_b64":    snap_b64,
                "whitelist":   set(self._whitelist),
                "blacklist":   set(self._blacklist),
            }

        except Exception:
            return None

    def classify_access(self, plate_text: str, whitelist: set, blacklist: set) -> Tuple[str, str, str]:
        """
        Classifica acesso. Retorna (event_type, severity, emoji).
        """
        norm = _normalize_plate(plate_text) if plate_text else ""
        if blacklist and norm in blacklist:
            return "plate_blacklisted", "critical", "⛔"
        if whitelist and norm and norm not in whitelist:
            return "plate_unauthorized", "warn", "⚠️"
        if norm:
            return "plate_detected", "info", "🚗"
        return "plate_region_detected", "info", "🔍"
