"""
ETI SENTINEL - AI Worker com ONNX Runtime
==========================================
Motor de inferencia leve: sem PyTorch, sem ultralytics.
Requer apenas: onnxruntime (~15 MB) + opencv-python.

Compativel com modelos YOLOv8 exportados via exportar_modelo.py.

Variaveis de ambiente:
  AI_ONNX_MODEL          Caminho do modelo .onnx (padrao: bin/modelo_ia.onnx)
  AI_ONNX_CLASSES        Caminho do JSON de classes (padrao: bin/onnx_classes.json)
  AI_CONF_THRESHOLD      Confianca minima 0.0-1.0 (padrao: 0.50)
  AI_NMS_THRESHOLD       Limiar de NMS 0.0-1.0 (padrao: 0.45)
  AI_IMAGE_SIZE          Tamanho de entrada do modelo (padrao: 640)
  AI_CLASSES             Classes permitidas, separadas por virgula
  AI_PEOPLE_MAX_COUNT    Alerta de lotacao (0 = desabilitado)
  AI_ZONES               Zonas de intrusao JSON
  AI_CROSSING_LINES      Linhas virtuais JSON
  AI_FRAME_EVERY_SECONDS Intervalo entre frames analisados (padrao: 1.0)
  AI_EVENT_COOLDOWN_SECONDS Cooldown entre eventos (padrao: 45)
  AI_STARTUP_DELAY_SECONDS  Delay de inicio em segundos (padrao: 20)
  ENABLE_AI_ANALYTICS    1 para ativar (padrao: 0)
"""

import base64
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

logger = logging.getLogger(__name__)

# Classes COCO padrao (fallback se onnx_classes.json nao existir)
_COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana",
    "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table",
    "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]

# Classes de animais — usadas para rejeitar falsos positivos de "pessoa"
_ANIMAL_CLASSES: Set[str] = {
    "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe",
}


# ---------------------------------------------------------------------------
# Nomes em portugues e cores por classe
# ---------------------------------------------------------------------------

_LABELS_PT: Dict[str, str] = {
    "person":     "Pessoa",
    "car":        "Carro",
    "motorcycle": "Moto",
    "truck":      "Caminhao",
    "bus":        "Onibus",
    "bicycle":    "Bicicleta",
    "dog":        "Cachorro",
    "cat":        "Gato",
    "boat":       "Embarcacao",
    "airplane":   "Aviao",
}

_EMOJIS_CLS: Dict[str, str] = {
    "person":     "👤",
    "car":        "🚗",
    "motorcycle": "🏍",
    "truck":      "🚛",
    "bus":        "🚌",
    "bicycle":    "🚲",
    "boat":       "⛵",
    "airplane":   "✈️",
}

