# ETI SENTINEL — Monitoramento Inteligente de Infraestrutura

Sistema de monitoramento com Edge Agent Windows, alertas em tempo real via Telegram/WhatsApp, painel React e 10 features de IA embarcada.

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
ENABLE_AI_ANALYTICS=0

# Supressão de alertas (não geram notificação no celular)
EDGE_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat
EDGE_FORWARD_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat
```

> **CRÍTICO:** O `.env` deve ser gravado **sem BOM**. Use `System.IO.File::WriteAllLines` com `UTF8Encoding($false)` — nunca `Set-Content -Encoding UTF8`.

### Variáveis avançadas (features de IA)

| Variável | Padrão | Descrição |
|---|---|---|
| `ENABLE_AI_ANALYTICS` | `0` | `1` ativa todos os analíticos de vídeo |
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

## Estado Atual do Sistema (2026-05-31)

| Item | Status |
|---|---|
| Edge Agent EXE | Funcionando — 88 MB |
| Heartbeat spam | Suprimido — celular não recebe spam |
| Conexão Railway | Operacional |
| Dashboard local | `http://localhost:8808` |
| Inicialização automática | HKCU Run (login do usuário) |
| Instalador visual | `ETI_SENTINEL_Setup.exe` disponível |
| Analíticos de IA | Disponíveis — ativar com `ENABLE_AI_ANALYTICS=1` |
| Cooldown de eventos IA | 300s (edge) / 600s (processor para `ai_*` genéricos) |
| Deduplicação de alertas | Por dispositivo, TTL 120s |
