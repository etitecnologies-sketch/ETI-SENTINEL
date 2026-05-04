# Especificação de Design (Desktop-first) — Dashboard ETI (inspirado em UniFi) + Topologia

## Estilo global (todos os pages)
**Layout**: grid 12 colunas (desktop), sidebar fixa + header fixo; conteúdo com cards em CSS Grid; interações com Drawer/Modal. Breakpoints: ≥1280 (desktop), 1024–1279 (laptop), ≤1023 (stack).

**Meta**:
- Title base: "ETI Sentinel" + sufixo da página
- Description: "Monitoramento de rede e CFTV em tempo real" (ajustar por página)
- OG: title/description + screenshot do dashboard

**Tokens (identidade ETI)**:
- Background: #0B1220 (base), surface: #0F1B2D, card: #12233A
- Texto: #E6EDF7 (primário), #9FB0C7 (secundário)
- Acentos: ETI Blue #2F7AF8, ETI Cyan #21D4FD, Success #2FD07A, Warning #F6C343, Critical #FF4D4F
- Tipografia: Inter/Roboto; escala 12/14/16/20/24
- Espaçamento: 4/8/12/16/24/32; padding padrão de card: 16; gap de grids: 16–24
- Raios: 10 (cards), 8 (inputs/botões); sombras: 1 nível (sutil) para separar card do fundo
- Botões: primário (blue), secundário (surface + borda), danger (critical). Hover: +8% brilho; Disabled: 40% opacidade; Focus: outline visível (2px)
- Badges de status: Online (success), Offline (critical), Alerta (warning), Unknown (cinza)

**Componentes compartilhados**:
- Sidebar: logo ETI, itens (Dashboard, Topologia), seletor de site (dropdown), estado ativo.
- Header: breadcrumbs (opcional), busca global (nome/IP/MAC), “Última atualização”, botão "Atualizar".
- Drawer de detalhes (direita): abas (Visão geral, Métricas, Portas/Links, Eventos).
- Modal player CFTV: player + status do stream + ações (abrir em nova aba, copiar URL quando permitido).
- Estados padrão (para cards, gráficos, tabelas e drawer):
  - Loading: skeleton (sem mudar layout)
  - Empty: mensagem curta + dica de filtro (quando aplicável)
  - Error: erro curto + ação "Tentar novamente"; detalhes somente em tooltip/expand

## Página: Login (/login)
**Meta**: Title "ETI Sentinel — Login"; OG simples.
**Estrutura**: centralização (Flex), card único.
**Seções**:
1. Card Login
   - Campos: e-mail, senha; checkbox "Manter conectado".
   - Botão primário "Entrar".
   - Estados: loading, erro (toast + inline), sucesso (redirect).
2. Seletor de site (condicional)
   - Se usuário possuir múltiplos sites: dropdown pós-login (ou tela intermediária simples).

**Comportamento dos botões**:
- Entrar: valida campos → desabilita durante request → mostra erro amigável.
- Sair (no app): encerra sessão e redireciona ao /login.

## Página: Dashboard (/dashboard)
**Page Structure**: coluna única com seções empilhadas; grids de cards.
**Seções & componentes**:
1. KPIs (4–6 cards)
   - Dados: devices online/offline/alerta; câmeras online/offline; tráfego up/down; latência média; alertas abertos.
   - Interação: clicar no KPI aplica filtro global (ex.: “somente offline”).
2. Saúde por categoria
   - Gráfico simples (donut/stacked bar) por tipo e severidade.
   - Tooltip: contagens e %.
3. Ativos críticos (tabela compacta)
   - Colunas: Nome, Tipo, Status, IP, Último visto, Ação.
   - Ação: "Ver na topologia".
4. CFTV resumo (grid de câmeras)
   - Card: nome, status, localização; snapshot (se disponível).
   - Ações: "Abrir ao vivo" e "Ver na topologia".
5. Eventos/Alertas recentes (timeline)
   - Itens: severidade, mensagem, origem, hora.
   - Ação: "Reconhecer" (ack) quando permitido.

**Comportamento dos botões**:
- Atualizar (header): refaz queries (KPIs, eventos, status); atualiza “Última atualização”.
- Ver na topologia: navega para /topologia com foco no item (highlight + zoom).
- Abrir ao vivo: abre Modal player; se indisponível, exibe fallback com snapshot + motivo.
- Reconhecer: marca evento como acknowledged; item muda estilo (cinza) e some do filtro “abertos”.

## Página: Topologia (/topologia)
**Page Structure**: layout 2 colunas (canvas 70% / painel 30%); em telas menores, painel vira drawer.

**Seções & componentes**:
1. Toolbar (topo do canvas)
   - Busca; filtros (Tipo, Status, Local); toggle "Somente problema"; botões (Auto-organizar, Centralizar, Zoom +/−).
2. Canvas de topologia
   - Nós: ícone por tipo; badge de status; label (nome) + sublabel (IP).
   - Links: espessura por velocidade (quando disponível); cor por status.
   - Interações: hover destaca conexões; clique seleciona e abre Drawer; arrastar nó fixa posição; duplo clique centraliza no item; multi-select opcional (shift) para comparação simples.
   - Performance/escala: limitar sombras no canvas; reduzir labels quando zoom-out; evitar re-render completo ao abrir drawer.
   - Estado vazio: quando não houver dados do site, mostrar mensagem central + botão "Atualizar".
3. Drawer de detalhes (seleção)
   - Cabeçalho: nome, tipo, status, tags (site/local).
   - Conteúdo (abas):
     - Visão geral: IP/MAC, uptime (se houver), última vez visto.
     - Métricas: tráfego, CPU/RAM, latência (sparklines).
     - Portas/Links: lista de portas com status/velocidade e link remoto.
     - Eventos: últimos eventos do item.
4. Modo CFTV (quando item=câmera)
   - Player ao vivo embutido no Drawer (ou botão para Modal).
   - Dados: status do stream, bitrate, FPS (se disponível).

**Comportamento dos botões (Topologia)**:
- Auto-organizar: aplica layout automático e mantém itens fixos após arraste.
- Centralizar: enquadra todos os nós visíveis.
- Zoom +/−: ajusta escala mantendo ponto central.
- Copiar IP/MAC: copia para clipboard + toast.
- Localizar (LED): envia comando; mostra estado “executando” e resultado (sucesso/erro).
- Reiniciar (Admin): confirma em modal → executa → marca device como “reiniciando” até novo last_seen.
- Abrir câmera ao vivo: abre Modal player; se falhar, exibe diagnóstico e alternativa (snapshot).
