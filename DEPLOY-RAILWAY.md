# Deploy no Railway (Modo Serviços Separados) 🚀

Para o **ETI SENTINEL** rodar com máxima estabilidade 24/7, recomendamos criar serviços separados no Railway para cada parte do sistema.

## 1. Banco de Dados (TimescaleDB)
- **New** -> **Database** -> **PostgreSQL**.
- O Railway adicionará o plugin TimescaleDB automaticamente se disponível ou use uma imagem Docker personalizada se preferir.
- Anote a `DATABASE_URL`.

### Importante: criar o schema
- Execute o arquivo `sql/schema.sql` no seu banco (Railway -> Data/Query ou via `psql`).
- O schema tenta usar TimescaleDB se estiver disponível, mas funciona também em PostgreSQL puro.

## 2. Ingest API (O Coração)
- **New** -> **GitHub Repo** -> Selecione o repo.
- Em **Settings** -> **Root Directory**, coloque: `ingest-api`.
- **Variables**:
  - `DATABASE_URL`: (Vem do banco de dados)
  - `JWT_SECRET`: Uma senha forte
  - `CORS_ORIGIN`: `*`
  - `WEBSOCKET_URL`: URL interna do seu serviço WebSocket (ex: `http://websocket:3001`)

## 3. WebSocket Server (Real-time)
- **New** -> **GitHub Repo** -> Selecione o repo.
- Em **Settings** -> **Root Directory**, coloque: `websocket-server`.
- **Variables**:
  - `PORT`: `3001`

## 4. Frontend (Painel Web)
- **New** -> **GitHub Repo** -> Selecione o repo.
- Em **Settings** -> **Root Directory**, coloque: `frontend`.
- **Variables**:
  - `VITE_API_URL`: A URL pública da sua **Ingest API** (ex: `https://api-production.up.railway.app`)
  - `VITE_WS_URL`: A URL pública do seu **WebSocket** (ex: `https://ws-production.up.railway.app`)

## 5. Processor (Alertas)
- **New** -> **GitHub Repo** -> Selecione o repo.
- Em **Settings** -> **Root Directory**, coloque: `processor`.
- **Variables**:
  - `DATABASE_URL`: (Mesma do banco)
  - Configurações de SMTP/Telegram se desejar alertas.

---

## 6. Video-Service (Etapa 2 — Descoberta/Health/HLS)
- **New** -> **GitHub Repo** -> Selecione o repo.
- Em **Settings** -> **Root Directory**, coloque: `video-service`.
- **Variables**:
  - `INGEST_API_URL`: URL interna do ingest-api no Railway (ex: `https://seu-ingest-api.up.railway.app`)
  - `COLLECTOR_KEY`: mesma chave usada pelos collectors
  - `CLIENT_ID`: (opcional) filtra RTSP configs por cliente
  - `ADMIN_TOKEN`: JWT de um superadmin (opcional, necessário para auto-registrar câmeras via discovery)
  - `DISCOVERY_INTERVAL_SECONDS`: 0 desliga discovery (ex: `60` para buscar a cada 1 min)
  - `HEALTH_INTERVAL_SECONDS`: 0 desliga health (ex: `30` para monitorar RTSP)

### Endpoints úteis
- `/health`
- `/discover?run_register=true` (requer `ADMIN_TOKEN`)
- `/streams`
- `/hls/{device_id}/{channel}/index.m3u8`

### Por que separar?
1. **Logs Individuais**: Se a API cair, você sabe exatamente o porquê sem afetar o Frontend.
2. **Escalabilidade**: Você pode dar mais memória apenas para o Banco ou para a API.
3. **Economia**: O Railway só cobra pelo que cada serviço pequeno consome.
