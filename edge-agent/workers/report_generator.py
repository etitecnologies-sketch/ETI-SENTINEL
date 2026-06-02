"""
ETI SENTINEL — Gerador de Relatório Diário (Feature Relatório)
==============================================================
Gera relatório diário de eventos e envia via Telegram às 23h.
Também salva arquivo HTML local para consulta posterior.

Como funciona:
  1. Roda em thread separada monitorando a hora atual.
  2. Às REPORT_SEND_HOUR (padrão 23h), coleta eventos do último dia
     via /api/events do edge agent local.
  3. Calcula: total de eventos, top câmeras, distribuição por hora,
     severidades, score de risco.
  4. Envia resumo formatado no Telegram e salva HTML em .reports/.

Variáveis de ambiente:
  ENABLE_DAILY_REPORT       1 para ativar (padrão: 0)
  REPORT_SEND_HOUR          Hora do envio, 0-23 (padrão: 23)
  REPORT_MAX_AGE_DAYS       Dias para manter relatórios HTML (padrão: 30)
  EDGE_PUSH_URL             URL local do edge agent (padrão: http://127.0.0.1:8808)
"""

import json
import logging
import os
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key) or default)
    except Exception:
        return default


def _sanitize(s: Any) -> str:
    return str(s or "").strip()


