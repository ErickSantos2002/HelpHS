# Fase 16 — escopo aberto

O que foi **decidido** e ainda **não implementado**, com a Etapa em que sai.
Este arquivo existe porque três coisas foram decididas em telas que não têm
Etapa nas 2–7, e sem um lugar para elas a decisão viraria conhecimento de quem
estava na sala.

---

## Etapa 16.1 — `ReportsPage`

A tela com mais cor de série do sistema, e a única com gráfico que ficou de fora
das Etapas 2–7. **Nada aqui é decisão nova**: tudo já está decidido, só falta
sair.

### O que já saiu

Prioridade. As quatro cores passaram a vir de `lib/prioridade.ts`, o selo à mão
virou `PriorityBadge`, e o mapa que pintava "baixa" com o **verde de sucesso**
foi embora. Feito em `cc77257`, fora de Etapa, porque pintar prioridade baixa de
verde afirma que ela é uma coisa boa.

### O que falta

**A escala de satisfação (CSAT).** Decisão registrada no `DECISOES.md` em
08/09/2026 e não implementada:

> 1–4 `danger`, 5–7 `warning`, 8–10 `success`, e **o número sempre no rótulo**.

Sai a rampa de dez cores cravadas (`#dc2626` … `#22c55e`), que falha o critério
de separação por construção: degraus vizinhos são próximos de propósito, e o
eixo vermelho-verde é o que colapsa em protanopia e deuteranopia.

As três faixas consomem os `--fill-*` da **E19**, quando ela estiver gravada.

**Os gráficos categóricos.** Passam a `--chart-*`:

| gráfico | onde |
|---|---|
| Tickets por categoria | `ReportsPage.tsx` |
| Tickets por produto | `ReportsPage.tsx` |
| Tickets por hora do dia | `ReportsPage.tsx` |
| Volume por dia da semana | `ReportsPage.tsx` |

**Os gráficos de status.** Passam à tabela fixa da **E18**, com legenda
obrigatória:

| gráfico | onde |
|---|---|
| Distribuição por técnico (séries são status) | `ReportsPage.tsx` |

**As séries temporais.** Regra do operador: *série temporal da mesma natureza
usa uma cor só quando for a mesma medida.* Hoje são **cinco gráficos da mesma
natureza em quatro cores diferentes** — `#0ea5e9` no `AdminDashboard` e no
`TechnicianDashboard`, `#6366f1`, `#22c55e` e `#f59e0b` no `ReportsPage`.

**O cromo dos gráficos.** Eixo, grade e dica ainda saem de hexadecimal cravado
escolhido por tema à mão (`#132238`, `#1E3A5F`, `#475569`, `#94a3b8`,
`#f1f5f9`…), em três arquivos. Não é cor de série, mas é cor fora do sistema.

---

## Etapa 16.2 — o resto dos 15 gráficos

`AdminDashboard` e `TechnicianDashboard` têm Etapa própria (6 e 5). O que sai
lá, pela mesma regra: categórico em `--chart-*`, status pela E18, prioridade
pelo módulo, temporal em uma cor só.

Fica registrado aqui porque a **rosca e a barra empilhada do `AdminDashboard`
só migram depois da E18 gravada** — a tentativa anterior de migrá-las com
tokens de interface quebrou o gráfico, e o `colors.css` do pacote registra isso.
A E18 é a medição que explica por quê.

---

## Etapa 16.3 — o que depende do pacote

| item | trava |
|---|---|
| `--fill-*` deixarem de ser locais | E19 gravada e recopiada |
| `--chart-7` existir | E18 gravada e recopiada |
| status → slot | E18 gravada |

Enquanto a E19 não é gravada, o `--fill-warning` vive em
`frontend/src/index.css`, declarado sobre degraus do pacote e **sem valor
cravado** — então ele acompanha a rampa sozinho e não precisa de catraca. Está
marcado no próprio arquivo como candidato a emenda.

---

## O que NÃO entra na Fase 16

**Os três indicadores do `ClientDashboard`** que são contados no cliente sobre
os 500 itens trazidos. Passando de 500 chamados a tela mostra três números que
não fecham, sem sinal de truncamento. É defeito de **serviço**, não de sistema
de design, e está registrado no próprio arquivo.
