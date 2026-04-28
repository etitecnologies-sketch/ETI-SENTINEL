# Video-Service (Etapa 2)

Microserviço do ETI SENTINEL focado em vídeo:

- Descoberta de câmeras ONVIF via WS-Discovery
- Health check de RTSP (gera eventos `videoloss_started`/`videoloss_stopped`)
- Gateway HLS básico (RTSP → HLS)

## Variáveis

- `INGEST_API_URL` (obrigatório)
- `COLLECTOR_KEY` (obrigatório para `/streams`, health e HLS)
- `CLIENT_ID` (opcional)
- `ADMIN_TOKEN` (opcional; necessário para `GET /discover?run_register=true` criar devices)
- `DISCOVERY_INTERVAL_SECONDS` (0 desliga)
- `HEALTH_INTERVAL_SECONDS` (0 desliga)
- `DEFAULT_TIMEOUT_SECONDS` (default 8)
- `HLS_DIR` (default `/tmp/eti-sentinel-hls`)
- `HLS_SEG_TIME` (default 2)
- `HLS_LIST_SIZE` (default 6)
- `PORT` (default 8002)

## Endpoints

- `GET /health`
- `GET /discover` (lista câmeras ONVIF)
- `GET /discover?run_register=true` (cria devices `camera-*` e registra evento; requer `ADMIN_TOKEN`)
- `GET /streams` (lista streams RTSP ativos via ingest-api)
- `GET /hls/{device_id}/{channel}/index.m3u8` (inicia HLS sob demanda)

