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

Observação: para offline “real” (sem internet), o bundle precisa incluir:
- `wheelhouse/` (dependências Python)
- `repo/main.zip` (snapshot do repositório)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.03-Instalar-Edge-Offline.ps1 -OfflineBundle "D:\ETI-BUNDLE.zip"
```

## Update (atualização de Edge já instalado)

### Update online

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.02-Instalar-Edge-Online.ps1 -Update
```

### Update offline

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.03-Instalar-Edge-Offline.ps1 -OfflineBundle "D:\ETI-BUNDLE.zip" -Update
```

### Observação

- Rotação de `COLLECTOR_KEY` não é “automática” no update: você precisa atualizar o `.env` de cada Edge.

## Atualizar o kit (pendrive)

Para levar o kit sempre atualizado em campo, rode no seu PC (dentro do repositório):

```powershell
.00-Atualizar-Kit.ps1
```

Isso faz `git pull` e gera uma pasta `KIT-PENDRIVE` pronta para copiar para o pendrive.

Gerar com bundle offline junto (recomendado para clientes corporativos):

```powershell
.00-Atualizar-Kit.ps1 -WithOfflineBundle
```

Gerar também ZIP:

```powershell
.00-Atualizar-Kit.ps1 -WithOfflineBundle -Zip
```

## Checklist

Use o checklist rápido em [CHECKLIST.md](./instalador-campo/CHECKLIST.md).

## Observação importante

Ao rotacionar a `COLLECTOR_KEY` do cliente, todos os Edges daquele `CLIENT_ID` precisam ser atualizados.
