"""
ETI SENTINEL — Mapa de Calor de Movimentacao (Feature #9)
==========================================================
Acumula posicoes de pessoas detectadas e gera periodicamente uma imagem
colorida mostrando onde ha mais movimentacao na area monitorada.

Como funciona:
  1. Cada pessoa detectada incrementa uma celula de um grid invisivel.
  2. Celulas com mais deteccoes ficam "quentes" (vermelho/laranja).
  3. A cada AI_HEATMAP_INTERVAL_MINUTES, gera a imagem do mapa de calor.
  4. Envia como evento ai_heatmap com a imagem em base64.
  5. Aplica decaimento temporal para que dados antigos percam peso.

Variaveis de ambiente:
  ENABLE_HEATMAP                1 para ativar (padrao: 0)
  AI_HEATMAP_INTERVAL_MINUTES   Intervalo entre geracao de mapas (padrao: 60)
  AI_HEATMAP_GRID_SIZE          Resolucao do grid interno (padrao: 64)
  AI_HEATMAP_BLUR_RADIUS        Raio do blur gaussiano em celulas (padrao: 3)
  AI_HEATMAP_DECAY_FACTOR       Fator de decaimento por intervalo 0.0-1.0 (padrao: 0.85)
  AI_HEATMAP_MIN_DETECTIONS     Minimo de deteccoes para gerar o mapa (padrao: 10)
  AI_HEATMAP_OUTPUT_PATH        Salva o PNG em disco alem de enviar (opcional)
  AI_HEATMAP_OVERLAY_ALPHA      Transparencia do heatmap sobre frame 0.0-1.0 (padrao: 0.6)
"""

import base64
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


