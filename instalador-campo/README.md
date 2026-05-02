# ETI SENTINEL — Instalador de Campo

Esta pasta é o kit de instalação para uso em campo.

## Fluxo recomendado (sem erro)

1) No painel (superadmin): crie o cliente e copie `CLIENT_ID` + `COLLECTOR_KEY`.
2) No cliente (local A/B/C): rode o instalador online ou offline.
3) No final: valide `http://127.0.0.1:8808/api/status` e a visibilidade no painel.

## Instalação online (cliente com internet)

Abra PowerShell como Administrador e rode:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.02-Instalar-Edge-Online.ps1
```

Você vai informar:
- `INGEST_API_URL` (SaaS, igual para todos)
- `CLIENT_ID`
- `COLLECTOR_KEY`

## Instalação offline (cliente corporativo)

Pré-requisito: você levou um bundle offline (pasta ou `.zip`).

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.03-Instalar-Edge-Offline.ps1 -OfflineBundle "D:\ETI-BUNDLE.zip"
```

## Checklist

Use o checklist rápido em [CHECKLIST.md](file:///c:/Users/EZEQUIEL%20LIMA%20GUIDA/Desktop/ETI%20SENTINEL/instalador-campo/CHECKLIST.md).

## Observação importante

Ao rotacionar a `COLLECTOR_KEY` do cliente, todos os Edges daquele `CLIENT_ID` precisam ser atualizados.

