# Checklist de Campo (8 itens)

## Antes (3)

1) Confirmar dados do cliente
- `INGEST_API_URL` (SaaS)
- `CLIENT_ID`
- `COLLECTOR_KEY`
- Definir o `AGENT_ID` do local (ex: `LOCAL_A`, `LOCAL_B`, `LOCAL_C`)

2) Validar cenário de rede
- Se for corporativo (proxy/bloqueios): leve `OfflineBundle` com `wheelhouse/`.

3) Garantir acesso administrativo
- Você precisa de permissão de Administrador local (UAC).

## Durante (3)

4) Rodar o instalador como Administrador
- Online: `02-Instalar-Edge-Online.ps1`
- Offline: `03-Instalar-Edge-Offline.ps1 -OfflineBundle ...`

5) Informar `COLLECTOR_KEY` corretamente
- Sem “default global”. Chave é por cliente.

6) Confirmar que os serviços subiram
- `ETI_SENTINEL_MEDIAMTX`
- `ETI_SENTINEL_EDGE_AGENT`

## Depois (2)

7) Validar saúde local
- Abrir `http://127.0.0.1:8808/api/status`

8) Validar saúde na nuvem
- Painel mostra os devices do cliente online
- Teste: reiniciar o PC e confirmar que volta sozinho

