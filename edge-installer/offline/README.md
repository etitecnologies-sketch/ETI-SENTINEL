# ETI SENTINEL — Bundle Offline (Modo SaaS)

Este diretório descreve o formato do bundle offline usado por `Setup-ETI-SENTINEL-Edge.ps1` quando o cliente não tem `winget` e/ou não consegue baixar dependências (proxy corporativo, bloqueio de Store, sem internet).

## Como usar

- Pasta:
  - Execute `Setup-ETI-SENTINEL-Edge.ps1 -OfflineBundle "C:\caminho\para\bundle"`
- ZIP:
  - Execute `Setup-ETI-SENTINEL-Edge.ps1 -OfflineBundle "C:\caminho\para\bundle.zip"`

Também é suportado `ETI_OFFLINE_BUNDLE` como variável de ambiente.

## Estrutura esperada do bundle

O bundle é uma pasta (ou zip) com esta estrutura:

- `winsw/`
  - `WinSW-x64.exe` **ou** `winsw.exe`
- `python/`
  - `python-3.12.10-amd64.exe` (ou outra 3.12.x)
  - (opcional) `python-installer.exe`
- `ffmpeg/`
  - `ffmpeg.exe` (+ opcional `ffprobe.exe`) **ou**
  - `ffmpeg-release-essentials.zip` **ou** `ffmpeg.zip`
- `mediamtx/`
  - `mediamtx.exe` (+ opcional `mediamtx.yml`) **ou**
  - `mediamtx_v1.9.0_windows_amd64.zip` **ou** `mediamtx.zip`
- `wheelhouse/` (opcional, recomendado para offline “real”)
  - arquivos `*.whl` para instalar `edge-agent/requirements.txt` sem internet

## Observações

- Se `wheelhouse/` existir, o instalador usa `pip install --no-index --find-links wheelhouse -r requirements.txt`.
- Sem `wheelhouse/`, a instalação de requirements ainda precisa de acesso à internet (PyPI).