class HeatmapGenerator:
    """
    Gera mapas de calor de movimentacao por camera.

    Uso tipico:
        heatmap = HeatmapGenerator()

        # A cada frame com deteccoes:
        heatmap.record(stream_key, detections)

        # Verificar se e hora de gerar o mapa:
        result = heatmap.maybe_generate(stream_key, last_frame, now)
        if result:
            # result["image_b64"] contem o JPEG em base64
            # result["total_detections"] contem o total acumulado
    """

    def __init__(self) -> None:
        # Grid de acumulacao: stream_key -> ndarray float32 (H, W)
        self._grids: Dict[str, np.ndarray] = {}
        # Contagem total de deteccoes por stream (para o relatorio)
        self._totals: Dict[str, int] = {}
        # Timestamp da ultima geracao de mapa por stream
        self._last_gen: Dict[str, float] = {}
        # Ultimo frame recebido por stream (para overlay)
        self._last_frame: Dict[str, Optional[np.ndarray]] = {}

        logger.info("[HEATMAP] Gerador de mapa de calor inicializado.")

    def _get_grid(self, stream_key: str) -> np.ndarray:
        if stream_key not in self._grids:
            g = _env_int("AI_HEATMAP_GRID_SIZE", 64)
            self._grids[stream_key] = np.zeros((g, g), dtype=np.float32)
            self._totals[stream_key] = 0
            self._last_gen[stream_key] = time.time()
            self._last_frame[stream_key] = None
        return self._grids[stream_key]

    def record(
        self,
        stream_key: str,
        detections: List[Dict],
        frame: Optional[np.ndarray] = None,
    ) -> None:
        """
        Registra posicoes de pessoas no grid e atualiza o frame de referencia.
        Deve ser chamado a cada frame processado.
        """
        grid = self._get_grid(stream_key)
        g = grid.shape[0]

        if frame is not None:
            self._last_frame[stream_key] = frame

        person_dets = [d for d in detections if d["cls_name"] == "person"]
        for det in person_dets:
            cx = det["cx_norm"]
            cy = det["cy_norm"]
            col = min(int(cx * g), g - 1)
            row = min(int(cy * g), g - 1)
            grid[row, col] += 1.0
            self._totals[stream_key] = self._totals.get(stream_key, 0) + 1

    def maybe_generate(
        self,
        stream_key: str,
        now: float,
    ) -> Optional[Dict]:
        """
        Gera o mapa de calor se o intervalo configurado passou.

        Retorna dict com:
          {
            "image_b64":         str,   # JPEG em base64
            "total_detections":  int,   # total acumulado desde o reset
            "grid_max":          float, # valor maximo no grid (pico de calor)
            "stream_key":        str,
          }
        ou None se ainda nao e hora ou nao ha dados suficientes.
        """
        import cv2

        interval_s   = _env_float("AI_HEATMAP_INTERVAL_MINUTES", 60.0) * 60.0
        min_dets     = _env_int("AI_HEATMAP_MIN_DETECTIONS", 10)
        decay        = _env_float("AI_HEATMAP_DECAY_FACTOR",  0.85)
        blur_r       = _env_int("AI_HEATMAP_BLUR_RADIUS", 3)
        overlay_a    = _env_float("AI_HEATMAP_OVERLAY_ALPHA", 0.6)

        grid  = self._get_grid(stream_key)
        total = self._totals.get(stream_key, 0)
        last  = self._last_gen.get(stream_key, 0.0)

        if (now - last) < interval_s:
            return None
        if total < min_dets:
            # Intervalo passou mas sem dados suficientes — reseta o timer
            self._last_gen[stream_key] = now
            return None

        # Gera a imagem
        result = self._render(stream_key, grid, total, blur_r, overlay_a, cv2)

        # Aplica decaimento e reseta contagem (mas mantém historico suavizado)
        self._grids[stream_key] = grid * decay
        self._totals[stream_key] = 0
        self._last_gen[stream_key] = now

        return result

    def _render(
        self,
        stream_key: str,
        grid: np.ndarray,
        total: int,
        blur_r: int,
        overlay_alpha: float,
        cv2,
    ) -> Optional[Dict]:
        """Converte o grid numerico em imagem colorida JPEG."""
        try:
            g = grid.shape[0]

            # Suaviza com blur gaussiano para visual mais fluido
            kernel = max(3, blur_r * 2 + 1)
            if kernel % 2 == 0:
                kernel += 1
            blurred = cv2.GaussianBlur(grid, (kernel, kernel), 0)

            # Normaliza para 0-255
            max_val = float(blurred.max())
            if max_val < 1e-6:
                return None
            normalized = (blurred / max_val * 255).astype(np.uint8)

            # Aplica colormap JET: azul (frio) → verde → amarelo → vermelho (quente)
            colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)

            # Redimensiona para 640x640 para melhor visualizacao
            output_size = 640
            heatmap_img = cv2.resize(colored, (output_size, output_size),
                                     interpolation=cv2.INTER_CUBIC)

            # Overlay sobre o ultimo frame capturado (se disponivel)
            ref_frame = self._last_frame.get(stream_key)
            if ref_frame is not None and ref_frame.size > 0:
                try:
                    ref = cv2.resize(ref_frame, (output_size, output_size),
                                     interpolation=cv2.INTER_AREA)
                    # Mistura frame original (fundo) com heatmap (sobreposicao)
                    heatmap_img = cv2.addWeighted(
                        ref,         1.0 - overlay_alpha,
                        heatmap_img, overlay_alpha,
                        0,
                    )
                except Exception:
                    pass

            # Adiciona legenda no rodape
            self._draw_legend(heatmap_img, total, cv2)

            # Salva em disco se configurado
            output_path = (os.getenv("AI_HEATMAP_OUTPUT_PATH") or "").strip()
            if output_path:
                try:
                    path = Path(output_path) / f"heatmap_{stream_key}_{int(time.time())}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(path), heatmap_img)
                except Exception:
                    pass

            # Codifica como JPEG base64
            ok, buf = cv2.imencode(".jpg", heatmap_img, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                return None

            image_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            logger.info(
                f"[HEATMAP] {stream_key} mapa gerado — "
                f"{total} deteccoes | pico={max_val:.0f}"
            )
            return {
                "image_b64":        image_b64,
                "total_detections": total,
                "grid_max":         round(max_val, 1),
                "stream_key":       stream_key,
            }

        except Exception as exc:
            logger.warning(f"[HEATMAP] Falha ao gerar mapa: {exc}")
            return None

    @staticmethod
    def _draw_legend(img: np.ndarray, total: int, cv2) -> None:
        """Desenha barra de legenda e texto no rodape da imagem."""
        h, w = img.shape[:2]
        bar_h = 28

        # Fundo escuro no rodape
        cv2.rectangle(img, (0, h - bar_h), (w, h), (20, 20, 20), -1)

        # Barra de gradiente azul→vermelho
        bar_w = w // 3
        bar_x = w // 2 - bar_w // 2
        for i in range(bar_w):
            val = int(i / bar_w * 255)
            color_strip = np.zeros((1, 1, 3), dtype=np.uint8)
            color_strip[0, 0, :] = [val, val, val]
            colored = cv2.applyColorMap(color_strip, cv2.COLORMAP_JET)[0, 0].tolist()
            cv2.line(img,
                     (bar_x + i, h - bar_h + 4),
                     (bar_x + i, h - 6),
                     tuple(colored), 1)

        # Rotulos
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img, "Frio", (bar_x - 32, h - 8),
                    font, 0.38, (180, 180, 180), 1)
        cv2.putText(img, "Quente", (bar_x + bar_w + 4, h - 8),
                    font, 0.38, (180, 180, 180), 1)
        cv2.putText(img, f"Total: {total} deteccoes",
                    (8, h - 8), font, 0.40, (220, 220, 220), 1)
