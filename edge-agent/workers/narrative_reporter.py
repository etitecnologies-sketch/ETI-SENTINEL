"""
ETI SENTINEL - Relatório Narrativo Automático com IA
Usa Claude Haiku para gerar análise contextualizada em português.
Envio assíncrono: não bloqueia o fluxo principal de alertas.

Configuração no .env:
  ANTHROPIC_API_KEY=sk-ant-...
  ENABLE_AI_NARRATIVE=1
"""

import os
import threading
import time
from typing import Any, Callable, Dict, Optional

import requests

_MODEL = "claude-haiku-4-5-20251001"
_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"

# Tipos de eventos que merecem análise — heartbeats e routine ficam de fora
_TRIGGER_EVENTS = {
    "ai_zone_intrusion",
    "ai_line_crossing",
    "ai_crowd_alert",
    "ai_person_detected",
    "ai_abandoned_object",
    "audio_glass_break",
    "audio_scream",
    "audio_alarm",
    "audio_loud_bang",
    "intrusion_detected",
    "motion_detected",
    "alarm_input",
    "videoloss_started",
    "edge_stream_offline",
}

_DEBOUNCE_SECONDS = 90.0  # mínimo entre narrativas do mesmo dispositivo/canal

_PROMPT = """\
Você é um sistema de monitoramento de segurança inteligente. \
Escreva EXATAMENTE 2 frases em português descrevendo o evento abaixo, \
como se fosse um relatório enviado ao operador responsável. \
Inclua horário, nome do dispositivo e uma recomendação de ação objetiva. \
Seja direto, profissional e conciso. Não use markdown, listas ou prefixos.

Dados do evento:
- Tipo: {event_type}
- Dispositivo: {device_name}
- Horário: {ts_fmt}
- Severidade: {severity}
- Descrição: {description}
- Score de Risco Atual: {risk_score}/100 ({risk_label})"""


def _fmt_ts(ts: float) -> str:
    return time.strftime("%H:%M:%S de %d/%m/%Y", time.localtime(ts))


def _bool_env(key: str) -> bool:
    return str(os.getenv(key) or "").strip().lower() in {"1", "true", "yes", "on"}


class NarrativeReporter:
    """
    Gera narrativas assíncronas para eventos relevantes e as envia via callback.
    Thread-safe. Debounce por dispositivo/canal para evitar spam.
    """

    def __init__(self, env: Dict[str, str]) -> None:
        self._env = env
        self._lock = threading.Lock()
        self._last_ts: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def analyze_async(
        self,
        ev: Dict[str, Any],
        device_name: str,
        risk_snapshot: Dict[str, Any],
        send_fn: Callable[[str], None],
    ) -> None:
        """Dispara análise em background. send_fn(texto) é chamado quando pronto."""
        if not self._is_enabled():
            return
        et = str(ev.get("event_type") or "").lower()
        if not any(et == t or t in et for t in _TRIGGER_EVENTS):
            return

        device_key = f"{ev.get('device_id', '?')}:{ev.get('channel', 0)}"
        now = time.time()
        with self._lock:
            if (now - self._last_ts.get(device_key, 0.0)) < _DEBOUNCE_SECONDS:
                return
            self._last_ts[device_key] = now

        threading.Thread(
            target=self._worker,
            args=(ev, device_name, risk_snapshot, send_fn),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_enabled(self) -> bool:
        return bool(self._api_key()) and _bool_env("ENABLE_AI_NARRATIVE")

    def _api_key(self) -> str:
        return str(
            self._env.get("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or ""
        ).strip()

    def _worker(
        self,
        ev: Dict[str, Any],
        device_name: str,
        risk_snapshot: Dict[str, Any],
        send_fn: Callable[[str], None],
    ) -> None:
        try:
            time.sleep(2.5)  # aguarda alerta principal ser entregue
            narrative = self._call_claude(ev, device_name, risk_snapshot)
            if narrative:
                send_fn(f"📝 Análise do Sistema:\n{narrative}")
        except Exception:
            pass

    def _call_claude(
        self,
        ev: Dict[str, Any],
        device_name: str,
        risk_snapshot: Dict[str, Any],
    ) -> Optional[str]:
        key = self._api_key()
        if not key:
            return None

        ts = float(ev.get("ts") or ev.get("timestamp") or time.time())
        prompt = _PROMPT.format(
            event_type=str(ev.get("event_type") or "—"),
            device_name=device_name or "dispositivo não identificado",
            ts_fmt=_fmt_ts(ts),
            severity=str(ev.get("severity") or "info"),
            description=str(ev.get("description") or "—")[:200],
            risk_score=int(risk_snapshot.get("score", 0)),
            risk_label=str(risk_snapshot.get("label", "BAIXO")),
        )

        try:
            resp = requests.post(
                _API_URL,
                headers={
                    "x-api-key": key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": _MODEL,
                    "max_tokens": 220,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                return None
            content = resp.json().get("content") or []
            text = (content[0].get("text") or "") if content else ""
            return text.strip()[:480] or None
        except Exception:
            return None
