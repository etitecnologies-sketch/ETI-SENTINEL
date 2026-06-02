"""
ETI SENTINEL — OTA Update Worker (Atualização Automática)
=========================================================
Verifica periodicamente se há uma nova versão do agente disponível na nuvem.
Quando detecta atualização: baixa, valida SHA256, grava script de substituição
e reinicia o agente sem intervenção do técnico.

Fluxo:
  1. Chama GET /collector/update-check com a versão atual.
  2. Se a API retornar { up_to_date: true } → nada a fazer.
  3. Se retornar { version, download_url, sha256 } → inicia download.
  4. Valida SHA256 do arquivo baixado.
  5. Salva o novo EXE em <exe_dir>/_new_agent.exe.
  6. Grava <exe_dir>/_updater.bat que:
       • Aguarda 4s para o processo atual encerrar
       • Substitui o EXE atual pelo novo
       • Relança o agente novo
       • Remove a si mesmo
  7. Lança _updater.bat (detached) e chama sys.exit(0).

Variáveis de ambiente:
  ENABLE_OTA               1 para ativar (padrão: 0)
  OTA_CHECK_INTERVAL_MIN   Intervalo entre verificações em minutos (padrão: 60)
  AGENT_VERSION            Versão atual (injetada no build — padrão: "2.1.0")
"""

import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Versão atual do agente — deve ser atualizada a cada build
AGENT_VERSION = os.getenv("AGENT_VERSION") or "2.1.0"


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key) or default)
    except Exception:
        return default


def _exe_path() -> Path:
    """Retorna o caminho do EXE em execução (funciona tanto no EXE quanto em .py)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve().parent.parent / "edge_agent.py"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_updater_bat(exe_path: Path, new_exe_path: Path) -> Path:
    """
    Grava script .bat que substitui o EXE atual pelo novo e relança.
    Usa timeout em vez de ping — mais confiável em ambientes sem rede.
    """
    bat_path = exe_path.parent / "_eti_updater.bat"
    exe_str  = str(exe_path)
    new_str  = str(new_exe_path)
    bat_path.write_text(
        "@echo off\r\n"
        "timeout /t 5 /nobreak >nul\r\n"
        f'copy /y "{new_str}" "{exe_str}"\r\n'
        f'start "" "{exe_str}"\r\n'
        f'del "{new_str}"\r\n'
        'del "%~f0"\r\n',
        encoding="ascii",
    )
    return bat_path


class OTAUpdater:
    """
    Worker de atualização automática (OTA).

    Uso típico:
        updater = OTAUpdater(env)
        updater.start()   # inicia thread de verificação periódica
        updater.stop()    # para ao encerrar o agente
    """

    def __init__(self, env: dict) -> None:
        self._env      = env
        self._stop     = False
        self._sess     = requests.Session()
        self._checked  = False

    def start(self) -> None:
        t = threading.Thread(target=self._loop, daemon=True, name="OTAUpdater")
        t.start()
        logger.info(f"[OTA] Worker iniciado — versão atual: {AGENT_VERSION}")

    def stop(self) -> None:
        self._stop = True

    # ---- Loop de verificação ----

    def _loop(self) -> None:
        # Primeira verificação com delay de 2 min para o agente estabilizar
        time.sleep(120)

        while not self._stop:
            if os.getenv("ENABLE_OTA", "0").strip() in {"1", "true", "yes"}:
                try:
                    self._check_and_update()
                except Exception as exc:
                    logger.error(f"[OTA] Erro na verificação: {exc}")

            interval_min = _env_float("OTA_CHECK_INTERVAL_MIN", 60.0)
            time.sleep(max(10.0, interval_min * 60))

    def _check_and_update(self) -> None:
        ingest_url = (self._env.get("INGEST_API_URL") or "").rstrip("/")
        collector_key = self._env.get("COLLECTOR_KEY") or ""
        client_id  = self._env.get("CLIENT_ID") or ""

        if not ingest_url or not collector_key:
            return

        try:
            r = self._sess.get(
                f"{ingest_url}/collector/update-check",
                headers={"x-collector-key": collector_key},
                params={"version": AGENT_VERSION, "client_id": client_id},
                timeout=(5, 20),
            )
        except Exception as exc:
            logger.debug(f"[OTA] Falha ao contatar servidor: {exc}")
            return

        if r.status_code != 200:
            return

        data = r.json() if r.text else {}
        if not isinstance(data, dict):
            return

        if data.get("up_to_date"):
            if not self._checked:
                logger.info(f"[OTA] Agente atualizado (v{AGENT_VERSION}).")
                self._checked = True
            return

        new_version  = str(data.get("version") or "").strip()
        download_url = str(data.get("download_url") or "").strip()
        expected_sha = str(data.get("sha256") or "").strip().lower()
        required     = bool(data.get("required"))

        if not new_version or not download_url or not expected_sha:
            logger.warning("[OTA] Manifesto incompleto — ignorando.")
            return

        logger.info(
            f"[OTA] Nova versão disponível: v{new_version}"
            f" (atual: v{AGENT_VERSION})"
            f"{'  [OBRIGATÓRIA]' if required else ''}"
        )

        self._apply_update(download_url, expected_sha, new_version)

    def _apply_update(self, url: str, expected_sha: str, version: str) -> None:
        exe_path    = _exe_path()
        tmp_dir     = exe_path.parent
        new_exe     = tmp_dir / "_new_agent.exe"

        # ---- Download ----
        logger.info(f"[OTA] Baixando v{version}...")
        try:
            r = self._sess.get(url, stream=True, timeout=(10, 300))
            r.raise_for_status()
            downloaded = 0
            with open(new_exe, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            logger.info(f"[OTA] Download concluído: {downloaded // 1024} KB")
        except Exception as exc:
            logger.error(f"[OTA] Falha no download: {exc}")
            new_exe.unlink(missing_ok=True)
            return

        # ---- Validação SHA256 ----
        actual_sha = _sha256_file(new_exe)
        if actual_sha != expected_sha:
            logger.error(
                f"[OTA] SHA256 inválido! Esperado={expected_sha[:16]}… "
                f"Obtido={actual_sha[:16]}… Abortando."
            )
            new_exe.unlink(missing_ok=True)
            return

        logger.info(f"[OTA] SHA256 verificado. Preparando atualização para v{version}...")

        # ---- Script de substituição ----
        # Só cria .bat se estiver rodando como EXE compilado
        if not getattr(sys, "frozen", False):
            logger.info("[OTA] Modo desenvolvimento — não substitui EXE.")
            new_exe.unlink(missing_ok=True)
            return

        try:
            bat = _write_updater_bat(exe_path, new_exe)
            logger.info(f"[OTA] Lançando updater: {bat.name}")
            subprocess.Popen(
                ["cmd", "/c", str(bat)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            logger.info("[OTA] Encerrando agente para aplicar atualização...")
            time.sleep(1)
            sys.exit(0)
        except Exception as exc:
            logger.error(f"[OTA] Falha ao lançar updater: {exc}")
            new_exe.unlink(missing_ok=True)
