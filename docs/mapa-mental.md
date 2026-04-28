# ETI SENTINEL — Mapa mental do projeto

Este documento resume os módulos, fluxos e pontos de melhoria do ETI SENTINEL.

## Mindmap (Mermaid)

```mermaid
mindmap
  root((ETI SENTINEL))
    Objetivo
      Monitoramento de infraestrutura
      Multi-tenant (clientes)
      Tempo real (WebSocket)
      Alertas (processor)
      Extensões (ONVIF/RTSP)
    Frontend (React/Vite)
      src/App.jsx
        Login/Setup
        Sidebar + Dashboard
        Clientes (superadmin)
        Devices
        Triggers
        Alertas
        Eventos
        Solar
      Variáveis
        VITE_API_URL
        VITE_WS_URL
      Build/Deploy
        Docker + Nginx
        Railway (Root Directory: frontend)
    Ingest API (Node/Express)
      Endpoints
        /health
        /ready
        /auth/status
        /auth/setup
        /auth/login
        /metrics (HTTP)
        TCP ingest (porta 3002)
      Integrações
        Postgres (DATABASE_URL)
        WebSocket publish (WEBSOCKET_URL)
      Segurança
        JWT (JWT_SECRET)
        Rate limit
        Validação de payload
    WebSocket Server (Socket.IO)
      /health
      Eventos
        subscribe/unsubscribe
        metric:all
      CORS_ORIGIN
    Processor (Python)
      Funções
        Avaliar triggers
        Detectar offline
        Gerar alertas
        Notificações (Telegram/Email)
      Solar
        Coleta/API
        Persistência solar_metrics
      Variáveis
        DATABASE_URL
        EVAL_INTERVAL
        OFFLINE_TIMEOUT
        ALERT_COOLDOWN
    Banco (PostgreSQL/Timescale)
      schema.sql
        clients
        users
        devices
        metrics
        triggers
        alerts
        events
        solar_inverters
        solar_metrics
        onvif_configs
        rtsp_configs
      Índices
        idx_metrics_host_time
        idx_solar_metrics_time
      Timescale (opcional)
        hypertable
        compress/retention
    Agents/Collectors
      agent (Go)
        Coleta CPU/RAM/Disco/Rede/Latência
        Envio para /metrics
      agentes Python
        instalar_agente.py
        local_agent.py
      onvif-collector
        Inventário/telemetria ONVIF
      rtsp-monitor
        Monitoramento RTSP
    Deploy
      Docker Compose (local)
        db
        ingest-api
        websocket
        processor
        frontend
        agent
      Railway (produção)
        4 serviços separados
          postgres
          ingest-api
          websocket-server
          frontend
        (opcional)
          processor
          onvif-collector
          rtsp-monitor
    Observabilidade
      Health checks
        API /health /ready
        WS /health
      Logs
        Railway logs por serviço
    Melhorias
      Qualidade
        Testes unitários
        CI (GitHub Actions)
        Lint/format
      Segurança
        Remover defaults fracos (JWT_SECRET)
        Rotação de tokens
        RBAC por role/client_id
      Dados
        Migrações versionadas
        Backups/retention
      Produto
        Filtros/Busca
        Auditoria de eventos
        UX de onboarding
```

## Componentes (o que faz o quê)

- `frontend/` — Painel web (login/setup, dashboard, clientes, devices, triggers, alertas, eventos, solar).
- `ingest-api/` — API principal: autenticação, cadastro, ingestão de métricas, integração com Postgres e publicação para WS.
- `websocket-server/` — Canal realtime para o painel.
- `processor/` — Avaliador de triggers, offline e alertas + integrações de notificação + pipeline solar.
- `sql/schema.sql` — Schema completo do banco.
- `agent/` — Agente Go para coletar métricas e enviar para a API.
- `onvif-collector/` e `rtsp-monitor/` — coletores opcionais.

## Fluxos principais

### 1) Primeiro acesso
- Frontend chama `GET /auth/status`
- Se `setupDone=false`: mostra “CRIAR CONTA MASTER” (`POST /auth/setup`)
- Se `setupDone=true`: login (`POST /auth/login`) e guarda token

### 2) Ingestão de métricas
- Agent envia para `POST /metrics` com `X-Device-Token`
- API grava em `metrics` e atualiza `devices.last_seen/status`
- API publica resumo/stream para o WebSocket
- Frontend atualiza cards/tabela em tempo real

### 3) Alertas
- Processor lê `triggers` + `devices/metrics`
- Gera `alerts` e opcionalmente envia notificação (Telegram/Email)
- Frontend lista alertas e eventos

## Variáveis (Railway)

### ingest-api
- `DATABASE_URL`
- `JWT_SECRET`
- `CORS_ORIGIN`
- `WEBSOCKET_URL`

### websocket-server
- `PORT=3001`
- `CORS_ORIGIN`

### frontend
- `VITE_API_URL`
- `VITE_WS_URL`

### processor (se estiver em produção)
- `DATABASE_URL`
- `EVAL_INTERVAL`, `OFFLINE_TIMEOUT`, `ALERT_COOLDOWN`
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` (opcional)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL` (opcional)

## Checklist de melhorias (para você avaliar)

### Alta prioridade (impacto direto)
- Autenticação/RBAC: garantir isolamento por `client_id` em todos endpoints.
- Segredos: exigir `JWT_SECRET` forte e remover defaults em produção.
- Migrações: padronizar em uma pasta única e versionada (ex.: `migrations/NNN_*.sql`).
- Observabilidade: adicionar logs estruturados e correlação (request-id) na API.

### Média prioridade (qualidade e escala)
- Testes: Jest (Node), pytest (Python), testes de contrato para endpoints críticos.
- CI/CD: workflow com lint + build + testes + deploy.
- Performance: índices por `client_id`, paginação para lists, cache control no frontend.

### Produto/UX
- Onboarding guiado: criar cliente → criar device → gerar token → instalar agent.
- Dashboards por cliente, filtros salvos e “visões” (por tipo/tag/local).
- Auditoria: log de ações (criar/editar device/trigger) em `events`.

