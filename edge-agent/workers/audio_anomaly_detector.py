"""
ETI SENTINEL - Detecção de Anomalias de Áudio
Captura áudio dos streams RTSP via FFmpeg e classifica sons anômalos offline.
Sem modelo adicional — análise espectral pura com numpy.

Eventos detectados:
  audio_glass_break  — vidro quebrando (alta frequência, impulsivo)
  audio_scream       — grito / voz em alerta (frequência vocal, sustentado)
  audio_alarm        — alarme / sirene (médio, sustentado, modulado)
  audio_loud_bang    — barulho forte e curto (tiro, batida forte)
  audio_anomaly      — anomalia genérica

Configuração via .env:
  ENABLE_AUDIO_ANOMALY=1
  AUDIO_SAMPLE_RATE=16000
  AUDIO_CHUNK_SECONDS=1.0
  AUDIO_SPIKE_FACTOR=4.0         vezes acima do baseline para considerar anômalo
  AUDIO_BASELINE_ALPHA=0.05      velocidade de adaptação ao ambiente (0-1)
  AUDIO_EVENT_COOLDOWN_SECONDS=45
  AUDIO_MAX_STREAMS=4            limite de streams com análise de áudio simultânea
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


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


def _sanitize(s: Any) -> str:
    return str(s or "").strip()


def _find_ffmpeg() -> str:
    path = os.environ.get("INTERNAL_FFMPEG_PATH") or ""
    if path and os.path.isfile(path):
        return path
    candidates = [
        os.path.join(os.environ.get("PROGRAMDATA", ""), "ETI-SENTINEL", "bin", "ffmpeg.exe"),
        os.path.join(os.path.dirname(__file__), "..", "..", "bin", "ffmpeg.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"


# ---------------------------------------------------------------------------
# Analisador espectral com baseline adaptativo
# ---------------------------------------------------------------------------

class AudioAnalyzer:
    """
    Analisa chunks de áudio PCM mono 16-bit usando FFT.
    Baseline adaptativo: aprende o nível ambiente e alerta apenas desvios.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        baseline_alpha: float = 0.05,
        spike_factor: float = 4.0,
    ) -> None:
        self._sr = sample_rate
        self._alpha = baseline_alpha
        self._spike = spike_factor
        self._baseline_rms: Optional[float] = None
        self._recent_rms: List[float] = []   # janela deslizante dos últimos 10s
        self._alarm_hits: int = 0             # contador para confirmar alarme sustentado

    def analyze(self, samples: "np.ndarray") -> List[Tuple[str, str, str]]:
        """
        Retorna lista de (event_type, severity, description) detectados no chunk.
        Retorna lista vazia se nada anômalo.
        """
        try:
            import numpy as np
        except ImportError:
            return []

        if len(samples) == 0:
            return []

        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))

        # Silêncio absoluto
        if rms < 10.0:
            self._update_baseline(rms)
            return []

        if self._baseline_rms is None:
            self._baseline_rms = rms
            return []

        self._recent_rms.append(rms)
        if len(self._recent_rms) > 10:
            self._recent_rms = self._recent_rms[-10:]

        events: List[Tuple[str, str, str]] = []
        if rms >= self._baseline_rms * self._spike:
            events = self._classify(samples, rms)

        self._update_baseline(rms)
        return events

    def _update_baseline(self, rms: float) -> None:
        if self._baseline_rms is None:
            self._baseline_rms = rms
            return
        # Reduz alpha durante anomalias para não contaminar o baseline
        alpha = self._alpha if rms < self._baseline_rms * 2.0 else self._alpha * 0.1
        self._baseline_rms = self._baseline_rms * (1.0 - alpha) + rms * alpha

    def _classify(self, samples: "np.ndarray", rms: float) -> List[Tuple[str, str, str]]:
        try:
            import numpy as np
        except ImportError:
            return [("audio_anomaly", "warn", "Anomalia de áudio detectada")]

        n = min(len(samples), 4096)
        fft_vals = np.abs(np.fft.rfft(samples[:n].astype(np.float32), n=n))
        freqs = np.fft.rfftfreq(n, 1.0 / self._sr)

        def _band(lo: float, hi: float) -> float:
            mask = (freqs >= lo) & (freqs < hi)
            return float(np.mean(fft_vals[mask])) if mask.any() else 0.0

        mid_e  = _band(300, 3000)
        high_e = _band(3000, 8000)
        total  = _band(20, 8000) + 1e-6

        mid_ratio  = mid_e / total
        high_ratio = high_e / total

        # Zero-crossing rate
        zcr = float(np.mean(np.abs(np.diff(np.sign(samples))))) / 2.0

        # Fator de crista (pico / RMS) — alto = impulsivo
        peak = float(np.max(np.abs(samples.astype(np.float32))))
        crest = peak / (rms + 1e-6)

        # Fração do chunk com energia elevada
        above_frac = float(np.mean(np.abs(samples.astype(np.float32)) > (rms * 0.5)))

        # ---- Regras de classificação ----

        # Vidro quebrando: alta freq, ZCR alto, impulsivo
        if high_ratio > 0.32 and zcr > 0.22 and crest > 4.5:
            return [("audio_glass_break", "critical", "Possível quebra de vidro detectada")]

        # Grito / voz em alerta: frequência vocal dominante, sustentado, tonal
        if mid_ratio > 0.55 and zcr < 0.20 and above_frac > 0.35:
            return [("audio_scream", "critical", "Possível grito ou alarme vocal detectado")]

        # Alarme / sirene: médio dominante, sustentado
        if mid_ratio > 0.45 and above_frac > 0.55:
            self._alarm_hits += 1
            if self._alarm_hits >= 2:   # confirma em 2 chunks seguidos (~2s)
                self._alarm_hits = 0
                return [("audio_alarm", "warn", "Possível alarme ou sirene detectado")]
            return []
        else:
            self._alarm_hits = 0

        # Barulho forte e curto (tiro, batida forte)
        if crest > 7.0 and above_frac < 0.15:
            return [("audio_loud_bang", "warn", "Barulho forte e impulsivo detectado")]

        # Genérico
        return [("audio_anomaly", "warn", "Anomalia de áudio detectada")]


