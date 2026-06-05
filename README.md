# ETI SENTINEL — Monitoramento Inteligente de Infraestrutura

Sistema de monitoramento com Edge Agent Windows, alertas em tempo real via Telegram/WhatsApp, painel React, 12 features de IA embarcada e configuração remota de clientes via OTA.

---

## Arquitetura Atual

```
[Câmeras RTSP / DVRs]
        |
[Edge Agent (EXE Windows)] ──────────────────────────────────────────┐
   • Heartbeat a cada 15s                                             │
   • Analíticos de IA (ONNX — opcional)                              │
   • API local em http://localhost:8808                               │
        |                                                             │
        ▼                                                             │
[Ingest API — Railway (Node.js/Express)]                             │
        |                                                             │
   ┌────┴──────────────┐                                             │
   │                   │                                             │
[Processor Python]  [WebSocket Server (Socket.IO)]                  │
   • Avalia alertas   • Push realtime                                │
   • Telegram / WA         |                                         │
                     [Frontend React + Vite]  ◄───────────────────┘
                      http://localhost:8808
                      (também servido pelo Edge Agent)
```

| Componente | Tecnologia | Onde roda | Função |
|---|---|---|---|
| `edge-agent` | Python → EXE (PyInstaller) | Windows do cliente | Coleta eventos, IA local, API local |
| `ingest-api` | Node.js + Express | Railway (nuvem) | Recebe e desuplica eventos |
| `processor` | Python | Railway (nuvem) | Avalia thresholds e dispara alertas |
| `websocket-server` | Node.js + Socket.IO | Railway (nuvem) | Push realtime para o frontend |
| `frontend` | React + Vite | Railway / local | Dashboard de monitoramento |

---

## Instalação no Cliente (Campo)

### Opção 1 — Wizard visual (recomendado)

O técnico faz duplo clique em **`ETI_SENTINEL_Setup.exe`** e segue o assistente (4 telas):

1. Boas-vindas
2. Dados do cliente (URL da API, Chave, ID do cliente)
3. Instalando (automático — NSSM ou Agendador de Tarefas como fallback)
4. Concluído

### Opção 2 — Instalador bat

```bat
REM Executar como Administrador
INSTALAR.bat
```

Versão atual: **v2.1**

### O que o instalador faz

- Cria `C:\ProgramData\ETI-SENTINEL\` e copia os arquivos
- Gera `.env` **sem BOM** (crítico — BOM quebra a leitura da `INGEST_API_URL`)
- Registra o agente para iniciar automaticamente no login do Windows
- Suprime heartbeats de gerar spam no celular do cliente
- Documenta as features avançadas (F7–F10) como comentário no `.env`

### Desinstalação e diagnóstico

```bat
DESINSTALAR.bat    REM remove o serviço e os arquivos
VERIFICAR.bat      REM diagnóstico rápido de status
```

---

## Configuração — .env de Produção

Localização: `C:\ProgramData\ETI-SENTINEL\.env`

```env
INGEST_API_URL=https://eti-sentinel-production.up.railway.app
COLLECTOR_KEY=<chave do cliente>
CLIENT_ID=<id do cliente>
AGENT_API_PORT=8808
EDGE_PUSH_URL=http://127.0.0.1:8808/api/push
ENABLE_STREAMING=1
ENABLE_DEVICE_MONITOR=1
ENABLE_AI_ANALYTICS=1
ENABLE_FIRE_DETECTION=1
ENABLE_TAMPER_DETECTION=1