class ReportGenerator:
    """
    Gera e envia relatório diário de eventos de segurança.

    Uso típico (inicializar junto com o agente):
        reporter = ReportGenerator(env, telegram_cfg_fn, push_url)
        reporter.start()     # Inicia a thread de agendamento
        reporter.stop()      # Para a thread ao encerrar o agente
    """

    def __init__(
        self,
        env: Dict[str, str],
        get_telegram_cfg,   # callable que retorna {"token": ..., "chat_id": ...}
        get_recent_events,  # callable(limit) -> List[Dict]  (já existe no PushRelay)
        get_risk_snapshot,  # callable() -> Dict
    ) -> None:
        self._env             = env
        self._get_telegram    = get_telegram_cfg
        self._get_events      = get_recent_events
        self._get_risk        = get_risk_snapshot
        self._stop_flag       = False
        self._last_report_day = -1
        self._reports_dir     = (
            Path(__file__).resolve().parent.parent / ".reports"
        )

    def start(self) -> None:
        t = threading.Thread(target=self._scheduler_loop, daemon=True, name="ReportScheduler")
        t.start()
        logger.info("[REPORT] Agendador de relatório diário iniciado.")

    def stop(self) -> None:
        self._stop_flag = True

    # ---- Loop de agendamento ----

    def _scheduler_loop(self) -> None:
        while not self._stop_flag:
            try:
                if os.getenv("ENABLE_DAILY_REPORT", "0").strip() not in {"1", "true", "yes"}:
                    time.sleep(60)
                    continue

                send_hour = _env_int("REPORT_SEND_HOUR", 23)
                now       = time.localtime()

                if now.tm_hour == send_hour and now.tm_yday != self._last_report_day:
                    self._last_report_day = now.tm_yday
                    logger.info("[REPORT] Gerando relatório diário...")
                    try:
                        self._generate_and_send()
                    except Exception as exc:
                        logger.error(f"[REPORT] Erro ao gerar relatório: {exc}")
            except Exception:
                pass
            time.sleep(60)  # Verifica uma vez por minuto

    # ---- Geração do relatório ----

    def _generate_and_send(self) -> None:
        events  = self._get_events(500)      # Últimos 500 eventos do dia
        risk    = self._get_risk()
        tg_cfg  = self._get_telegram()

        if not events:
            logger.info("[REPORT] Nenhum evento para reportar hoje.")
            return

        # Filtra apenas eventos das últimas 24h
        cutoff  = time.time() - 86400
        today   = [e for e in events if float(e.get("ts") or e.get("timestamp") or 0) >= cutoff]

        stats   = self._compute_stats(today)
        msg     = self._format_telegram(stats, risk)
        html    = self._format_html(stats, risk)

        # Envia Telegram
        tok  = tg_cfg.get("telegram_token") or ""
        chat = tg_cfg.get("telegram_chat_id") or ""
        if tok and chat:
            self._send_telegram(msg, tok, chat)

        # Salva HTML local
        self._save_html(html)
        self._cleanup_old_reports()

    def _compute_stats(self, events: List[Dict]) -> Dict[str, Any]:
        total        = len(events)
        by_camera    = Counter()
        by_type      = Counter()
        by_hour      = Counter()
        by_severity  = Counter()
        ai_events    = 0

        for ev in events:
            et    = _sanitize(ev.get("event_type") or "")
            cam   = _sanitize(ev.get("device_id") or "?")
            sev   = _sanitize(ev.get("severity") or "info")
            ts    = float(ev.get("ts") or ev.get("timestamp") or 0)

            by_type[et] += 1
            by_camera[cam] += 1
            by_severity[sev] += 1
            if ts:
                hour = time.localtime(ts).tm_hour
                by_hour[hour] += 1
            if et.startswith("ai_"):
                ai_events += 1

        top_cameras = by_camera.most_common(5)
        top_types   = by_type.most_common(8)
        peak_hour   = by_hour.most_common(1)[0] if by_hour else (0, 0)

        return {
            "total":       total,
            "ai_events":   ai_events,
            "top_cameras": top_cameras,
            "top_types":   top_types,
            "peak_hour":   peak_hour,
            "by_severity": dict(by_severity),
            "by_hour":     dict(by_hour),
            "date_str":    time.strftime("%d/%m/%Y"),
        }

    def _format_telegram(self, stats: Dict, risk: Dict) -> str:
        date     = stats["date_str"]
        total    = stats["total"]
        ai       = stats["ai_events"]
        peak_h   = stats["peak_hour"]
        crits    = stats["by_severity"].get("critical", 0)
        warns    = stats["by_severity"].get("warn", 0)
        risk_lbl = _sanitize(risk.get("label") or "BAIXO")
        risk_sc  = int(risk.get("score") or 0)

        lines = [
            f"📊 *RELATÓRIO DIÁRIO ETI SENTINEL*",
            f"📅 {date}",
            f"",
            f"🔢 *Total de eventos:* {total}",
            f"🤖 Detecções de IA: {ai}",
            f"🚨 Críticos: {crits}  ⚠️ Alertas: {warns}",
            f"⏰ Pico de atividade: {peak_h[0]}h ({peak_h[1]} eventos)",
            f"🛡 Score de risco final: {risk_sc} ({risk_lbl})",
            f"",
        ]

        if stats["top_cameras"]:
            lines.append("📷 *Top câmeras por alertas:*")
            for cam, cnt in stats["top_cameras"]:
                lines.append(f"  • Dispositivo {cam}: {cnt} evento(s)")
            lines.append("")

        if stats["top_types"]:
            lines.append("📋 *Tipos mais frequentes:*")
            for etype, cnt in stats["top_types"][:5]:
                lines.append(f"  • `{etype}`: {cnt}x")
            lines.append("")

        lines.append("_Relatório gerado automaticamente pelo ETI SENTINEL_")
        return "\n".join(lines)

    def _format_html(self, stats: Dict, risk: Dict) -> str:
        date    = stats["date_str"]
        total   = stats["total"]
        ai      = stats["ai_events"]
        risk_sc = int(risk.get("score") or 0)
        risk_lbl = _sanitize(risk.get("label") or "BAIXO")
        risk_col = _sanitize(risk.get("color") or "#00c9a7")
        crits   = stats["by_severity"].get("critical", 0)
        warns   = stats["by_severity"].get("warn", 0)
        peak_h  = stats["peak_hour"]

        cam_rows = "".join(
            f"<tr><td>Dispositivo {cam}</td><td>{cnt}</td></tr>"
            for cam, cnt in stats["top_cameras"]
        )
        type_rows = "".join(
            f"<tr><td><code>{etype}</code></td><td>{cnt}</td></tr>"
            for etype, cnt in stats["top_types"]
        )
        hour_bars = ""
        if stats["by_hour"]:
            max_h = max(stats["by_hour"].values()) or 1
            for h in range(24):
                cnt = stats["by_hour"].get(h, 0)
                pct = int(cnt / max_h * 100)
                hour_bars += (
                    f'<div class="bar-row">'
                    f'<span class="bar-label">{h:02d}h</span>'
                    f'<div class="bar-wrap"><div class="bar-fill" style="width:{pct}%"></div></div>'
                    f'<span class="bar-cnt">{cnt}</span>'
                    f'</div>'
                )

        return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>ETI SENTINEL — Relatório {date}</title>
