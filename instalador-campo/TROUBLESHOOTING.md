# Troubleshooting rápido

## Onde ver logs

- Logs dos serviços (instalação nova): `C:\ProgramData\ETI-SENTINEL\.logs`
- Logs do Edge: `C:\ProgramData\ETI-SENTINEL\edge-agent\.state`

## Erros comuns

### 1) `401 Unauthorized` nos `/collector/*`
- `COLLECTOR_KEY` errada ou rotacionada.
- Solução: pegar a chave atual no painel (aba `🔑 Edge`) e atualizar o `.env` de cada Edge do cliente.

### 5) Quero atualizar o Edge

- Online: `02-Instalar-Edge-Online.ps1 -Update`
- Offline: `03-Instalar-Edge-Offline.ps1 -OfflineBundle ... -Update`

### 2) `Health-check falhou`
- Validar se `ffmpeg.exe` e `mediamtx.exe` existem em `C:\ProgramData\ETI-SENTINEL\bin`.
- Em corporativo, usar `-OfflineBundle` com bundle completo.

### 3) Cliente corporativo bloqueia downloads
- Use `03-Instalar-Edge-Offline.ps1` com bundle offline.
- Para offline real (sem PyPI), o bundle precisa ter `wheelhouse/`.

### 4) Serviços não iniciam
- Verificar em `services.msc`.
- Ver logs em `C:\ProgramData\ETI-SENTINEL\.logs`.

### 6) MediaMTX não inicia (erro bind UDP :8000)

Sintoma comum:
- `ERR listen udp :8000: bind: Only one usage of each socket address...`

Como resolver rápido:
- Pare o Edge Agent: `Stop-Service ETI_SENTINEL_EDGE_AGENT`
- Encontre e mate qualquer `mediamtx.exe` que ficou aberto manualmente (porta 8554/8000):
  - `netstat -ano | findstr ":8554"`
  - `tasklist /FI "PID eq <PID>"`
  - `Stop-Process -Id <PID> -Force`
- Inicie o MediaMTX: `Start-Service ETI_SENTINEL_MEDIAMTX`
- Inicie o Edge Agent: `Start-Service ETI_SENTINEL_EDGE_AGENT`

Observação:
- A instalação nova força `protocols: [tcp]` no `mediamtx.yml`, reduzindo conflito em UDP e melhorando estabilidade.