# ---------------------------------------------------------------------------
# Captura por stream (thread individual)
# ---------------------------------------------------------------------------

class _StreamAudioCapture:
    """Captura e analisa áudio de um único stream RTSP via FFmpeg."""

    MAX_FAIL_STREAK = 3   # falhas seguidas → backoff longo

    def __init__(
        self,
        stream_key: str,
        cfg: Dict[str, Any],
        on_event: Any,   # callback(ev_type, severity, desc, device_id, channel, token, cam_name)
        sample_rate: int,
        chunk_seconds: float,
        baseline_alpha: float,
        spike_factor: float,
    ) -> None:
        self._key = stream_key
        self._cfg = cfg
        self._on_event = on_event
        self._sample_rate = sample_rate
        self._chunk_bytes = int(sample_rate * chunk_seconds) * 2  # 16-bit
        self._analyzer = AudioAnalyzer(sample_rate, baseline_alpha, spike_factor)
        self._running = True
        self._fail_streak = 0

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        source_tmpl = os.getenv("AI_SOURCE_URL_TEMPLATE") or "rtsp://127.0.0.1:8554/{stream_key}"
        rtsp_url = source_tmpl.replace("{stream_key}", self._key)
        ffmpeg = _find_ffmpeg()
        device_id = int(self._cfg.get("device_id") or 0)
        channel   = int(self._cfg.get("channel") or 0)
        token     = _sanitize(self._cfg.get("token") or "x")
        cam_name  = _sanitize(self._cfg.get("name") or self._key)

        while self._running:
            proc = None
            try:
                cmd = [
                    ffmpeg,
                    "-rtsp_transport", "tcp",
                    "-i", rtsp_url,
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", str(self._sample_rate),
                    "-ac", "1",
                    "-f", "s16le",
                    "-loglevel", "quiet",
                    "pipe:1",
                ]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
                consecutive_empty = 0
                while self._running:
                    data = proc.stdout.read(self._chunk_bytes)
                    if not data:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            break
                        continue
                    consecutive_empty = 0
                    if len(data) < self._chunk_bytes:
                        continue

                    try:
                        import numpy as np
                        samples = np.frombuffer(data, dtype=np.int16)
                        events = self._analyzer.analyze(samples)
                        for ev_type, severity, description in events:
                            self._on_event(ev_type, severity, description, device_id, channel, token, cam_name)
                    except ImportError:
                        pass

                self._fail_streak += 1

            except Exception as e:
                self._fail_streak += 1
                logger.debug(f"[Audio] {self._key}: {e}")
            finally:
                if proc:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except Exception:
                        pass

            if not self._running:
                break

            # Backoff progressivo após falhas consecutivas
            wait = min(30.0, 5.0 * self._fail_streak)
            time.sleep(wait)
            if self._fail_streak >= self.MAX_FAIL_STREAK:
                logger.debug(f"[Audio] {self._key}: sem áudio disponível, parando captura.")
                break

        logger.debug(f"[Audio] Captura encerrada: {self._key}")