# Supressão de alertas (não geram notificação no celular)
EDGE_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat
EDGE_FORWARD_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat
```

> **CRÍTICO:** O `.env` deve ser gravado **sem BOM**. Use `System.IO.File::WriteAllLines` com `UTF8Encoding($false)` — nunca `Set-Content -Encoding UTF8`.

### Variáveis avançadas (features de IA)

| Variável | Padrão | Descrição |
|---|---|---|
| `ENABLE_AI_ANALYTICS` | `1` | `1` ativa todos os analíticos de vídeo |
| `ENABLE_AI_NARRATIVE` | `0` | `1` ativa relatório narrativo via Claude Haiku |
| `ENABLE_AUDIO_ANOMALY` | `0` | `1` ativa detecção de áudio anômalo |
| `ENABLE_PLATE_RECOGNITION` | `0` | `1` ativa reconhecimento de placas |
| `ENABLE_BEHAVIORAL_LEARNING` | `0` | `1` ativa aprendizado comportamental |
| `AI_EVENT_COOLDOWN_SECONDS` | `300` | Cooldown entre eventos de IA da mesma câmera |
| `AI_DETECTION_COOLDOWN` | `600` | Cooldown no processor para eventos `ai_*` genéricos |
| `AI_CONF_THRESHOLD` | `0.50` | Confiança mínima de detecção (0.0–1.0) |
| `AI_FRAME_EVERY_SECONDS` | `1.0` | Intervalo entre frames analisados |
| `AI_STARTUP_DELAY_SECONDS` | `20` | Delay antes de iniciar analíticos |
| `AI_PEOPLE_MAX_COUNT` | `0` | Alerta de lotação (0 = desabilitado) |
| `AI_ABANDON_SECONDS` | `30` | Tempo sem pessoa para disparar abandono de objeto |
| `AI_BEHAVIOR_LEARN_DAYS` | `7` | Dias de aprendizado antes de suprimir falsos positivos |
| `AI_PLATE_WHITELIST` | — | Placas permitidas (CSV) |
| `AI_PLATE_BLACKLIST` | — | Placas bloqueadas (CSV) |
| `PROCESSOR_SUPPRESS_EVENT_TYPES` | — | Tipos de evento silenciados no processor |
| `ENABLE_FIRE_DETECTION` | `0` | `1` ativa detecção de fogo e fumaça (F11) |
| `AI_FIRE_AREA_THRESHOLD` | `0.012` | Fração mínima do frame com cor de fogo (1.2%) |
| `AI_FIRE_CONFIRM_FRAMES` | `4` | Frames consecutivos para confirmar fogo |
| `AI_FIRE_ALERT_INTERVAL` | `120` | Intervalo mínimo entre alertas de fogo (s) |
| `ENABLE_TAMPER_DETECTION` | `0` | `1` ativa detecção de câmera sabotada (F12) |
| `AI_TAMPER_BASELINE_FRAMES` | `60` | Frames para aprender perfil normal da câmera |
| `AI_TAMPER_CONFIRM_FRAMES` | `8` | Frames consecutivos para confirmar sabotagem |
| `AI_TAMPER_ALERT_INTERVAL` | `180` | Intervalo mínimo entre alertas de sabotagem (s) |
| `ENABLE_CLIP_RECORDING` | `0` | `1` grava clips MP4 de 12s antes de cada alerta |
| `CLIP_PRE_EVENT_SECONDS` | `12` | Segundos de buffer pré-alerta gravados |
| `CLIP_FPS` | `6` | FPS do clip gravado |
| `CLIP_MAX_AGE_HOURS` | `48` | Horas até clips antigos serem deletados |
| `CLIP_MAX_PER_CAMERA` | `20` | Máximo de clips armazenados por câmera |
| `ENABLE_DAILY_REPORT` | `0` | `1` envia relatório diário via Telegram às 23h |
| `REPORT_SEND_HOUR` | `23` | Hora do envio do relatório diário (0-23) |
| `QUEUE_MAX_AGE_HOURS` | `24` | Horas até eventos offline expirados serem descartados |
| `QUEUE_MAX_SIZE` | `500` | Máximo de eventos na fila offline |

---

## Features de IA Embarcada

Todas as features são opcionais e ativadas individualmente no `.env`. Requerem `ENABLE_AI_ANALYTICS=1` e o modelo `bin/modelo_ia.onnx`.

| # | Feature | Arquivo | Como ativar |
|---|---|---|---|
| F1 | **Score de Risco em Tempo Real** (0–100) | `workers/risk_scorer.py` | Ativo por padrão com IA ligada |
| F2 | **Relatório Narrativo com IA** | `workers/narrative_reporter.py` | `ENABLE_AI_NARRATIVE=1` + `ANTHROPIC_API_KEY` |
| F3 | **Detecção de Abandono de Objeto** | `workers/abandoned_object_detector.py` | `ENABLE_AI_ANALYTICS=1` |
| F4 | **Detecção de Anomalias de Áudio** | `workers/audio_anomaly_detector.py` | `ENABLE_AUDIO_ANOMALY=1` |
| F5 | **Reconhecimento de Placa Veicular (offline)** | `workers/plate_recognizer.py` | `ENABLE_PLATE_RECOGNITION=1` |
| F6 | **Aprendizado Comportamental por Câmera** | `workers/behavioral_learner.py` | `ENABLE_BEHAVIORAL_LEARNING=1` |
| F7 | **Contador Direcional de Pessoas** (entrada/saída) | `workers/directional_counter.py` | `ENABLE_AI_ANALYTICS=1` |
| F8 | **Detecção de Permanência Prolongada** (loitering) | `workers/loitering_detector.py` | `ENABLE_AI_ANALYTICS=1` |
| F9 | **Mapa de Calor de Movimentação** | `workers/heatmap_generator.py` | `ENABLE_AI_ANALYTICS=1` |
| F10 | **Detecção de Queda de Pessoa** | `workers/fall_detector.py` | `ENABLE_AI_ANALYTICS=1` |
| F11 | **Detecção de Fogo e Fumaça** | `workers/fire_smoke_detector.py` | `ENABLE_FIRE_DETECTION=1` |
| F12 | **Detecção de Câmera Sabotada** (coberta/virada) | `workers/tamper_detector.py` | `ENABLE_TAMPER_DETECTION=1` |
| — | **Clips de Vídeo nos Alertas** (buffer 15s pré-evento) | `workers/clip_recorder.py` | `ENABLE_CLIP_RECORDING=1` |
| — | **Relatório Diário Automático** (Telegram + HTML) | `workers/report_generator.py` | `ENABLE_DAILY_REPORT=1` |

### Detalhes das features

**F1 — Score de Risco:** índice 0–100 com decaimento exponencial (meia-vida 10 min), ponderado por horário e tipo de evento. Disponível em `/api/risk` e exibido no painel técnico.

**F2 — Relatório Narrativo:** Claude Haiku gera análise em PT-BR ~2,5s após o alerta, enviada como mensagem de follow-up no Telegram.

**F3 — Abandono de Objeto:** rastreamento por centroide. Alerta `ai_abandoned_object` após `AI_ABANDON_SECONDS` sem pessoa próxima. Detecta: mochila, mala, bolsa, etc.

**F4 — Anomalias de Áudio:** FFmpeg extrai áudio do stream RTSP; numpy classifica: vidro quebrando, grito, alarme, barulho forte.

**F5 — Placas Veiculares:** morfologia OpenCV para localizar a região da placa + easyocr para leitura. Suporta whitelist/blacklist.

**F6 — Aprendizado Comportamental:** matriz `[7 dias × 48 slots]` com estatísticas de Welford. Aprende padrão normal e suprime falsos positivos automaticamente. Estado salvo em `behavior.json`.

**F7 — Contador Direcional:** linha virtual configurável; conta pessoas cruzando em cada sentido.

**F8 — Loitering:** alerta quando uma pessoa permanece na mesma área por tempo superior ao configurado.

**F9 — Mapa de Calor:** acumula posições de detecção e gera imagem de calor por câmera.

**F10 — Queda de Pessoa:** detecta proporção e trajetória da bounding box para identificar quedas.

---

## Configuração Remota de Clientes (OTA env_patch)

O sistema permite atualizar variáveis do `.env` de clientes já instalados **sem acesso físico ao computador**.

### Como funciona

1. No **Portal Admin** → linha do cliente → botão **📡 Config .env**
2. Ative/desative features ou ajuste parâmetros no painel
3. Clique **🚀 Enviar para Agente**
4. Em até 1 hora o agente recebe, aplica no `.env` e reinicia automaticamente

### Via API (direto)

```http
PUT /admin/clients/:id/env-patch
Authorization: Bearer <jwt>

