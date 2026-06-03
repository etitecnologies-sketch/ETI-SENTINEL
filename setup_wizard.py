"""
ETI SENTINEL — Instalador Visual (Setup Wizard)
Gera ETI_SENTINEL_Setup.exe via build_setup.py
"""
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# Cores e constantes
# ---------------------------------------------------------------------------
BG        = "#0d1117"
BG2       = "#161b22"
BG3       = "#21262d"
BORDER    = "#30363d"
ACCENT    = "#2ea043"
ACCENT_HV = "#3fb950"
TEXT      = "#e6edf3"
TEXT_DIM  = "#7d8590"
ERR       = "#f85149"
OK_COLOR  = "#3fb950"

DESTINO  = Path(r"C:\ProgramData\ETI-SENTINEL")
SVC_NAME = "ETI_SENTINEL_EDGE_AGENT"
INGEST   = "https://eti-sentinel-production.up.railway.app"

# Pasta de origem (onde o wizard está sendo executado)
if getattr(sys, "frozen", False):
    ORIGEM = Path(sys.executable).parent
else:
    ORIGEM = Path(__file__).parent / "ETI_SENTINEL_CLIENT_READY"


# ---------------------------------------------------------------------------
# Verifica / solicita permissão de administrador
# ---------------------------------------------------------------------------
def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> None:
    exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, "", None, 1)


