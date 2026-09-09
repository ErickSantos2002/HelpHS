# Checkpoint 3 — as três telas da §25, sobre os primitivos

**Fechado em 08/09/2026, pelo portão de evidência.**

O operador definiu o portão em três pernas, e este documento é o que passa por
elas: **catraca zero**, **fichas da §29** e **capturas pela galeria DEV com a
API interceptada**.

---

## 1. Catraca zero

As quatro telas da Fase 11 **não aparecem mais na catraca de contraste**, em
nenhuma das duas listas.

```
$ node scripts/varredura-contraste.mjs --catraca
catraca: 39 par(es) abaixo de 4,5:1, linha de base 39
         25 cor(es) cheia(s) de significado como texto, linha de base 25
  ok - em dia.

ClientDashboard · TicketFormPage · TicketListPage · TicketDetailPage
  zero ocorrências
```

Os 39 restantes são de telas que ainda não foram migradas. A catraca desceu de
**49** (antes da Fase 11) para **39**, e as cheias de **28** para **25**.

### Chegar a zero exigiu consertar três coisas, e as três eram minhas

| tela | o que era | quanto dava |
|---|---|---:|
| `TicketDetailPage` | `text-conteudo-faint` sobre `bg-surface-elevated` | 2,34 no claro |
| `TicketFormPage` | `bg-primary` com `text-on-primary` | 3,83 no claro |
| `TicketListPage` | `hover:text-danger` — cheia semântica como texto | — |

O primeiro nasceu da minha varredura de `slate`: mapeei `text-slate-600` para
`text-conteudo-faint` sem medir o par resultante contra a superfície elevada.

O segundo é a **mesma família** do `bg-success text-on-success` que a catraca
pegou duas telas antes: o par certo com o fundo errado. `--text-on-primary` é o
par do degrau de **ação**, e o comentário do `tailwind.config.js` diz isso com
todas as letras — eu li o nome e não o comentário.

---

## 2. Fichas da §29

Uma por tela, no `fase-11/RELATORIO.md`, com a contagem do que resta à mão.

| tela | controles à mão | SVG solto | cor crua |
|---|---:|---:|---:|
| `ClientDashboard` | 2 (ambos em comentário) | 0 | 0 |
| `TicketFormPage` | 2 | 0 | 0 |
| `TicketListPage` | 3 | 0 | 0 |
| `TicketDetailPage` | 18 | 0 | 0 |

**Todos os controles restantes são ação, e nenhum está sem nome acessível** —
auditados um a um. A regra manda **contar, não julgar**: número maior que zero
significa que alguém tem de olhar, não que há trabalho pendente.

### O que as quatro telas ganharam

| | |
|---|---|
| primitivos novos | `RadioCards`, `KpiCard` |
| fontes únicas | `lib/prioridade.ts`, `lib/status.ts`, `lib/categoria.ts` |
| mapas divergentes eliminados | **dez** de prioridade, **três** de status, **três** de categoria |
| ícones | 53 `<svg>` soltos viraram `Icon`; 21 subiram ao pacote na **E20** |
| emendas que nasceram aqui | E17, E18, E19, E20 |

---

## 3. Capturas

`scripts/capturar-telas.mjs` — **dez fotos**, quatro telas nos dois temas mais
o quadro largo. (O script chamava-se `capturar-fase11.mjs`; ao cobrir também as
18 telas da Fase 16 o nome deixou de descrevê-lo. As fotos da Fase 11 seguem
onde estavam: cada tela declara a sua fase, e a saída é a pasta daquela fase.
Para refazer só estas dez: `node scripts/capturar-telas.mjs 11/`.)

```
✔ helphs-painel-{claro,escuro}-1366.png
✔ helphs-lista-{claro,escuro}-1366.png
✔ helphs-formulario-{claro,escuro}-1366.png
✔ helphs-detalhe-{claro,escuro}-1366.png
✔ helphs-lista-larga-{claro,escuro}-2100.png

Requisições barradas de propósito (0):
✔ Nenhuma requisição escapou. Nada saiu para a rede.
```

**Zero chamadas sem resposta prevista**, e zero fugas. O `backend/.env` deste
ambiente aponta para o banco de produção; a sonda não "evita" a rede, ela a
impede por lista de permissão.

### Ela não contorna a autenticação

Semeia uma sessão falsa e responde ao `/users/me`. As telas são **as de
verdade**, com as rotas de verdade e o `AuthGuard` de verdade — só os dados é
que não existem. Uma galeria que renderizasse cópias das telas provaria coisa
nenhuma sobre as telas.

### Três travas antes de cada disparo, e cada uma bloqueia sozinha

| trava | o que responde |
|---|---|
| produto | `data-app="helphs"` no `<html>`, **falha fechada** |
| pixel | a cor do viewport contra o `--bg-base` lido do `colors.css` **em disco** |
| conteúdo | um seletor que só existe na tela pedida |

A do pixel é provada isolada em `e2e/sonda-captura.spec.ts` — sete casos, sem
marcador, sem classe `dark`, sem canário.

### O papel varia por tela, e não é detalhe

A rota `/` escolhe o painel **pelo papel**, e o painel da Fase 11 é o do
**cliente**. Capturar como admin fotografaria o `AdminDashboard`, que tem a
rosca e a barra empilhada — travadas até a E18 chegar ao código.

### Três defeitos da própria sonda, achados fotografando

1. **O recuo respondia `{}`** à chamada não prevista, e `data.items` indefinido
   derrubava a árvore inteira.
2. **A ordem dos padrões:** `/tickets` sem âncora casava com
   `/tickets/t-1/messages`, e a tela de detalhe recebia a **lista de chamados**
   como se fossem mensagens.
3. **`/tags` e `/users/technicians` devolvem `data.items`**, e eu dava array.

Os três apareciam como *"a tela não montou"*, apontando para o seletor em vez da
causa. A mensagem passou a carregar **o que a tela mostra**, **as chamadas sem
resposta prevista** e **os erros de JavaScript** — sem o terceiro, um `<body>`
vazio não diz nada.

---

## O que a evidência mostra, e vale olhar

**Os dois "Aguardando" compartilham o âmbar.** É a §16, e está na captura larga:
`awaiting_technical` e `awaiting_client` são o mesmo estado para quem olha o
quadro, e o que os separa está no título da coluna. A medição da E18 confirmou
que nem daria para mantê-los distintos com rigor — dois degraus de `warning` que
passem 3:1 nas três superfícies do claro ficam a **12,2** de ΔE, contra um piso
de 20.

**A prioridade fala uma língua só.** "Crítica, Alta, Média, Baixa" em todas as
quatro telas, no feminino que a **E17** fixou. Eram dez mapas.

---

## O que NÃO entra neste checkpoint

**A rosca e a barra empilhada do `AdminDashboard`** seguem travadas até a E18
chegar ao código. A tentativa anterior de migrá-las com tokens de interface
quebrou o gráfico, e o `colors.css` do pacote registra isso — a E18 é a medição
que explica por quê.

**A escala CSAT** foi tokenizada mas não ganhou as três faixas decididas. Tem
Etapa marcada na Fase 16.

**O `cancelled` sem coluna** é defeito de produto, não de sistema de design, e
está em `COMPARTILHADO/achados-helphs-frontend.md`.