{
  "env_patch": {
    "ENABLE_AI_ANALYTICS": "1",
    "ENABLE_FIRE_DETECTION": "1",
    "ENABLE_TAMPER_DETECTION": "1",
    "AI_CONF_THRESHOLD": "0.55"
  }
}
```

### Variáveis permitidas remotamente

As seguintes variáveis podem ser atualizadas via env_patch. Credenciais e URLs são **bloqueadas por segurança** (`COLLECTOR_KEY`, `INGEST_API_URL`, `CLIENT_ID`).

| Categoria | Variáveis |
|---|---|
| Analíticos | `ENABLE_AI_ANALYTICS`, `ENABLE_FIRE_DETECTION`, `ENABLE_TAMPER_DETECTION`, `ENABLE_FALL_DETECTION`, `ENABLE_LOITERING`, `ENABLE_HEATMAP`, `ENABLE_CLIP_RECORDING`, `ENABLE_DAILY_REPORT` |
| Parâmetros | `AI_CLASSES`, `AI_CONF_THRESHOLD`, `AI_NMS_THRESHOLD`, `AI_FRAME_EVERY_SECONDS`, `AI_EVENT_COOLDOWN_SECONDS`, `AI_PEOPLE_MAX_COUNT`, `AI_STARTUP_DELAY_SECONDS` |
| Sistema | `ENABLE_OTA`, `LOG_LEVEL`, `OTA_CHECK_INTERVAL_MIN`, `AGENT_VERSION` |

---

## Build e Distribuição

```powershell
# 1. Instalar dependências Python
pip install onnxruntime-directml opencv-python pyinstaller python-dotenv requests psutil