# ---------------------------------------------------------------------------
# Wizard principal
# ---------------------------------------------------------------------------
class Wizard(tk.Tk):

    def __init__(self) -> None:
        super().__init__()
        self.title("ETI SENTINEL — Instalador")
        self.geometry("500x560")
        self.resizable(False, False)
        self.configure(bg=BG)

        # Centraliza na tela
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 500) // 2
        y = (self.winfo_screenheight() - 560) // 2
        self.geometry(f"500x560+{x}+{y}")

        # Ícone (ignora silenciosamente se não existir)
        try:
            ico = ORIGEM / "bin" / "eti_sentinel.ico"
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

        # Variáveis de entrada
        self._client_id = tk.StringVar()
        self._coll_key  = tk.StringVar()
        self._show_key  = tk.BooleanVar(value=False)

        # Estilo TTK (barra de progresso verde)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "ETI.Horizontal.TProgressbar",
            background=ACCENT, troughcolor=BG3,
            borderwidth=0, thickness=18,
        )

        self._build_header()
        self._build_footer()

        # Área de conteúdo (muda a cada página)
        self._area = tk.Frame(self, bg=BG)
        self._area.place(x=0, y=96, width=500, height=400)

        # Páginas
        self._pages = {
            0: self._build_page_welcome(),
            1: self._build_page_config(),
            2: self._build_page_installing(),
            3: self._build_page_done(),
        }

        self._show(0)

    # ── Layout fixo ─────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=BG2, height=96)
        hdr.place(x=0, y=0, width=500, height=96)
        tk.Frame(self, bg=BORDER, height=1).place(x=0, y=95, width=500)

        tk.Label(hdr, text="ETI SENTINEL",
                 font=("Segoe UI", 17, "bold"), bg=BG2, fg=TEXT
                 ).place(x=24, y=18)
        tk.Label(hdr, text="Edge Agent  —  Instalador v2.1",
                 font=("Segoe UI", 10), bg=BG2, fg=TEXT_DIM
                 ).place(x=26, y=54)

        # Linha de progresso de passos
        steps = ["Boas-vindas", "Configurar", "Instalar", "Concluído"]
        self._step_labels: list[tk.Label] = []
        sx = 24
        for s in steps:
            lbl = tk.Label(hdr, text=s, font=("Segoe UI", 8),
                           bg=BG2, fg=TEXT_DIM)
            lbl.place(x=sx, y=74)
            self._step_labels.append(lbl)
            sx += 115

    def _build_footer(self) -> None:
        ft = tk.Frame(self, bg=BG2, height=64)
        ft.place(x=0, y=496, width=500, height=64)
        tk.Frame(self, bg=BORDER, height=1).place(x=0, y=496, width=500)

        self._btn_back = tk.Button(
            ft, text="← Voltar", width=10,
            command=self._back,
            bg=BG3, fg=TEXT_DIM, relief="flat", cursor="hand2",
            activebackground=BORDER, activeforeground=TEXT,
            font=("Segoe UI", 10),
        )
        self._btn_back.place(x=20, y=16)

        self._btn_cancel = tk.Button(
            ft, text="Cancelar", width=10,
            command=self.destroy,
            bg=BG3, fg=TEXT_DIM, relief="flat", cursor="hand2",
            activebackground=BORDER, activeforeground=TEXT,
            font=("Segoe UI", 10),
        )
        self._btn_cancel.place(x=290, y=16)

        self._btn_next = tk.Button(
            ft, text="Próximo  →", width=13,
            command=self._next,
            bg=ACCENT, fg="#ffffff", relief="flat", cursor="hand2",
            activebackground=ACCENT_HV, activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
        )
        self._btn_next.place(x=388, y=16)

    # ── Navegação ────────────────────────────────────────────────────────────

    def _show(self, n: int) -> None:
        for p in self._pages.values():
            p.place_forget()
        self._pages[n].place(x=0, y=0, width=500, height=400)
        self._current = n
        self._update_footer(n)
        self._update_steps(n)

    def _update_footer(self, n: int) -> None:
        # Botão Voltar
        self._btn_back.config(state="normal" if n == 1 else "disabled")

        if n == 0:
            self._btn_next.config(text="Próximo  →", command=self._next,
                                  state="normal", bg=ACCENT)
            self._btn_cancel.config(state="normal")
        elif n == 1:
            self._btn_next.config(text="Instalar  ▶", command=self._validate_and_install,
                                  state="normal", bg=ACCENT)
            self._btn_cancel.config(state="normal")
        elif n == 2:
            self._btn_next.config(state="disabled", bg=BG3)
            self._btn_cancel.config(state="disabled")
        elif n == 3:
            self._btn_next.config(text="Fechar", command=self.destroy,
                                  state="normal", bg=ACCENT)
            self._btn_cancel.config(state="disabled")
            self._btn_back.config(state="disabled")

    def _update_steps(self, n: int) -> None:
        for i, lbl in enumerate(self._step_labels):
            if i < n:
                lbl.config(fg=OK_COLOR)
            elif i == n:
                lbl.config(fg=TEXT, font=("Segoe UI", 8, "bold"))
            else:
                lbl.config(fg=TEXT_DIM, font=("Segoe UI", 8))

    def _next(self) -> None:
        self._show(self._current + 1)

    def _back(self) -> None:
        if self._current > 0:
            self._show(self._current - 1)

    # ── Página 0 — Boas-vindas ───────────────────────────────────────────────

    def _build_page_welcome(self) -> tk.Frame:
        f = tk.Frame(self._area, bg=BG)

        tk.Label(f, text="Bem-vindo", font=("Segoe UI", 20, "bold"),
                 bg=BG, fg=TEXT).place(x=28, y=28)
        tk.Label(f, text="Assistente de instalação do ETI SENTINEL Edge Agent.",
                 font=("Segoe UI", 10), bg=BG, fg=TEXT_DIM).place(x=28, y=68)

        tk.Frame(f, bg=BORDER, height=1).place(x=28, y=100, width=444)

        items = [
            ("Monitoramento de câmeras em tempo real",
             "Suporte a câmeras IP via RTSP / ONVIF"),
            ("Detecção com Inteligência Artificial",
             "Pessoas, veículos, placas, anomalias e muito mais"),
            ("Alertas automáticos",
             "Telegram, WhatsApp e dashboard local"),
            ("10 features de segurança ativas",
             "Queda, loitering, mapa de calor, contagem e mais"),
        ]

        y = 120
        for title, sub in items:
            tk.Label(f, text=f"  ✔  {title}", font=("Segoe UI", 10, "bold"),
                     bg=BG, fg=TEXT, anchor="w").place(x=28, y=y, width=444)
            tk.Label(f, text=f"       {sub}", font=("Segoe UI", 9),
                     bg=BG, fg=TEXT_DIM, anchor="w").place(x=28, y=y + 18, width=444)
            y += 50

        tk.Frame(f, bg=BORDER, height=1).place(x=28, y=340, width=444)
        tk.Label(f, text="Clique em  Próximo  para informar os dados do cliente.",
                 font=("Segoe UI", 9, "italic"),
                 bg=BG, fg=TEXT_DIM).place(x=28, y=356)

        return f

    # ── Página 1 — Configuração ──────────────────────────────────────────────

    def _build_page_config(self) -> tk.Frame:
        f = tk.Frame(self._area, bg=BG)

        tk.Label(f, text="Dados do Cliente", font=("Segoe UI", 16, "bold"),
                 bg=BG, fg=TEXT).place(x=28, y=28)
        tk.Label(f, text="Informe os dados fornecidos pela ETI Tecnologias.",
                 font=("Segoe UI", 10), bg=BG, fg=TEXT_DIM).place(x=28, y=60)

        tk.Frame(f, bg=BORDER, height=1).place(x=28, y=90, width=444)

        # ID do Cliente
        tk.Label(f, text="ID do Cliente  *", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=TEXT).place(x=28, y=112)
        tk.Label(f, text="Número único do estabelecimento  (ex: 5)",
                 font=("Segoe UI", 9), bg=BG, fg=TEXT_DIM).place(x=28, y=132)

        self._entry_id = tk.Entry(
            f, textvariable=self._client_id,
            font=("Segoe UI", 12), bg=BG3, fg=TEXT,
            insertbackground=TEXT, relief="flat",
            highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=BORDER,
        )
        self._entry_id.place(x=28, y=156, width=444, height=38)

        # Chave Coletora
        tk.Label(f, text="Chave Coletora  *", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=TEXT).place(x=28, y=212)
        tk.Label(f, text="Token de autenticação fornecido pela ETI",
                 font=("Segoe UI", 9), bg=BG, fg=TEXT_DIM).place(x=28, y=232)

        self._entry_key = tk.Entry(
            f, textvariable=self._coll_key,
            font=("Segoe UI", 12), bg=BG3, fg=TEXT,
            insertbackground=TEXT, relief="flat", show="*",
            highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=BORDER,
        )
        self._entry_key.place(x=28, y=256, width=444, height=38)

        def toggle_key():
            self._entry_key.config(show="" if self._show_key.get() else "*")

        tk.Checkbutton(
            f, text="Mostrar chave", variable=self._show_key,
            command=toggle_key, bg=BG, fg=TEXT_DIM,
            selectcolor=BG3, activebackground=BG, activeforeground=TEXT,
            font=("Segoe UI", 9), cursor="hand2",
        ).place(x=28, y=304)

        tk.Frame(f, bg=BORDER, height=1).place(x=28, y=335, width=444)

        tk.Label(f, text="Pasta de instalacao:  C:\\ProgramData\\ETI-SENTINEL",
                 font=("Consolas", 9), bg=BG, fg=TEXT_DIM).place(x=28, y=350)

        self._err_lbl = tk.Label(f, text="", font=("Segoe UI", 9),
                                 bg=BG, fg=ERR)
        self._err_lbl.place(x=28, y=374)

        return f

    # ── Página 2 — Instalando ────────────────────────────────────────────────

    def _build_page_installing(self) -> tk.Frame:
        f = tk.Frame(self._area, bg=BG)

        tk.Label(f, text="Instalando...", font=("Segoe UI", 16, "bold"),
                 bg=BG, fg=TEXT).place(x=28, y=28)

        self._prog = ttk.Progressbar(
            f, style="ETI.Horizontal.TProgressbar",
            mode="determinate", maximum=100,
        )
        self._prog.place(x=28, y=72, width=444, height=18)

        self._prog_lbl = tk.Label(f, text="Aguardando...",
                                  font=("Segoe UI", 9), bg=BG, fg=TEXT_DIM)
        self._prog_lbl.place(x=28, y=98)

        # Caixa de log
        log_frame = tk.Frame(f, bg=BG3,
                             highlightthickness=1, highlightbackground=BORDER)
        log_frame.place(x=28, y=124, width=444, height=248)

        self._log_txt = tk.Text(
            log_frame, bg=BG3, fg=TEXT_DIM,
            font=("Consolas", 9), relief="flat",
            state="disabled", wrap="word", padx=10, pady=8,
        )
        self._log_txt.pack(fill="both", expand=True)

        return f

    # ── Página 3 — Concluído ─────────────────────────────────────────────────

    def _build_page_done(self) -> tk.Frame:
        f = tk.Frame(self._area, bg=BG)

        tk.Label(f, text="Instalação Concluída!", font=("Segoe UI", 20, "bold"),
                 bg=BG, fg=OK_COLOR).place(x=0, y=40, width=500)
        tk.Label(f, text="O ETI SENTINEL Edge Agent está ativo.",
                 font=("Segoe UI", 11), bg=BG, fg=TEXT_DIM).place(x=0, y=80, width=500)

        tk.Frame(f, bg=BORDER, height=1).place(x=28, y=120, width=444)

        infos = [
            ("Dashboard local", "http://localhost:8808"),
            ("Configuracao",    "C:\\ProgramData\\ETI-SENTINEL\\.env"),
            ("Logs",            "C:\\ProgramData\\ETI-SENTINEL\\.state\\"),
        ]
        y = 140
        for label, value in infos:
            tk.Label(f, text=label, font=("Segoe UI", 9, "bold"),
                     bg=BG, fg=TEXT_DIM, anchor="w").place(x=44, y=y)
            tk.Label(f, text=value, font=("Consolas", 9),
                     bg=BG, fg=TEXT, anchor="w").place(x=44, y=y + 18)
            y += 52

        tk.Frame(f, bg=BORDER, height=1).place(x=28, y=310, width=444)

        tk.Label(f,
                 text="O agente inicia automaticamente toda vez\nque este computador for ligado.",
                 font=("Segoe UI", 10), bg=BG, fg=TEXT_DIM,
                 justify="center").place(x=0, y=326, width=500)

        return f

    # ── Instalação ───────────────────────────────────────────────────────────

    def _validate_and_install(self) -> None:
        cid  = self._client_id.get().strip()
        ckey = self._coll_key.get().strip()

        if not cid:
            self._err_lbl.config(text="Campo obrigatorio: ID do Cliente.")
            return
        if not cid.isdigit():
            self._err_lbl.config(text="O ID do Cliente deve ser um numero.")
            return
        if not ckey:
            self._err_lbl.config(text="Campo obrigatorio: Chave Coletora.")
            return
        if len(ckey) < 6:
            self._err_lbl.config(text="Chave Coletora invalida (muito curta).")
            return

        self._err_lbl.config(text="")
        self._show(2)
        threading.Thread(
            target=self._install_worker, args=(cid, ckey), daemon=True
        ).start()

    def _log(self, msg: str, color: str = TEXT_DIM) -> None:
        self._log_txt.config(state="normal")
        tag = f"t{len(self._log_txt.get('1.0', 'end'))}"
        self._log_txt.insert("end", msg + "\n", tag)
        self._log_txt.tag_config(tag, foreground=color)
        self._log_txt.see("end")
        self._log_txt.config(state="disabled")
        self.update_idletasks()

    def _progress(self, pct: int, label: str) -> None:
        self._prog["value"] = pct
        self._prog_lbl.config(text=label)
        self.update_idletasks()

    def _install_worker(self, cid: str, ckey: str) -> None:
        try:
            # 1. Pastas
            self._progress(8, "Criando pastas de instalacao...")
            self._log("Criando pastas...")
            DESTINO.mkdir(parents=True, exist_ok=True)
            (DESTINO / "bin").mkdir(exist_ok=True)
            (DESTINO / ".state").mkdir(exist_ok=True)
            self._log("  OK  C:\\ProgramData\\ETI-SENTINEL", OK_COLOR)

            # 2. Executável
            self._progress(20, "Copiando ETI_SENTINEL_Edge.exe...")
            exe_src = ORIGEM / "ETI_SENTINEL_Edge.exe"
            if not exe_src.exists():
                raise FileNotFoundError(
                    f"ETI_SENTINEL_Edge.exe nao encontrado em:\n  {ORIGEM}"
                )
            self._log("Copiando executavel (87 MB)...")
            shutil.copy2(exe_src, DESTINO / "ETI_SENTINEL_Edge.exe")
            self._log("  OK  ETI_SENTINEL_Edge.exe", OK_COLOR)

            # 3. Binários (ffmpeg, mediamtx, modelo IA)
            self._progress(40, "Copiando FFmpeg, MediaMTX e modelo IA...")
            bin_src = ORIGEM / "bin"
            if bin_src.exists():
                self._log("Copiando binarios (FFmpeg, MediaMTX, modelo IA)...")
                shutil.copytree(str(bin_src), str(DESTINO / "bin"), dirs_exist_ok=True)
                self._log("  OK  bin/", OK_COLOR)
            else:
                self._log("  AVISO  pasta bin/ nao encontrada — streaming pode nao funcionar.", ERR)

            # 4. Arquivo .env (SEM BOM — Python open() nao adiciona BOM)
            self._progress(60, "Criando configuracao...")
            self._log("Gerando arquivo .env...")
            env_lines = "\n".join([
                f"INGEST_API_URL={INGEST}",
                f"COLLECTOR_KEY={ckey}",
                f"CLIENT_ID={cid}",
                "AGENT_API_PORT=8808",
                "AGENT_API_BIND=0.0.0.0",
                "ENABLE_STREAMING=1",
                "ENABLE_DEVICE_MONITOR=1",
                "ENABLE_ONVIF_COLLECTOR=0",
                "ENABLE_DISCOVERY=0",
                "ENABLE_TRAY=0",
                "ENABLE_RECORDING=0",
                "LOG_LEVEL=INFO",
                "EDGE_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat",
                "EDGE_FORWARD_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat",
                "# --- Analiticos de Video (ativar com ENABLE_AI_ANALYTICS=1) ---",
                "ENABLE_AI_ANALYTICS=0",
                "AI_STARTUP_DELAY_SECONDS=20",
                "AI_CLASSES=person,car,motorcycle",
                "AI_PEOPLE_MAX_COUNT=0",
                "# --- Features Avancadas ---",
                "# ENABLE_DIRECTIONAL_COUNTER=1   # F7: Contador entrada/saida",
                "# ENABLE_LOITERING=1             # F8: Permanencia prolongada",
                "# ENABLE_HEATMAP=1               # F9: Mapa de calor",
                "# ENABLE_FALL_DETECTION=1        # F10: Queda de pessoa",
                "# ENABLE_FIRE_DETECTION=1        # F11: Fogo e fumaca",
                "# ENABLE_TAMPER_DETECTION=1      # F12: Camera sabotada/coberta",
                "# --- Gravacao e Relatorios ---",
                "# ENABLE_CLIP_RECORDING=1        # Clips MP4 de 12s antes de cada alerta",
                "# ENABLE_DAILY_REPORT=1          # Relatorio diario via Telegram as 23h",
                "# --- Atualizacao automatica (OTA) ---",
                "ENABLE_OTA=0",
                "AGENT_VERSION=2.1.0",
            ])
            with open(DESTINO / ".env", "w", encoding="utf-8", newline="\n") as fp:
                fp.write(env_lines + "\n")
            self._log("  OK  .env criado (sem BOM)", OK_COLOR)

            # 5. Registro no Windows
            self._progress(78, "Registrando inicializacao automatica...")
            self._log("Registrando no Windows...")
            exe_dest = str(DESTINO / "ETI_SENTINEL_Edge.exe")
            nssm     = DESTINO / "bin" / "nssm.exe"

            if nssm.exists():
                subprocess.run([str(nssm), "stop",    SVC_NAME], capture_output=True)
                subprocess.run([str(nssm), "remove",  SVC_NAME, "confirm"], capture_output=True)
                subprocess.run([str(nssm), "install", SVC_NAME, exe_dest],
                               capture_output=True, check=True)
                subprocess.run([str(nssm), "set", SVC_NAME, "AppDirectory", str(DESTINO)],
                               capture_output=True)
                subprocess.run([str(nssm), "set", SVC_NAME, "AppRestartDelay", "5000"],
                               capture_output=True)
                subprocess.run([str(nssm), "set", SVC_NAME, "Start", "SERVICE_AUTO_START"],
                               capture_output=True)
                subprocess.run([str(nssm), "start", SVC_NAME], capture_output=True)
                self._log("  OK  Servico Windows registrado (NSSM)", OK_COLOR)
            else:
                subprocess.run(["schtasks", "/delete", "/tn", SVC_NAME, "/f"],
                               capture_output=True)
                subprocess.run([
                    "schtasks", "/create", "/tn", SVC_NAME,
                    "/tr", f'"{exe_dest}"',
                    "/sc", "onstart", "/ru", "SYSTEM", "/rl", "HIGHEST", "/f",
                ], capture_output=True, check=True)
                subprocess.run(["schtasks", "/run", "/tn", SVC_NAME], capture_output=True)
                self._log("  OK  Tarefa agendada criada (Agendador Windows)", OK_COLOR)

            # 6. Verifica processo
            self._progress(92, "Verificando agente...")
            time.sleep(3)
            result = subprocess.run(
                ["tasklist", "/fi", "imagename eq ETI_SENTINEL_Edge.exe"],
                capture_output=True, text=True,
            )
            if "ETI_SENTINEL_Edge.exe" in result.stdout:
                self._log("  OK  Agente ETI SENTINEL rodando!", OK_COLOR)
            else:
                self._log("  INFO  Agente sera iniciado no proximo boot.", TEXT_DIM)

            self._progress(100, "Concluido!")
            self._log("\nInstalacao concluida com sucesso!", OK_COLOR)
            time.sleep(1)
            self.after(0, lambda: self._show(3))

        except Exception as exc:
            self._log(f"\nERRO: {exc}", ERR)
            self._progress(0, "Falha na instalacao.")
            self.after(0, lambda: self._btn_next.config(
                state="normal", text="Fechar", command=self.destroy, bg=ERR,
            ))


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def main() -> None:
    if not _is_admin():
        _relaunch_as_admin()
        sys.exit(0)

    app = Wizard()
    app.mainloop()


if __name__ == "__main__":
    main()
