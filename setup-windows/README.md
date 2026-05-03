# Setup Windows (Online)

Este instalador é um "setup" online (estilo UltraViewer): ele abre uma janela, pede `INGEST_API_URL`, `CLIENT_ID` e `COLLECTOR_KEY`, baixa o repositório (main.zip) e executa o instalador oficial do Edge.

## Rodar como script (sem EXE)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
./setup-windows/Setup-ETI-SENTINEL-Edge-GUI.ps1
```

## Gerar um EXE (IExpress)

No Windows, rode:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
./setup-windows/Build-Setup-EXE.ps1
```

Saída padrão:
- `./dist/ETI-SENTINEL-Edge-Setup.exe`

Observação: o EXE é um bootstrapper. Ele ainda baixa a versão mais recente do `main` na hora da instalação.