# ---------------------------------------------------------------------------
# Worker principal
# ---------------------------------------------------------------------------

class AudioAnomalyWorker:
    """
    Gerencia a captura de áudio por stream e dispara eventos de anomalia.
    Interface compatível com ONNXAIWorker para integração no edge_agent.py.
    """

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.running = True
        self._captures: Dict[str, _StreamAudioCapture] = {}
        self._threads:  Dict[str, threading.Thread] = {}
        self._sess = requests.Session()
        self._cooldowns: Dict[Tuple[int, int, str], float] = {}
        self._lock = threading.Lock()

    def stop(self) -> None:
        self.running = False
        for cap in self._captures.values():
            cap.stop()

    def run(self) -> None:
        if not _bool(os.getenv("ENABLE_AUDIO_ANOMALY") or "0"):
            logger.info("[Audio] ENABLE_AUDIO_ANOMALY=0, worker desativado.")
            return

        logger.info("[Audio] Worker de anomalia de áudio iniciado.")

        sample_rate    = _env_int("AUDIO_SAMPLE_RATE", 16000)
        chunk_seconds  = _env_float("AUDIO_CHUNK_SECONDS", 1.0)
        baseline_alpha = _env_float("AUDIO_BASELINE_ALPHA", 0.05)
        spike_factor   = _env_float("AUDIO_SPIKE_FACTOR", 4.0)
        max_streams    = _env_int("AUDIO_MAX_STREAMS", 4)

        while self.running:
            try:
                active_cfgs: Dict[str, Any] = self.manager.get_configs() or {}
                active_keys = set(list(active_cfgs.keys())[:max_streams])

                # Inicia captura para streams novos
                for key in active_keys - set(self._captures.keys()):
                    cfg = active_cfgs[key]
                    cap = _StreamAudioCapture(
                        stream_key=key, cfg=cfg,
                        on_event=self._on_event,
                        sample_rate=sample_rate,
                        chunk_seconds=chunk_seconds,
                        baseline_alpha=baseline_alpha,
                        spike_factor=spike_factor,
                    )
                    t = threading.Thread(
                        target=cap.run,
                        daemon=True,
                        name=f"audio-{key}",
                    )
                    self._captures[key] = cap
                    self._threads[key] = t
                    t.start()
                    logger.info(f"[Audio] Captura iniciada: {key}")

                # Remove streams inativos ou threads mortas
                for key in list(self._captures.keys()):
                    t = self._threads.get(key)
                    if key not in active_keys or (t and not t.is_alive()):
                        self._captures[key].stop()
                        del self._captures[key]
                        self._threads.pop(key, None)

            except Exception as e:
                logger.error(f"[Audio] Erro no loop principal: {e}")

            time.sleep(15)

        logger.info("[Audio] Worker encerrado.")

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_event(
        self,
        ev_type: str,
        severity: str,
        description: str,
        device_id: int,
        channel: int,
        token: str,
        cam_name: str,
    ) -> None:
        cooldown = _env_float("AUDIO_EVENT_COOLDOWN_SECONDS", 45.0)
        key = (device_id, channel, ev_type)
        now = time.time()
        with self._lock:
            if (now - self._cooldowns.get(key, 0.0)) < cooldown:
                return
            self._cooldowns[key] = now

        emoji = {
            "audio_glass_break": "🔴",
            "audio_scream":      "🆘",
            "audio_alarm":       "🚨",
            "audio_loud_bang":   "💥",
        }.get(ev_type, "🔔")

        full_desc = f"{emoji} {description} • Cam: {cam_name}"
        logger.info(f"[Audio] {full_desc}")
        self._push_event(token, device_id, channel, ev_type, severity, full_desc)

    def _push_event(
        self,
        token: str,
        device_id: int,
        channel: int,
        event_type: str,
        severity: str,
        description: str,
    ) -> None:
        url = _sanitize(os.getenv("EDGE_PUSH_URL") or "http://127.0.0.1:8808/api/push")
        payload = {
            "token": token or "x",
            "device_id": int(device_id),
            "channel": int(channel),
            "event_type": event_type,
            "severity": severity,
            "description": description[:400],
        }
        try:
            self._sess.post(
                url, json=payload,
                headers={"x-event-source": "audio-worker"},
                timeout=(3, 8),
            )
        except Exception:
            pass
