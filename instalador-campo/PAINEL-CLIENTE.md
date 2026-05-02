# Painel — Criar cliente e pegar credenciais do Edge

## Criar cliente

1) Login como `superadmin`
2) Menu `Clientes`
3) `+ Novo Cliente` → preencher → `Salvar Cliente`

Ao salvar, o painel gera e mostra uma `COLLECTOR_KEY` (uma vez) para você copiar.

## Rotacionar COLLECTOR_KEY

1) `Clientes` → editar cliente
2) Aba `🔑 Edge`
3) Botão `Gerar/Rotacionar COLLECTOR_KEY`

Observação: após rotacionar, os Edges antigos daquele cliente precisam ser atualizados.

## Config padrão de Edge (copiar e ajustar)

Use como base no `.env` do Edge:

```
INGEST_API_URL=<seu-saas>
CLIENT_ID=<id-do-cliente>
COLLECTOR_KEY=<chave-do-cliente>
AGENT_ID=LOCAL_A
```