# BGR para OpenCV
_CLASS_COLORS: Dict[str, tuple] = {
    "person":     (0, 230, 0),    # Verde
    "car":        (0, 165, 255),  # Laranja
    "motorcycle": (0, 165, 255),  # Laranja
    "truck":      (0, 80, 255),   # Vermelho-laranja
    "bus":        (0, 0, 255),    # Vermelho
    "bicycle":    (255, 200, 0),  # Ciano
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _sanitize(s: Any) -> str:
    return str(s or "").strip()


def _csv_set(s: str) -> Set[str]:
    return {x.strip().lower() for x in (_sanitize(s) or "").split(",") if x.strip()}


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


# ---------------------------------------------------------------------------
# Pre/Pos-processamento ONNX YOLOv8
# ---------------------------------------------------------------------------

def _find_model() -> Optional[str]:
    """Procura o modelo ONNX em varios locais."""
    env_path = _sanitize(os.getenv("AI_ONNX_MODEL"))
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        Path(os.environ.get("PROGRAMDATA", "")) / "ETI-SENTINEL" / "bin" / "modelo_ia.onnx",
        Path(__file__).resolve().parent.parent.parent / "bin" / "modelo_ia.onnx",
        Path(__file__).resolve().parent.parent / "bin" / "modelo_ia.onnx",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _load_classes() -> List[str]:
    """Carrega nomes das classes do JSON ou usa COCO padrao."""
    env_path = _sanitize(os.getenv("AI_ONNX_CLASSES"))
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates += [
        Path(os.environ.get("PROGRAMDATA", "")) / "ETI-SENTINEL" / "bin" / "onnx_classes.json",
        Path(__file__).resolve().parent.parent.parent / "bin" / "onnx_classes.json",
        Path(__file__).resolve().parent.parent / "bin" / "onnx_classes.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                    classes = data.get("classes") or data
                    if isinstance(classes, list) and classes:
                        logger.info(f"[AI-ONNX] Classes carregadas: {p} ({len(classes)} classes)")
                        return [str(c).lower() for c in classes]
            except Exception:
                continue
    return _COCO_CLASSES


def _letterbox(img, new_shape=640, color=(114, 114, 114)):
    """Redimensiona mantendo proporcao e preenche com cinza."""
    import numpy as np
    import cv2

    h, w = img.shape[:2]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    scale = min(new_shape[0] / h, new_shape[1] / w)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    dw = (new_shape[1] - new_w) / 2
    dh = (new_shape[0] - new_h) / 2

    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    top = int(round(dh - 0.1))
    bottom = int(round(dh + 0.1))
    left = int(round(dw - 0.1))
    right = int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

    # Retorna o padding inteiro real aplicado (não o float dw/dh)
    # Garante que _postprocess desfaça exatamente os pixels adicionados
    return img, scale, (left, top)


def _preprocess(frame, img_size: int = 640):
    """Prepara o frame para inferencia ONNX."""
    import numpy as np
    import cv2

    img, scale, pad = _letterbox(frame, img_size)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    img = img.transpose(2, 0, 1)                    # HWC -> CHW
    img = np.expand_dims(img, axis=0)               # CHW -> BCHW
    return img, scale, pad


def _postprocess(
    output: Any,
    scale: float,
    pad: Tuple[float, float],
    orig_h: int,
    orig_w: int,
    conf_threshold: float = 0.50,
    nms_threshold: float = 0.45,
    classes: Optional[List[str]] = None,
    allowed_classes: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Decodifica saida YOLOv8 ONNX: [1, 84, 8400] -> lista de deteccoes."""
    import numpy as np
    import cv2

    pred = output[0]                        # [1, 84, 8400] -> [84, 8400]
    if pred.ndim == 3:
        pred = pred[0]
    pred = pred.T                           # [8400, 84]

    num_classes = pred.shape[1] - 4
    boxes_xywh = pred[:, :4]               # cx, cy, w, h (em pixels do input)
    scores_all = pred[:, 4:]               # [8400, num_classes]

    class_ids = np.argmax(scores_all, axis=1)
    confidences = scores_all[np.arange(len(scores_all)), class_ids]

    mask = confidences >= conf_threshold
    if not mask.any():
        return []

    boxes_xywh = boxes_xywh[mask]
    confidences = confidences[mask]
    class_ids = class_ids[mask]
    scores_filtered = scores_all[mask]  # scores completos para checagem runner-up

    # Converte xywh -> xyxy no espaco do input (640x640)
    x1 = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
    y1 = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
    x2 = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
    y2 = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2

    # Desfaz o letterbox para coordenadas do frame original
    x1 = np.clip((x1 - pad[0]) / scale, 0, orig_w)
    y1 = np.clip((y1 - pad[1]) / scale, 0, orig_h)
    x2 = np.clip((x2 - pad[0]) / scale, 0, orig_w)
    y2 = np.clip((y2 - pad[1]) / scale, 0, orig_h)

    # NMS via OpenCV (sem torchvision)
    boxes_nms = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
    confs_nms = confidences.tolist()
    indices = cv2.dnn.NMSBoxes(boxes_nms, confs_nms, conf_threshold, nms_threshold)

    if indices is None or len(indices) == 0:
        return []

    indices = indices.flatten() if hasattr(indices, "flatten") else list(indices)

    results = []
    for i in indices:
        cls_id = int(class_ids[i])
        cls_name = (classes[cls_id] if classes and cls_id < len(classes) else str(cls_id)).lower()

        if allowed_classes and cls_name not in allowed_classes:
            continue

        fx1, fy1, fx2, fy2 = float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i])

        # ---- Filtros anti-falso-positivo exclusivos para "pessoa" ----
        if cls_name == "person":
            box_w = fx2 - fx1
            box_h = fy2 - fy1

            # Filtro 1 — proporção: pessoa é mais alta que larga.
            # Animal de 4 patas tem caixa bem mais larga que alta (aspect < 0.4).
            if box_w > 0 and box_h > 0 and (box_h / box_w) < 0.4:
                continue

            # Filtro 2 — runner-up: se o 2º melhor palpite do modelo for um animal
            # e a diferença de confiança for pequena (< 0.15), o modelo está em dúvida
            # → rejeita para evitar falso alarme.
            scores_i = scores_filtered[i]
            sorted_ids = np.argsort(scores_i)[::-1]
            if len(sorted_ids) > 1:
                runner_up_id = int(sorted_ids[1])
                runner_up_name = (classes[runner_up_id] if classes and runner_up_id < len(classes) else "").lower()
                if runner_up_name in _ANIMAL_CLASSES and (float(confidences[i]) - float(scores_i[runner_up_id])) < 0.15:
                    continue

        cx_norm = ((fx1 + fx2) / 2.0) / max(1, orig_w)
        cy_norm = ((fy1 + fy2) / 2.0) / max(1, orig_h)

        results.append({
            "cls_name": cls_name,
            "cls_id": cls_id,
            "conf": float(confidences[i]),
            "xyxy": [fx1, fy1, fx2, fy2],
            "cx_norm": max(0.0, min(1.0, cx_norm)),
            "cy_norm": max(0.0, min(1.0, cy_norm)),
        })

    return results


# ---------------------------------------------------------------------------
# Captura de frame via OpenCV
# ---------------------------------------------------------------------------

class _CapManager:
    """Gerencia conexoes VideoCapture com backoff automatico."""

    def __init__(self) -> None:
        self._caps: Dict[str, Any] = {}
        self._fail_ts: Dict[str, float] = {}

    def get(self, stream_key: str, source_url: str, backoff_s: float = 5.0):
        import cv2
        cap = self._caps.get(stream_key)
        if cap is not None:
            return cap

        now = time.time()
        if (now - float(self._fail_ts.get(stream_key) or 0)) < backoff_s:
            return None

        try:
            cap = cv2.VideoCapture(source_url, cv2.CAP_FFMPEG)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            if not cap.isOpened():
                cap.release()
                self._fail_ts[stream_key] = time.time()
                return None
            # Descarta os primeiros frames: decodificador RTSP demora
            # alguns frames para inicializar e retorna cinza nesse período.
            for _ in range(5):
                cap.grab()
            self._caps[stream_key] = cap
            return cap
        except Exception:
            self._fail_ts[stream_key] = time.time()
            return None

    def release(self, stream_key: str) -> None:
        cap = self._caps.pop(stream_key, None)
        try:
            if cap:
                cap.release()
        except Exception:
            pass

    def release_inactive(self, active_keys: Set[str]) -> None:
        for k in list(self._caps):
            if k not in active_keys:
                self.release(k)


# ---------------------------------------------------------------------------
# Worker Principal
# ---------------------------------------------------------------------------

class ONNXAIWorker:
    """
    Worker de IA usando ONNX Runtime — leve, sem PyTorch.
    Interface compativel com AIWorker para substituicao direta.
    """

    def __init__(self, stream_manager) -> None:
        self.manager = stream_manager
        self.running = True
        self._sess = requests.Session()
        self._last_event_ts: Dict[Tuple[int, int, str], float] = {}
        self._last_frame_ts: Dict[str, float] = {}
        self._ort_session = None
        self._classes: List[str] = []
        self._cap_manager = _CapManager()
        self._stream_urls: Dict[str, str] = {}  # stream_key -> URL da câmera

        # Analiticos avancados
        self._analytics_available = False
        try:
            from workers.ai_analytics import ZoneIntrusionDetector, LineCrossingDetector, PeopleCounter
            self._zone_detector = ZoneIntrusionDetector()
            self._line_detector = LineCrossingDetector()
            self._people_counter = PeopleCounter()
            self._analytics_available = True
        except ImportError:
            try:
                from ai_analytics import ZoneIntrusionDetector, LineCrossingDetector, PeopleCounter
                self._zone_detector = ZoneIntrusionDetector()
                self._line_detector = LineCrossingDetector()
                self._people_counter = PeopleCounter()
                self._analytics_available = True
            except ImportError:
                pass

        # Detecção de abandono de objeto
        self._abandon_manager = None
        try:
            from workers.abandoned_object_detector import AbandonedObjectManager
            self._abandon_manager = AbandonedObjectManager()
        except ImportError:
            try:
                from abandoned_object_detector import AbandonedObjectManager
                self._abandon_manager = AbandonedObjectManager()
            except ImportError:
                pass

        # Reconhecimento de placa veicular
        self._plate_recognizer = None
        try:
            from workers.plate_recognizer import PlateRecognizer
            self._plate_recognizer = PlateRecognizer()
        except ImportError:
            try:
                from plate_recognizer import PlateRecognizer
                self._plate_recognizer = PlateRecognizer()
            except ImportError:
                pass

        # Aprendizado comportamental
        self._behavior = None
        try:
            from workers.behavioral_learner import BehavioralLearner
            self._behavior = BehavioralLearner()
        except ImportError:
            try:
                from behavioral_learner import BehavioralLearner
                self._behavior = BehavioralLearner()
            except ImportError:
                pass

        # Contador direcional de pessoas (Feature #7)
        self._directional_counter = None
        try:
            from workers.directional_counter import DirectionalCounter
            self._directional_counter = DirectionalCounter()
        except ImportError:
            try:
                from directional_counter import DirectionalCounter
                self._directional_counter = DirectionalCounter()
            except ImportError:
                pass

        # Detector de permanência prolongada (Feature #8)
        self._loitering_detector = None
        try:
            from workers.loitering_detector import LoiteringDetector
            self._loitering_detector = LoiteringDetector()
        except ImportError:
            try:
                from loitering_detector import LoiteringDetector
                self._loitering_detector = LoiteringDetector()
            except ImportError:
                pass

        # Mapa de calor de movimentação (Feature #9)
        self._heatmap = None
        try:
            from workers.heatmap_generator import HeatmapGenerator
            self._heatmap = HeatmapGenerator()
        except ImportError:
            try:
                from heatmap_generator import HeatmapGenerator
                self._heatmap = HeatmapGenerator()
            except ImportError:
                pass

    def stop(self) -> None:
        self.running = False

    # ---- Carregamento do modelo ----

    def _load_model(self) -> bool:
        if self._ort_session is not None:
            return True
        try:
            import onnxruntime as ort
        except ImportError:
            logger.error("[AI-ONNX] onnxruntime nao instalado. Execute: pip install onnxruntime-directml")
            return False

        model_path = _find_model()
        if not model_path:
            logger.warning("[AI-ONNX] Modelo ONNX nao encontrado. Execute: python exportar_modelo.py")
            return False

        try:
            providers = []
            available = ort.get_available_providers()
            if "DmlExecutionProvider" in available:
                providers.append("DmlExecutionProvider")
                logger.info("[AI-ONNX] Aceleracao GPU Windows (DirectML) habilitada.")
            elif "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
                logger.info("[AI-ONNX] Aceleracao NVIDIA CUDA habilitada.")
            else:
                logger.info("[AI-ONNX] Modo CPU (GPU nao disponivel).")
            providers.append("CPUExecutionProvider")

            self._ort_session = ort.InferenceSession(model_path, providers=providers)
            self._classes = _load_classes()
            logger.info(f"[AI-ONNX] Modelo carregado: {model_path} ({len(self._classes)} classes)")
            return True
        except Exception as e:
            logger.error(f"[AI-ONNX] Erro ao carregar modelo: {e}")
            return False

    # ---- Analise de frame ----

    def _should_analyze(self, stream_key: str, now: float) -> bool:
        interval = _env_float("AI_FRAME_EVERY_SECONDS", 1.0)
        last = float(self._last_frame_ts.get(stream_key) or 0.0)
        if last and (now - last) < max(0.1, interval):
            return False
        self._last_frame_ts[stream_key] = now
        return True

    def _cooldown_ok(self, device_id: int, channel: int, event_key: str, now: float) -> bool:
        cooldown = _env_float("AI_EVENT_COOLDOWN_SECONDS", 45.0)
        k = (int(device_id), int(channel), event_key)
        last = float(self._last_event_ts.get(k) or 0.0)
        if last and (now - last) < cooldown:
            return False
        self._last_event_ts[k] = now
        return True

    # ---- Snapshot com bounding boxes ----

    def _snapshot_b64(
        self,
        frame: Any,
        stream_key: str,
        detections: Optional[List[Dict]] = None,
    ) -> str:
        if not _bool(os.getenv("AI_SEND_SNAPSHOT") or "1"):
            return ""
        try:
            import cv2

            max_w   = _env_int("AI_SNAPSHOT_MAX_WIDTH", 1280)
            quality = _env_int("AI_SNAPSHOT_JPEG_QUALITY", 90)

            # Tenta capturar frame limpo via FFmpeg para resolver H.265/NV12.
            # Cameras com H.265 geram frame cinza no OpenCV do EXE (bug de
            # conversao de pixel format NV12 -> BGR). O FFmpeg do sistema
            # entrega a imagem com cores corretas.
            source_url = self._stream_urls.get(stream_key, "")
            if source_url:
                clean = self._capture_clean_frame(source_url)
                if clean is not None:
                    frame = clean

            img = frame.copy()
            h, w = img.shape[:2]

            # --- Desenha caixas ao redor de cada objeto detectado ---
            if detections:
                font       = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = max(0.45, min(0.75, w / 1000))
                thickness  = max(1, int(w / 400))

                for det in detections:
                    try:
                        x1, y1, x2, y2 = [int(v) for v in det["xyxy"]]
                        cls_name = det["cls_name"]
                        conf     = det["conf"]
                        color    = _CLASS_COLORS.get(cls_name, (0, 200, 255))
                        label_pt = _LABELS_PT.get(cls_name, cls_name.capitalize())
                        label    = f"{label_pt} {int(conf * 100)}%"

                        # Retangulo ao redor do objeto
                        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness + 1)

                        # Fundo escuro para o texto
                        (lw, lh), _ = cv2.getTextSize(label, font, font_scale, thickness)
                        cv2.rectangle(img, (x1, max(0, y1 - lh - 10)), (x1 + lw + 6, y1), color, -1)
                        cv2.putText(img, label, (x1 + 3, y1 - 4), font, font_scale, (255, 255, 255), thickness)
                    except Exception:
                        continue

            # --- Redimensiona se necessario ---
            # INTER_AREA é o melhor algoritmo para redução de tamanho:
            # preserva detalhes finos sem artefatos de aliasing.
            if max_w > 0 and w > max_w:
                scale = float(max_w) / float(w)
                img = cv2.resize(
                    img, (max_w, max(1, int(h * scale))),
                    interpolation=cv2.INTER_AREA,
                )

            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if ok:
                return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception:
            pass
        return ""

    # ---- Captura de frame limpo via FFmpeg do sistema ----

    def _ffmpeg_path(self) -> Optional[str]:
        """Localiza o FFmpeg instalado junto com o ETI SENTINEL."""
        candidates = [
            Path(os.environ.get("PROGRAMDATA", "")) / "ETI-SENTINEL" / "bin" / "ffmpeg.exe",
            Path(__file__).resolve().parent.parent.parent / "bin" / "ffmpeg.exe",
            Path(__file__).resolve().parent.parent / "bin" / "ffmpeg.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        found = shutil.which("ffmpeg")
        return found if found else None

    def _capture_clean_frame(self, source_url: str) -> Optional[Any]:
        """
        Captura um frame diretamente via FFmpeg do sistema.

        Resolve o problema de H.265/NV12: o OpenCV interno do EXE nao
        converte corretamente o pixel format, resultando em imagem cinza.
        O FFmpeg do sistema tem suporte completo a H.265 e entrega JPEG
        correto que o OpenCV decodifica sem distorcoes.
        """
        import numpy as np
        import cv2

        ffmpeg = self._ffmpeg_path()
        if not ffmpeg:
            return None
        try:
            cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-i", source_url,
                "-vframes", "1",
                "-q:v", "3",
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "pipe:1",
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=8)
            if result.returncode == 0 and result.stdout:
                arr = np.frombuffer(result.stdout, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None and float(np.std(img)) > 4.0:
                    return img
        except Exception as exc:
            logger.debug(f"[AI-ONNX] FFmpeg clean frame falhou: {exc}")
        return None

    # ---- Envio de evento ----

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
        payload: Dict[str, Any] = {
            "token": token or "x",
            "device_id": int(device_id),
            "channel": int(channel),
            "event_type": _sanitize(event_type),
            "severity": _sanitize(severity) or "info",
            "description": str(description)[:400],
        }
        if snapshot_jpg_b64:
            payload["snapshot_jpg_b64"] = snapshot_jpg_b64
        if isinstance(extra, dict):
            for k, v in extra.items():
                kk = _sanitize(k)
                if kk and kk not in payload:
                    if isinstance(v, (int, float, str, list)):
                        payload[kk] = v
        try:
            r = self._sess.post(url, json=payload, headers={"x-event-source": "ai-onnx"}, timeout=(3, 8))
            return r.status_code == 200
        except Exception:
            return False

    # ---- Loop principal ----

    def run(self) -> None:
        if not _bool(os.getenv("ENABLE_AI_ANALYTICS") or "0"):
            logger.info("[AI-ONNX] ENABLE_AI_ANALYTICS=0, worker desativado.")
            return

        if not self._load_model():
            logger.error("[AI-ONNX] Nao foi possivel carregar o modelo. Worker encerrado.")
            return

        try:
            import cv2
            import numpy as np
        except ImportError:
            logger.error("[AI-ONNX] opencv-python nao instalado. Execute: pip install opencv-python")
            return

        logger.info("[AI-ONNX] Worker iniciado (ONNX Runtime).")

        conf_threshold = _env_float("AI_CONF_THRESHOLD", 0.50)
        nms_threshold = _env_float("AI_NMS_THRESHOLD", 0.45)
        img_size = _env_int("AI_IMAGE_SIZE", 640)
        allowed_classes = _csv_set(os.getenv("AI_CLASSES") or "person,car,motorcycle,truck,bus")
        source_tmpl = _sanitize(os.getenv("AI_SOURCE_URL_TEMPLATE") or "rtsp://127.0.0.1:8554/{stream_key}")

        input_name = self._ort_session.get_inputs()[0].name

        while self.running:
            try:
                active = self.manager.get_configs() or {}
                self._cap_manager.release_inactive(set(active.keys()))
                now = time.time()

                for stream_key, cfg in active.items():
                    try:
                        device_id = int(cfg.get("device_id") or 0)
                        channel = int(cfg.get("channel") or 0)
                        token = _sanitize(cfg.get("token") or "")
                        tags = list(cfg.get("tags") or [])

                        if device_id <= 0:
                            continue
                        if not self._should_analyze(stream_key, now):
                            continue

                        source_url = source_tmpl.replace("{stream_key}", stream_key)
                        self._stream_urls[stream_key] = source_url  # usado pelo _snapshot_b64
                        backoff = _env_float("AI_RECONNECT_BACKOFF_SECONDS", 5.0)
                        cap = self._cap_manager.get(stream_key, source_url, backoff)
                        if cap is None:
                            continue

                        ok, frame = cap.read()
                        if not ok or frame is None:
                            self._cap_manager.release(stream_key)
                            continue

                        # Normaliza formato: algumas câmeras enviam greyscale
                        # (visão noturna) ou BGRA — converte sempre para BGR
                        if frame.ndim == 2:
                            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                        elif frame.ndim == 3 and frame.shape[2] == 4:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                        # Descarta frame corrompido: decodificador não
                        # inicializado ou pacote perdido geram cinza uniforme.
                        # std < 4 significa todos os pixels quase iguais.
                        if frame.size == 0 or float(np.std(frame)) < 4.0:
                            logger.debug(
                                f"[AI-ONNX] Frame descartado em {stream_key} "
                                f"(cinza/corrompido, std={np.std(frame):.1f})"
                            )
                            continue

                        orig_h, orig_w = frame.shape[:2]

                        # ---- Inferencia ONNX ----
                        try:
                            input_tensor, scale, pad = _preprocess(frame, img_size)
                            output = self._ort_session.run(None, {input_name: input_tensor})
                            detections = _postprocess(
                                output, scale, pad, orig_h, orig_w,
                                conf_threshold, nms_threshold,
                                self._classes, allowed_classes or None,
                            )
                        except Exception as e:
                            logger.debug(f"[AI-ONNX] Inferencia falhou em {stream_key}: {e}")
                            continue

                        # ---- Aprendizado comportamental ----
                        person_count = sum(1 for d in detections if d["cls_name"] == "person")
                        behavior_suppress = False
                        if self._behavior:
                            self._behavior.record(stream_key, person_count, now)
                            is_anom, binfo = self._behavior.is_anomalous(stream_key, person_count)
                            # Suprime alertas de pessoa quando comportamento é normal
                            # (não suprime intrusão de zona, cruzamento de linha, etc.)
                            if binfo.get("status") == "monitorando" and not is_anom:
                                behavior_suppress = True

                        # ---- Eventos por classe detectada ----
                        best_by_event: Dict[str, Dict] = {}
                        for det in detections:
                            ev_type = f"ai_{det['cls_name']}_detected"
                            prev = best_by_event.get(ev_type)
                            if prev is None or det["conf"] > prev["conf"]:
                                best_by_event[ev_type] = det

                        # Todas as deteccoes validas para desenhar na foto
                        valid_dets = list(best_by_event.values())

                        for ev_type, det in best_by_event.items():
                            cls_name = det["cls_name"]
                            conf     = det["conf"]
                            now_evt  = time.time()
                            if not self._cooldown_ok(device_id, channel, ev_type, now_evt):
                                continue

                            # Suprime ai_person_detected quando comportamento é normal
                            if behavior_suppress and ev_type == "ai_person_detected":
                                continue

                            sev      = "warn" if cls_name == "person" else "info"
                            emoji    = _EMOJIS_CLS.get(cls_name, "🔍")
                            label_pt = _LABELS_PT.get(cls_name, cls_name.capitalize())
                            cam_name = _sanitize(cfg.get("name") or stream_key)

                            # Mensagem amigavel em portugues
                            msg = (
                                f"{emoji} {label_pt} detectada"
                                f" • Cam: {cam_name}"
                                f" • Confianca: {int(conf * 100)}%"
                            )

                            # Foto com caixas desenhadas
                            snap = self._snapshot_b64(frame, stream_key, valid_dets)

                            self._push_event(
                                token, device_id, channel, ev_type, sev, msg,
                                snapshot_jpg_b64=snap,
                                extra={
                                    "ai_class":   cls_name,
                                    "ai_conf":    round(conf, 3),
                                    "ai_label":   label_pt,
                                    "device_type": cfg.get("device_type") or "",
                                    "tags":        tags,
                                },
                            )

                        # ---- Mapa de calor de movimentacao (Feature #9) ----
                        if self._heatmap and _bool(os.getenv("ENABLE_HEATMAP") or "0"):
                            try:
                                self._heatmap.record(stream_key, detections, frame)
                                hm = self._heatmap.maybe_generate(stream_key, now)
                                if hm:
                                    cam_name  = _sanitize(cfg.get("name") or stream_key)
                                    interval  = int(_env_float("AI_HEATMAP_INTERVAL_MINUTES", 60))
                                    total_det = hm["total_detections"]
                                    desc = (
                                        f"🌡️ Mapa de calor • Cam: {cam_name}"
                                        f" • {total_det} detecções no último {interval}min"
                                    )
                                    self._push_event(
                                        token, device_id, channel,
                                        "ai_heatmap", "info", desc,
                                        snapshot_jpg_b64=hm["image_b64"],
                                        extra={
                                            "heatmap_total":   total_det,
                                            "heatmap_peak":    hm["grid_max"],
                                            "heatmap_minutes": interval,
                                            "tags":            tags + ["ai_heatmap"],
                                            "device_type":     cfg.get("device_type") or "",
                                        },
                                    )
                            except Exception:
                                pass

                        # ---- Analiticos avancados (zona, linha, contagem) ----
                        if self._analytics_available and detections:
                            self._run_analytics(
                                stream_key, token, device_id, channel,
                                cfg, detections, frame, now,
                            )

                    except Exception:
                        continue

            except Exception as e:
                logger.error(f"[AI-ONNX] Erro no loop principal: {e}")

            time.sleep(max(0.05, _env_float("AI_LOOP_SLEEP_SECONDS", 0.3)))

        logger.info("[AI-ONNX] Worker encerrado.")

    # ---- Analiticos avancados ----

    def _run_analytics(
        self,
        stream_key: str,
        token: str,
        device_id: int,
        channel: int,
        cfg: Dict[str, Any],
        detections: List[Dict],
        frame: Any,
        now: float,
    ) -> None:
        tags = list(cfg.get("tags") or [])

        if bool(os.getenv("AI_ZONES")):
            for det in detections:
                try:
                    if self._zone_detector.check(stream_key, det["cls_name"], det["cx_norm"], det["cy_norm"]):
                        if self._cooldown_ok(device_id, channel, f"zone:{det['cls_name']}", now):
                            self._push_event(
                                token, device_id, channel, "ai_zone_intrusion", "warn",
                                f"{det['cls_name']} entrou na zona monitorada (conf={det['conf']:.2f})",
                                snapshot_jpg_b64=self._snapshot_b64(frame, stream_key),
                                extra={"ai_class": det["cls_name"], "ai_conf": det["conf"],
                                       "ai_cx": det["cx_norm"], "ai_cy": det["cy_norm"],
                                       "tags": tags + ["ai_zone"],
                                       "device_type": cfg.get("device_type") or ""},
                            )
                except Exception:
                    continue

        if bool(os.getenv("AI_CROSSING_LINES")):
            for det in detections:
                try:
                    if self._line_detector.check_all_lines(stream_key, det["cls_name"], det["cx_norm"], det["cy_norm"]):
                        if self._cooldown_ok(device_id, channel, f"line:{det['cls_name']}", now):
                            self._push_event(
                                token, device_id, channel, "ai_line_crossing", "warn",
                                f"{det['cls_name']} cruzou linha virtual (conf={det['conf']:.2f})",
                                snapshot_jpg_b64=self._snapshot_b64(frame, stream_key),
                                extra={"ai_class": det["cls_name"], "ai_conf": det["conf"],
                                       "tags": tags + ["ai_line"],
                                       "device_type": cfg.get("device_type") or ""},
                            )
                except Exception:
                    continue

        person_count = sum(1 for d in detections if d["cls_name"] == "person")
        try:
            crowd_alert, send_metric = self._people_counter.process(stream_key, person_count)
            if crowd_alert:
                max_count = _env_int("AI_PEOPLE_MAX_COUNT", 0)
                self._push_event(
                    token, device_id, channel, "ai_crowd_alert", "warn",
                    f"Lotacao: {person_count} pessoas (limite: {max_count})",
                    snapshot_jpg_b64=self._snapshot_b64(frame, stream_key),
                    extra={"ai_people_count": person_count, "tags": tags + ["ai_count"],
                           "device_type": cfg.get("device_type") or ""},
                )
            if send_metric and person_count > 0:
                self._push_event(
                    token, device_id, channel, "ai_people_count", "info",
                    f"Contagem: {person_count} pessoa(s) em cena",
                    extra={"ai_people_count": person_count, "tags": tags,
                           "device_type": cfg.get("device_type") or ""},
                )
        except Exception:
            pass

        # ---- Reconhecimento de placa veicular ----
        if self._plate_recognizer and _bool(os.getenv("ENABLE_PLATE_RECOGNITION") or "0"):
            try:
                vehicle_dets = [d for d in detections if d["cls_name"] in {"car", "truck", "bus", "motorcycle"}]
                for vdet in vehicle_dets[:3]:   # máximo 3 veículos por frame
                    plate_key = f"plate:{vdet['cls_name']}:{int(vdet['cx_norm']*100)}"
                    if not self._cooldown_ok(device_id, channel, plate_key, now):
                        continue
                    result = self._plate_recognizer.process(frame, vdet)
                    if result is None:
                        continue
                    ev_type, severity, emoji = self._plate_recognizer.classify_access(
                        result["plate_text"], result["whitelist"], result["blacklist"]
                    )
                    cam_name = _sanitize(cfg.get("name") or stream_key)
                    if result["plate_text"]:
                        plate_disp = result["plate_text"]
                        conf_pct   = int(result["plate_conf"] * 100)
                        desc = f"{emoji} Placa: {plate_disp} ({conf_pct}%) • Cam: {cam_name}"
                    else:
                        desc = f"🔍 Região de placa detectada (sem leitura OCR) • Cam: {cam_name}"
                    snap = self._snapshot_b64(frame, stream_key, [vdet]) if not result["snap_b64"] else ""
                    self._push_event(
                        token, device_id, channel, ev_type, severity, desc,
                        snapshot_jpg_b64=result["snap_b64"] or snap,
                        extra={
                            "plate_text":  result["plate_text"],
                            "plate_valid": result["plate_valid"],
                            "plate_conf":  result["plate_conf"],
                            "ai_class":    vdet["cls_name"],
                            "tags":        tags + ["plate"],
                            "device_type": cfg.get("device_type") or "",
                        },
                    )
            except Exception:
                pass

        # ---- Detecção de abandono de objeto ----
        if self._abandon_manager and _bool(os.getenv("ENABLE_AI_ANALYTICS") or "0"):
            try:
                abandon_events = self._abandon_manager.process(stream_key, detections, now)
                for ab in abandon_events:
                    if not self._cooldown_ok(device_id, channel, f"abandon:{ab['cls_name']}", now):
                        continue
                    cam_name = _sanitize(cfg.get("name") or stream_key)
                    dur = ab["duration_seconds"]
                    cls_pt = ab["cls_name"].replace("backpack", "mochila").replace(
                        "suitcase", "mala").replace("handbag", "bolsa").replace(
                        "umbrella", "guarda-chuva").replace("bottle", "garrafa")
                    snap = self._snapshot_b64(
                        frame, stream_key,
                        [{"cls_name": ab["cls_name"], "conf": 0.99, "xyxy": ab["xyxy"]}],
                    )
                    self._push_event(
                        token, device_id, channel, "ai_abandoned_object", "warn",
                        f"⚠️ Objeto sem dono: {cls_pt} • Cam: {cam_name} • {dur:.0f}s sem responsável",
                        snapshot_jpg_b64=snap,
                        extra={
                            "ai_class":        ab["cls_name"],
                            "ai_duration_s":   dur,
                            "ai_cx":           ab["cx_norm"],
                            "ai_cy":           ab["cy_norm"],
                            "tags":            tags + ["ai_abandon"],
                            "device_type":     cfg.get("device_type") or "",
                        },
                    )
            except Exception:
                pass

        # ---- Detecção de permanência prolongada (Feature #8) ----
        if self._loitering_detector and _bool(os.getenv("ENABLE_LOITERING") or "0"):
            try:
                loiter_alerts = self._loitering_detector.process(stream_key, detections, now)
                for la in loiter_alerts:
                    cam_name = _sanitize(cfg.get("name") or stream_key)
                    dur_str  = la["duration_str"]
                    prefix   = "🚨" if not la["first_alert"] else "⏱️"
                    desc = (
                        f"{prefix} Permanência suspeita: {dur_str} na área"
                        f" • Cam: {cam_name}"
                    )
                    person_dets = [d for d in detections if d["cls_name"] == "person"]
                    snap = self._snapshot_b64(frame, stream_key, person_dets)
                    self._push_event(
                        token, device_id, channel, "ai_loitering", "warn", desc,
                        snapshot_jpg_b64=snap,
                        extra={
                            "ai_duration_s":  round(la["duration_seconds"], 1),
                            "ai_duration_str": dur_str,
                            "ai_cx":          la["cx"],
                            "ai_cy":          la["cy"],
                            "tags":           tags + ["ai_loitering"],
                            "device_type":    cfg.get("device_type") or "",
                        },
                    )
            except Exception:
                pass

        # ---- Contador direcional de pessoas (Feature #7) ----
        if self._directional_counter and _bool(os.getenv("ENABLE_DIRECTIONAL_COUNTER") or "0"):
            try:
                crossing_events = self._directional_counter.process(stream_key, detections, now)
                for ev in crossing_events:
                    cam_name    = _sanitize(cfg.get("name") or stream_key)
                    enter_total = ev["enter_total"]
                    exit_total  = ev["exit_total"]
                    occupancy   = ev["occupancy"]

                    if ev["type"] == "enter":
                        ev_type = "ai_people_enter"
                        emoji, label = "🚶➡️", "Entrada"
                    else:
                        ev_type = "ai_people_exit"
                        emoji, label = "⬅️🚶", "Saída"

                    desc = (
                        f"{emoji} {label} detectada • Cam: {cam_name}"
                        f" • Entradas: {enter_total} | Saídas: {exit_total}"
                        f" | Ocupação: {occupancy}"
                    )

                    person_dets = [d for d in detections if d["cls_name"] == "person"]
                    snap = self._snapshot_b64(frame, stream_key, person_dets)

                    self._push_event(
                        token, device_id, channel, ev_type, "info", desc,
                        snapshot_jpg_b64=snap,
                        extra={
                            "enter_total":  enter_total,
                            "exit_total":   exit_total,
                            "occupancy":    occupancy,
                            "ai_cx":        ev["cx"],
                            "ai_cy":        ev["cy"],
                            "tags":         tags + ["ai_direction"],
                            "device_type":  cfg.get("device_type") or "",
                        },
                    )
            except Exception:
                pass
