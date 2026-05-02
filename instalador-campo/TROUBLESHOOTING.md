# Troubleshooting rápido

## Onde ver logs

- Logs dos serviços (instalação nova): `C:\ProgramData\ETI-SENTINEL\.logs`
- Logs do Edge: `C:\ProgramData\ETI-SENTINEL\edge-agent\.state`

## Erros comuns

### 1) `401 Unauthorized` nos `/collector/*`
- `COLLECTOR_KEY` errada ou rotacionada.
- Solução: pegar a chave atual no painel (aba `🔑 Edge`) e atualizar o `.env` de cada Edge do cliente.

### 2) `Health-check falhou`
- Validar se `ffmpeg.exe` e `mediamtx.exe` existem em `C:\ProgramData\ETI-SENTINEL\bin`.
- Em corporativo, usar `-OfflineBundle` com bundle completo.

### 3) Cliente corporativo bloqueia downloads
- Use `03-Instalar-Edge-Offline.ps1` com bundle offline.
- Para offline real (sem PyPI), o bundle precisa ter `wheelhouse/`.

### 4) Serviços não iniciam
- Verificar em `services.msc`.
- Ver logs em `C:\ProgramData\ETI-SENTINEL\.logs`.

