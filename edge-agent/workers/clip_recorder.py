"""
ETI SENTINEL — Gravador de Clips de Alerta (Feature Clips)
===========================================================
Mantém um buffer circular de frames por câmera. Quando um alerta dispara,
grava os últimos N segundos como arquivo MP4 e retorna o caminho.

Como funciona:
  1. A cada frame analisado, adiciona ao buffer circular da câmera.
  2. Quando um alerta ocorre, os frames do buffer são gravados em MP4 via
     OpenCV VideoWriter, salvo em RECORD_BASE_DIR/device_X/ch_Y/TIMESTAMP.mp4.
  3. O endpoint /api/recordings/list e /api/recordings/get (já existentes no
     agent_api.py) permitem listar e baixar os clipes pelo dashboard.
  4. Limpeza automática: clipes com mais de CLIP_MAX_AGE_HOURS são removidos.

Variáveis de ambiente:
  ENABLE_CLIP_RECORDING    1 para ativar (padrão: 0)
  CLIP_PRE_EVENT_SECONDS   Segundos antes do alerta gravados (padrão: 12)
  CLIP_FPS                 FPS do clipe (padrão: 6 — leve)
  CLIP_MAX_AGE_HOURS       Horas até deletar clips antigos (padrão: 48)
  CLIP_MAX_PER_CAMERA      Máximo de clips por câmera (padrão: 20)
  RECORD_BASE_DIR          Pasta base para os clipes (padrão: .recordings/)
"""

import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional, Tuple

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


def _base_dir() -> Path:
    raw = os.getenv("RECORD_BASE_DIR") or ""
    if raw.strip():
        return Path(raw.strip())
    # Padrão: pasta .recordings/ ao lado do agente
    return Path(__file__).resolve().parent.parent / ".recordings"


class ClipRecorder:
    """
    Buffer circular de frames por câmera + gravação sob demanda.

    Uso típico:
        recorder = ClipRecorder()
        # A cada frame analisado:
        recorder.push_frame(stream_key, frame, time.time())
        # Quando um alerta dispara:
        path = recorder.save_clip(stream_key, device_id, channel)
        if path:
            print("Clip salvo em:", path)
    """

    def __init__(self) -> None:
        # stream_key -> deque de (timestamp, frame)
        self._buffers: Dict[str, Deque[Tuple[float, Any]]] = {}
        self._last_cleanup = time.time()
        logger.info("[CLIP] Gravador de clips inicializado.")

    def push_frame(self, stream_key: str, frame: Any, now: float) -> None:
        """Adiciona frame ao buffer circular. Descarta frames antigos automaticamente."""
        if not self._is_enabled():
            return
        try:
            pre_s   = _env_float("CLIP_PRE_EVENT_SECONDS", 12.0)
            fps     = max(1, _env_int("CLIP_FPS", 6))
            maxlen  = int(pre_s * fps) + fps  # margem de 1s extra

            if stream_key not in self._buffers:
                self._buffers[stream_key] = deque(maxlen=maxlen)

            self._buffers[stream_key].append((now, frame))
        except Exception as exc:
            logger.debug(f"[CLIP] push_frame erro: {exc}")

    def save_clip(
        self,
        stream_key: str,
        device_id: int,
        channel: int,
        label: str = "alert",
    ) -> Optional[str]:
        """
        Grava os frames do buffer como MP4 e retorna o caminho absoluto.
        Retorna None se não houver frames suficientes ou ocorrer erro.
        """
        if not self._is_enabled():
            return None

        try:
            import cv2
        except ImportError:
            logger.debug("[CLIP] opencv-python não instalado — clips desativados.")
            return None

        buf = self._buffers.get(stream_key)
        if not buf or len(buf) < 3:
            return None

        fps     = max(1, _env_int("CLIP_FPS", 6))
        frames  = [f for _, f in buf]

        if not frames:
            return None

        h, w = frames[0].shape[:2]

        # Monta caminho de destino
        base  = _base_dir()
        ddir  = base / f"device_{int(device_id)}" / f"ch_{int(channel)}"
        ddir.mkdir(parents=True, exist_ok=True)

        ts_str = time.strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in (label or "alert"))
        out_path = ddir / f"{ts_str}_{safe_label}.mp4"

        try:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_path), fourcc, float(fps), (w, h))
            for frm in frames:
                writer.write(frm)
            writer.release()

            if not out_path.exists() or out_path.stat().st_size < 1000:
                out_path.unlink(missing_ok=True)
                return None

            logger.info(
                f"[CLIP] Clip salvo: {out_path.name} "
                f"({len(frames)} frames, {out_path.stat().st_size // 1024} KB)"
            )

            # Limpeza periódica de clips antigos
            if (time.time() - self._last_cleanup) > 3600:
                self._cleanup(base, device_id, channel)
                self._last_cleanup = time.time()

            return str(out_path)

        except Exception as exc:
            logger.error(f"[CLIP] Erro ao salvar clip: {exc}")
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    def _is_enabled(self) -> bool:
        return os.getenv("ENABLE_CLIP_RECORDING", "0").strip() in {"1", "true", "yes"}

    def _cleanup(self, base: Path, device_id: int, channel: int) -> None:
        """Remove clips antigos e excedentes."""
        try:
            max_age_h   = _env_float("CLIP_MAX_AGE_HOURS", 48.0)
            max_per_cam = _env_int("CLIP_MAX_PER_CAMERA", 20)
            cutoff      = time.time() - max_age_h * 3600
            ddir        = base / f"device_{int(device_id)}" / f"ch_{int(channel)}"

            if not ddir.exists():
                return

            clips = sorted(ddir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)

            # Remove por idade
            for clip in clips:
                try:
                    if clip.stat().st_mtime < cutoff:
                        clip.unlink()
                        logger.debug(f"[CLIP] Clip expirado removido: {clip.name}")
                except Exception:
                    pass

            # Remove excedentes (mantém os mais recentes)
            clips = sorted(ddir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
            while len(clips) > max_per_cam:
                try:
                    clips.pop(0).unlink()
                except Exception:
                    break

        except Exception as exc:
            logger.debug(f"[CLIP] Limpeza falhou: {exc}")