# 2. Exportar modelo (apenas uma vez)
python exportar_modelo.py        # gera bin/modelo_ia.onnx

# 3. Compilar o agente
python build_exe.py              # gera ETI_SENTINEL_CLIENT_READY/

# 4. Compilar o wizard de instalação (opcional)
python build_setup.py            # gera ETI_SENTINEL_Setup.exe

# 5. Copiar ETI_SENTINEL_CLIENT_READY/ para pendrive e entregar ao cliente
```

O EXE gerado tem **~88 MB** (otimizado — era 292 MB antes).

---

## Changelog

### 2026-06-05

- **fix (instalador):** `INSTALAR.bat` e `build_exe.py` geravam `.env` com `ENABLE_AI_ANALYTICS=0` — analíticos de vídeo nunca eram ativados nos clientes. Corrigido para `=1` por padrão. `ENABLE_FIRE_DETECTION=1` e `ENABLE_TAMPER_DETECTION=1` também ativados por padrão.
- **feat (OTA env_patch):** OTA agora distribui configurações do `.env` remotamente sem acesso físico ao cliente. Backend: coluna `clients.env_patch JSONB`, endpoint `PUT /admin/clients/:id/env-patch`, `env_patch` incluído na resposta do `/collector/update-check`. Agente: `_apply_env_patch()` com allowlist de segurança — aplica no `.env` e reinicia se houver mudanças.
- **feat (Admin):** Botão **📡 Config .env** no Portal Admin para cada cliente — toggles visuais para features de IA e inputs para parâmetros avançados, sem precisar usar a API diretamente.

### [não commitado] — 2026-06-02

- **feat (F11):** Detecção de Fogo e Fumaça (`workers/fire_smoke_detector.py`) — análise HSV + variância temporal, sem modelo extra. Ativar: `ENABLE_FIRE_DETECTION=1`.
- **feat (F12):** Detecção de Câmera Sabotada (`workers/tamper_detector.py`) — detecta câmera coberta, virada ou desfocada por histograma e bordas. Ativar: `ENABLE_TAMPER_DETECTION=1`.
- **feat:** Gravador de Clips MP4 (`workers/clip_recorder.py`) — buffer circular de 12s por câmera, grava evidência antes de cada alerta. Ativar: `ENABLE_CLIP_RECORDING=1`.
- **feat:** Relatório Diário Automático (`workers/report_generator.py`) — enviado via Telegram às 23h e salvo como HTML em `.reports/`. Ativar: `ENABLE_DAILY_REPORT=1`.
- **fix (agent_api.py):** `_flush_once` não enviava `x-collector-key` ao reenviar fila offline — Railway rejeitava todos silenciosamente. Corrigido. Adicionados TTL e tamanho máximo da fila (`QUEUE_MAX_AGE_HOURS`, `QUEUE_MAX_SIZE`).

### [não commitado] — 2026-05-31

- **fix:** `AI_EVENT_COOLDOWN_SECONDS` padrão aumentado de 45s para **300s** no `ai_worker_onnx.py` — reduz falsos positivos em ambientes com movimento contínuo.

### 2026-05-28

- **fix (processor):** supressão por prefixo para eventos `ai_*` genéricos — qualquer evento cujo tipo começa com `ai_` e não é de segurança recebe `AI_DETECTION_COOLDOWN` (padrão 600s) em vez dos 60s normais. Cobre tipos desconhecidos de DVR sem precisar de lista explícita.
- Tipos silenciosos adicionados: `ai_heatmap`, `ai_debug`.
- Tipos de segurança definidos: `zone_intrusion`, `line_crossing`, `fall`, `crowd`, `abandon`, `loiter`, `plate_blocked`.
- Nova env: `AI_DETECTION_COOLDOWN`, `PROCESSOR_SUPPRESS_EVENT_TYPES`.

### 2026-05-25

- **fix (ingest-api):** TTL de deduplicação aumentado de 2.500 ms para `ALERT_COOLDOWN` (120s) — elimina chuva de alertas duplicados do DVR ElSYS.
- **fix (ingest-api):** chave de dedup mudou de por-canal para por-dispositivo (remove `ch` e `desc` da key).
- **fix (processor):** cooldown de `check_new_events` agora é por-dispositivo (era por-canal).
- **fix (processor):** `gateway_heartbeat` adicionado à lista de tipos silenciosos.
- **fix (processor):** `set_cooldown` movido para antes dos sends — evita reenvio em caso de falha parcial.

### 2026-05-24

- **fix (INSTALAR.bat v2.1 — 2ª revisão):** adiciona `EDGE_SUPPRESS_EVENT_TYPES` e `EDGE_FORWARD_SUPPRESS_EVENT_TYPES` no `.env` gerado para suprimir heartbeats no celular do cliente. Features F7–F10 documentadas como comentários no `.env`.

### 2026-05-21

- **feat:** Instalador visual `ETI_SENTINEL_Setup.exe` — wizard tkinter com 4 telas, solicita elevação de administrador automaticamente, fallback automático NSSM → Agendador de Tarefas.
- **fix (INSTALAR.bat v2.1 — 1ª revisão):** BOM crítico corrigido (`Set-Content -Encoding UTF8` substituído por `WriteAllLines UTF8Encoding($false)`). Sem esse fix o `INGEST_API_URL` não era reconhecido e o agente ficava sem conexão com a nuvem.
- **fix (ai_worker_onnx.py):** filtro de animais detectados como pessoa — adicionada `_ANIMAL_CLASSES`, filtro de proporção `h/w < 0.4` e filtro runner-up (margem < 0,15 com classe animal → detecção rejeitada).
- **fix (ai_worker_onnx.py):** bug de letterbox padding — `_letterbox` retornava `(dw, dh)` float mas aplicava `(left, top)` int, causando bounding boxes deslocadas. Corrigido para retornar `(left, top)`.

### 2026-05-21 — Features F7–F10

- **feat (F10):** Detecção de Queda de Pessoa (`workers/fall_detector.py`)
- **feat (F9):** Mapa de Calor de Movimentação (`workers/heatmap_generator.py`)
- **feat (F8):** Detecção de Permanência Prolongada / Loitering (`workers/loitering_detector.py`)
- **feat (F7):** Contador Direcional de Pessoas — entrada/saída (`workers/directional_counter.py`)

### Anteriores — Features F1–F6 e correções de produção

- **feat (F6):** Aprendizado Comportamental por Câmera
- **feat (F5):** Reconhecimento de Placa Veicular Offline
- **feat (F4):** Detecção de Anomalias de Áudio
- **feat (F3):** Detecção de Abandono de Objeto
- **feat (F2):** Relatório Narrativo com IA (Claude Haiku)
- **feat (F1):** Score de Risco em Tempo Real (0–100)
- **fix:** snapshot via FFmpeg — resolve imagem cinza em streams H.265/NV12
- **fix:** imagens cinzas e distorcidas nos alertas de IA corrigidas
- **fix:** Frontend React reformulado — remove features falsas, adiciona dados reais
- **fix (edge-agent):** `__file__` no EXE aponta para pasta temp do PyInstaller → corrigido com `sys.executable` / `sys.frozen`
- **fix (agent_api.py):** `_read_json()` lia o Content-Length mas nunca lia o body → corrigido
- **fix (agent_api.py):** `_forward_push()` não enviava `x-collector-key` → Railway rejeitava todos os eventos
- **fix (device_monitor.py):** rodava como subprocesso Python (inexistente no cliente) → agora roda como thread quando `sys.frozen=True`
- **fix (watchdog_worker.py):** chamava `restart_stream()` inexistente → corrigido

---

## Estrutura de Pastas

```
ETI SENTINEL/
├── edge-agent/
│   ├── workers/
│   │   ├── ai_worker_onnx.py          # Inferência ONNX (sem PyTorch)
│   │   ├── ai_analytics.py            # Zonas, linhas virtuais, contagem
│   │   ├── risk_scorer.py             # F1 — Score de Risco
│   │   ├── narrative_reporter.py      # F2 — Relatório Narrativo IA
│   │   ├── abandoned_object_detector.py  # F3
│   │   ├── audio_anomaly_detector.py  # F4
│   │   ├── plate_recognizer.py        # F5
│   │   ├── behavioral_learner.py      # F6
│   │   ├── directional_counter.py     # F7
│   │   ├── loitering_detector.py      # F8
│   │   ├── heatmap_generator.py       # F9
│   │   ├── fall_detector.py           # F10
│   │   ├── fire_smoke_detector.py     # F11 — Fogo e Fumaça
│   │   ├── tamper_detector.py         # F12 — Câmera Sabotada
│   │   ├── clip_recorder.py           # Gravação de clips MP4
│   │   ├── report_generator.py        # Relatório diário
│   │   ├── ota_updater.py             # OTA — atualização EXE + env_patch
│   │   ├── heartbeat_worker.py
│   │   ├── stream_worker.py
│   │   └── watchdog_worker.py
│   ├── edge_agent.py
│   ├── agent_api.py
│   └── device_monitor.py
├── ingest-api/                        # Node.js/Express — Railway
├── processor/                         # Python — Railway
├── websocket-server/                  # Socket.IO — Railway
├── frontend/                          # React + Vite
├── ETI_SENTINEL_CLIENT_READY/
│   ├── ETI_SENTINEL_Setup.exe         # Wizard visual de instalação
│   ├── INSTALAR.bat                   # Instalador bat (v2.1)
│   ├── DESINSTALAR.bat
│   └── VERIFICAR.bat
├── setup_wizard.py                    # Código-fonte do wizard
├── build_setup.py                     # Compila setup_wizard → EXE
├── build_exe.py                       # Compila edge-agent → EXE
└── exportar_modelo.py                 # Converte YOLOv8 → ONNX
```

---

## Estado Atual do Sistema (2026-06-05)

| Item | Status |
|---|---|
| Edge Agent EXE | Funcionando — 88 MB |
| Heartbeat spam | Suprimido — celular não recebe spam |
| Conexão Railway | Operacional |
| Dashboard local | `http://localhost:8808` |
| Inicialização automática | HKCU Run (login do usuário) |
| Instalador visual | `ETI_SENTINEL_Setup.exe` disponível |
| Analíticos de IA | **Ativos por padrão** — `ENABLE_AI_ANALYTICS=1` no instalador |
| Fogo e Fumaça (F11) | **Ativo por padrão** — `ENABLE_FIRE_DETECTION=1` no instalador |
| Câmera Sabotada (F12) | **Ativo por padrão** — `ENABLE_TAMPER_DETECTION=1` no instalador |
| OTA env_patch | Operacional — configurações distribuídas remotamente pelo painel admin |
| Cooldown de eventos IA | 300s (edge) / 600s (processor para `ai_*` genéricos) |
| Deduplicação de alertas | Por dispositivo, TTL 120s |
