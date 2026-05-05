# ONVIF Collector

Esse serviço lê eventos ONVIF (PullPoint) de DVR/NVR/Câmeras e envia para o projeto via `POST /push` da Ingest API.

## Configuração

1. Copie [config.example.json](./onvif-collector/config.example.json) para `config.json`
2. Preencha `host`, `port`, `username`, `password` e principalmente o `token` (o token do device já cadastrado no sistema)

## Modo remoto (configurar tudo pelo sistema)

Você pode deixar o coletor buscar automaticamente a lista de dispositivos ONVIF habilitados direto da API.

1. Defina `COLLECTOR_KEY` no `.env` do **ingest-api** e no `.env` do coletor
2. No coletor, configure:
   - `ONVIF_REMOTE=true`
   - `INGEST_API_URL=http://...`
   - opcional: `CLIENT_ID=123` para filtrar por cliente

## Executar local (Windows)

```powershell
cd onvif-collector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
copy config.example.json config.json
python .\onvif_collector.py
```

## Tipos de eventos gerados

O coletor envia `event_type` compatível com o mapeamento já existente no `/push`:

- `videoloss_started` / `videoloss_stopped`
- `motion`
- `tamperdetection`
- `diskfull` / `diskerror`
- `vca` (fallback)
