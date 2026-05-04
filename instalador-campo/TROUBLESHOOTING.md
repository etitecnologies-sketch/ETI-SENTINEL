# Troubleshooting rápido

## Onde ver logs

- Logs dos serviços (instalação nova): `C:\ProgramData\ETI-SENTINEL\.logs`
- Logs do Edge: `C:\ProgramData\ETI-SENTINEL\edge-agent\.state`

## Erros comuns

### 0) "Python não foi encontrado" (Windows Store / App Execution Aliases)

Sintoma:
- Durante a instalação aparece: "Python não foi encontrado; executar sem argumentos para instalar do Microsoft Store..."

Causa:
- O `python.exe` do Windows está apontando para o atalho da Store (`WindowsApps`), mas o Python real não está instalado/permitido.

Como resolver (rápido):
- Configurações → Apps → Configurações avançadas de aplicativos → Aliases de execução de aplicativo
- Desative `python.exe` e `python3.exe`
- Reexecute o instalador (offline/online).

Alternativa (quando existe Python instalado mas o `python` aponta para `WindowsApps`):
- Descubra o caminho real:
  - `(Get-Command python).Source`
  - `where.exe python`
- Rode o instalador forçando o caminho:
  - `Setup-ETI-SENTINEL-Edge.ps1 -PythonExe "C:\caminho\para\python.exe"`
  - ou `setx ETI_PYTHON_EXE "C:\caminho\para\python.exe"` e reabra o PowerShell

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