<style>
  body{{font-family:'Segoe UI',sans-serif;background:#060e1c;color:#e2eaf5;margin:0;padding:24px}}
  h1{{color:#3b9eff;font-size:22px;margin-bottom:4px}}
  .sub{{color:#475569;font-size:13px;margin-bottom:24px}}
  .cards{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:24px}}
  .card{{background:#0b1525;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:16px 22px;min-width:140px}}
  .card-label{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}}
  .card-val{{font-size:26px;font-weight:800}}
  .ok{{color:#00c9a7}}.warn{{color:#f59e0b}}.err{{color:#ef4444}}.blue{{color:#3b9eff}}
  table{{width:100%;border-collapse:collapse;margin-bottom:24px;background:#0b1525;border-radius:12px;overflow:hidden}}
  th{{background:#0d1f35;color:#94a3b8;font-size:12px;text-transform:uppercase;padding:10px 14px;text-align:left}}
  td{{padding:9px 14px;border-bottom:1px solid rgba(255,255,255,.04);font-size:13px}}
  code{{background:#1e293b;padding:2px 6px;border-radius:4px;font-size:12px;color:#60a5fa}}
  h2{{color:#94a3b8;font-size:14px;text-transform:uppercase;letter-spacing:.6px;margin:24px 0 10px}}
  .bar-row{{display:flex;align-items:center;gap:8px;margin-bottom:5px}}
  .bar-label{{width:32px;font-size:11px;color:#475569;text-align:right}}
  .bar-wrap{{flex:1;background:#0d1f35;border-radius:4px;height:14px;overflow:hidden}}
  .bar-fill{{height:100%;background:#3b9eff;border-radius:4px;transition:.3s}}
  .bar-cnt{{font-size:11px;color:#64748b;width:32px}}
  footer{{color:#334155;font-size:12px;margin-top:32px;text-align:center}}
</style>
</head>
<body>
<h1>📊 ETI SENTINEL — Relatório Diário</h1>
<div class="sub">Data: {date} · Gerado automaticamente às {time.strftime("%H:%M:%S")}</div>

<div class="cards">
  <div class="card"><div class="card-label">Total de Eventos</div><div class="card-val blue">{total}</div></div>
  <div class="card"><div class="card-label">Detecções IA</div><div class="card-val blue">{ai}</div></div>
  <div class="card"><div class="card-label">Críticos</div><div class="card-val err">{crits}</div></div>
  <div class="card"><div class="card-label">Alertas</div><div class="card-val warn">{warns}</div></div>
  <div class="card"><div class="card-label">Pico</div><div class="card-val ok">{peak_h[0]}h</div></div>
  <div class="card"><div class="card-label">Score de Risco</div>
    <div class="card-val" style="color:{risk_col}">{risk_sc}</div>
    <div style="font-size:11px;font-weight:700;color:{risk_col}">{risk_lbl}</div>
  </div>
</div>

<h2>📷 Top Câmeras</h2>
<table><thead><tr><th>Dispositivo</th><th>Eventos</th></tr></thead>
<tbody>{cam_rows or "<tr><td colspan=2 style='color:#334155'>Sem dados</td></tr>"}</tbody></table>

<h2>📋 Tipos mais frequentes</h2>
<table><thead><tr><th>Tipo de evento</th><th>Ocorrências</th></tr></thead>
<tbody>{type_rows or "<tr><td colspan=2 style='color:#334155'>Sem dados</td></tr>"}</tbody></table>

<h2>⏰ Atividade por hora</h2>
{hour_bars or "<p style='color:#334155'>Sem dados horários.</p>"}

<footer>ETI SENTINEL · Monitoramento Inteligente 24/7</footer>
</body></html>"""

    def _send_telegram(self, msg: str, token: str, chat_id: str) -> None:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={
                "chat_id":    chat_id,
                "text":       msg,
                "parse_mode": "Markdown",
            }, timeout=(5, 15))
            logger.info("[REPORT] Relatório enviado via Telegram.")
        except Exception as exc:
            logger.error(f"[REPORT] Falha ao enviar Telegram: {exc}")

    def _save_html(self, html: str) -> None:
        try:
            self._reports_dir.mkdir(parents=True, exist_ok=True)
            fname = time.strftime("report_%Y%m%d.html")
            (self._reports_dir / fname).write_text(html, encoding="utf-8")
            logger.info(f"[REPORT] HTML salvo: {fname}")
        except Exception as exc:
            logger.error(f"[REPORT] Erro ao salvar HTML: {exc}")

    def _cleanup_old_reports(self) -> None:
        try:
            max_days = _env_int("REPORT_MAX_AGE_DAYS", 30)
            cutoff   = time.time() - max_days * 86400
            for p in self._reports_dir.glob("report_*.html"):
                if p.stat().st_mtime < cutoff:
                    p.unlink()
        except Exception:
            pass
