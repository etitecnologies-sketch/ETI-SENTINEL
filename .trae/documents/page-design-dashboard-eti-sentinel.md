# Page Design — Dashboard ETI SENTINEL (Desktop-first)

## 1) Diretrizes globais (identidade ETI SENTINEL)

### Layout (sistema e lógica)

* Estrutura base em **CSS Grid** (container principal) + **Flexbox** (alinhamentos internos).

* Duas colunas no desktop:

  * Coluna 1 (fixa): **Sidebar**.

  * Coluna 2 (flexível): **Conteúdo** com scroll vertical.

* Espaçamento por escala (ex.: 4/8/12/16/24/32px) e alinhamento consistente em grids.

### Meta information (SEO/Compartilhamento)

* Title: `ETI SENTINEL — Dashboard`

* Description: `Painel ETI SENTINEL com KPIs, gráficos e tabelas para monitoramento.`

* Open Graph:

  * og:title: `ETI SENTINEL — Dashboard`

  * og:description: `KPIs, gráficos e tabelas em um painel de monitoramento.`

  * og:type: `website`

### Global styles (design tokens sugeridos)

* Tema: **dark-first** (com bom contraste e legibilidade).

* Cores (tokens):

  * Background: `--bg-0` (fundo app), `--bg-1` (cards), `--bg-2` (hover/realce sutil)

  * Texto: `--text-0` (principal), `--text-1` (secundário)

  * Borda/Divisor: `--stroke-0`

  * Accent ETI SENTINEL: `--accent-0` (verde/teal característico), `--accent-1` (hover)

  * Status: `--success`, `--warning`, `--danger`, `--info`

* Tipografia:

  * Base: 14–16px

  * Títulos de seção: 16–18px (semi-bold)

  * KPI value: 24–32px (bold)

* Componentes:

  * Botões: raio 8px; estado hover com leve aumento de contraste; foco com outline visível.

  * Links/Itens de menu: estado ativo com barra/realce no accent.

  * Cards: borda sutil + sombra suave; padding 16–20px.

### Responsividade (desktop-first)

* Desktop (>= 1200px): sidebar fixa + conteúdo em grid (KPIs em 4 colunas quando couber).

* Tablet (>= 768px e < 1200px): KPIs em 2 colunas; gráficos empilham quando necessário.

* Mobile (< 768px): sidebar vira drawer/colapsável; KPIs em 1 coluna; tabelas com scroll horizontal.

***

## 2) Página: Dashboard

### Objetivo

Concentrar visão geral do estado do sistema por KPIs, análises por gráficos e detalhes operacionais em tabelas.

### Page structure (composição)

* Estrutura geral:

  1. **App Shell** (Sidebar + Top bar + Content).
  2. Conteúdo em seções empilhadas:

     * Linha 1: KPIs (cards)

     * Linha 2: Gráficos (grid)

     * Linha 3: Tabelas (stack)

### Seções & componentes

#### A) Sidebar fixa (navegação)

* Posição: fixa à esquerda; altura 100vh.

* Conteúdo:

  * **Brand/Logo** ETI SENTINEL (topo)

  * Itens de menu (lista vertical)

  * Rodapé opcional: versão/ambiente (se aplicável)

* Interações:

  * Item ativo destacado (accent + fundo `--bg-2`).

  * Hover com aumento de contraste.

#### B) Top bar (cabeçalho)

* Layout: flex horizontal (esquerda: título; direita: ações).

* Elementos:

  * Título: “Dashboard”

  * Subtítulo/contexto: “Visão geral” / período atual (quando houver)

  * Ação primária: “Atualizar” (ícone + texto)

* Comportamento:

  * Pode ser sticky no topo do conteúdo para manter contexto durante scroll (opcional).

#### C) Cards KPI (linha de resumo)

* Layout: grid responsivo (4 colunas no desktop, 2 tablet, 1 mobile).

* Cada card inclui:

  * Rótulo (texto secundário)

  * Valor (destaque tipográfico)

  * Indicador de variação/estado (badge/ícone) quando aplicável

* Estados:

  * Loading: skeleton do card

  * Empty: “Sem dados”

  * Error: mensagem curta + ação “Tentar novamente”

#### D) Seção de gráficos

* Layout: grid 2 colunas no desktop (ex.: 8/4 ou 6/6), empilhando no mobile.

* Cada bloco de gráfico:

  * Header do card: título + legenda/ajuda curta (quando necessário)

  * Corpo: área do gráfico com padding e limites claros

* Boas práticas visuais:

  * Linhas de grade discretas

  * Cores consistentes com tokens (accent para série principal)

* Estados:

  * Loading/Empty/Error padronizados como nos KPIs.

#### E) Seção de tabelas

* Layout: cards empilhados (uma tabela por card) ou 2 colunas se houver espaço.

* Elementos da tabela:

  * Cabeçalho com título

  * Tabela com colunas essenciais

  * Ordenação básica por colunas (indicador visual de ordenação)

* Usabilidade:

  * Cabeçalho pode ser sticky dentro do card quando houver muita rolagem

  * Mobile: scroll horizontal + truncamento com tooltip quando aplicável

* Estados:

  * Loading/Empty/Error padronizados.

#### F) Feedback e acessibilidade

* Feedback:

  * Toast/banner discreto para erros globais (quando necessário)

  * Indicadores de carregamento sem “pular” layout (skeleton)

* Acessibilidade:

  * Contraste mínimo adequado em tema escuro

  * Foco visível em navegação por teclado

  * Labels e títulos claros em cards/gráficos/tabelas

### Animações/transições (sutis)

* Hover de cards: transição 120–180ms (background/borda/sombra leve).

* Troca de estados (loading → conteúdo): fade curto para reduzir “flash”.

