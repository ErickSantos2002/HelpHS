# Checkpoint 4 — as vinte e duas telas da Fase 16, sobre o sistema

**Fechado em 09/09/2026, pelo portão de evidência.**

O portão é o mesmo das outras três vezes, em três pernas: **catraca**, **fichas
da §29** e **capturas com a API interceptada**. O que mudou nesta rodada não foi
o portão — foi a régua da terceira perna, que passou a ter tolerância declarada
e controle negativo.

---

## 1. Catraca

```
$ node scripts/varredura-contraste.mjs --catraca
catraca: 2 par(es) abaixo de 4,5:1, linha de base 2
         1 cor(es) cheia(s) de significado como texto, linha de base 1
  ok - em dia.
```

| medida | antes da Fase 11 | fim do Checkpoint 3 | agora |
|---|---:|---:|---:|
| pares abaixo de 4,5:1 | 49 | 39 | **2** |
| cores cheias como texto | 28 | 25 | **1** |

Os dois lugares que restam estão no `QuickReplyPicker`, componente do chat que a
fase não alcançou, e a única cor cheia é do `ForbiddenPage`. **Nenhum é resíduo
de tela migrada** — as vinte e duas telas da fase não aparecem em nenhuma das
duas listas.

### A catraca contava a explicação do conserto como defeito

Ao fechar a fase, três das quatro cores cheias restantes estavam **em
comentário**: o próprio texto que cada tela migrada ganhou dizendo qual cor saiu
dali. A régua media a explicação como se fosse o problema.

Isso é pior que um número errado — cria pressão para **não** explicar o que foi
removido, que é o contrário do que esses comentários existem para fazer. O corte
passou a ser um varredor de caractere que rastreia string, porque a classe mora
dentro de uma string (`className="text-danger"`), e um corte que apagasse
strings mediria zero em tudo e pareceria consertado. Seis casos de prova, e o
quinto é esse controle negativo.

---

## 2. Fichas da §29

**22 fichas**, uma por tela, todas com as travessias da §29 percorridas:

`AdminDashboard` · `AuditLogsPage` · `CalendarPage` · `ChangelogModal` ·
`ChatPanel` · `EquipmentPage` · `GroupsPage` · `KBArticlePage` · `KBFormPage` ·
`KBListPage` · `NotificationsPage` · `OnboardingPage` · `ProductsPage` ·
`ProfilePage` · `QuickRepliesPage` · `ReportsPage` · `SettingsPage` · `Sidebar` ·
`SlaConfigPage` · `TechnicianDashboard` · `Topbar` · `UsersPage`

Suíte ao fechar: **87 arquivos, 1187 casos, todos passando.**

---

## 3. Capturas — 50 fotos, e a régua que decide se duas execuções concordam

25 entradas, 50 fotos (claro e escuro), **nenhuma requisição escapou para a
rede** — a interceptação é por lista de permissão, e chamada sem resposta
prevista é erro, não silêncio.

| fase | entradas | fotos |
|---|---:|---:|
| 11 | 5 | 10 |
| 16 | 20 | 40 |

`Sidebar` e `Topbar` não têm foto própria porque aparecem **dentro das 50**;
`ChatPanel` aparece dentro do `detalhe`. O `KBFormPage` tem duas rotas
(`kb-novo` e `kb-editar`) e por isso duas entradas.

### A régua, e por que ela tem três partes

Byte a byte é forte demais e diz pouco: a mesma tela rasterizada duas vezes
difere por antialias, com centenas de pixels variando de 3 a 6 unidades sem que
nada tenha mudado. A régua declarada pelo operador:

1. nenhum pixel difere mais que **8 unidades** em canal nenhum;
2. a área afetada fica em **~1% ou menos**;
3. e a diferença tem de estar **espalhada**.

A terceira fecha o buraco das duas primeiras. Um elemento pequeno que aparece —
um ponto de série, um selo, um cursor — cabe em muito menos de 1% da tela e, se
a cor dele for parecida com o fundo, varia menos de 8 unidades. **Passaria nas
duas primeiras sendo a tela mudando.** Mede-se por densidade dentro da caixa que
contém as diferenças, e os dois casos reais que produziram a régua estão
separados por duas ordens de grandeza:

| medido em | pixels | caixa | densidade | é |
|---|---:|---|---:|---|
| `relatorios` | 458 | 978×103 | 0,5% | antialias |
| `painel-tecnico` | 2.948 | 28×138 | **76,2%** | **elemento** |

### O resultado, em número e não em adjetivo

Duas execuções seguidas, com a árvore parada:

```
50/50 dentro da tolerância (<=8 de variação, <=1% de área, espalhada).
```

E a seção "dentro da tolerância, mas com diferença medida" **saiu vazia**: as
cinquenta fecharam com **0 pixel de diferença**. A régua não precisou ser
exercida hoje, porque o conserto foi feito na origem — mas ela fica, e o número
que este documento reporta é o que o comparador mediu, não um "idênticas".

O comparador tem controle negativo próprio: conta os nomes dos **dois lados** e
separa `mudou`, `nova` e `sumiu`. Num contador só, "nenhuma diferença" e "nenhum
arquivo" são indistinguíveis — e nesta mesma sessão dois diagnósticos meus
relataram verde comparando nada com nada.

---

## As dez fotos da Fase 11, e por que mudaram — duas causas, em dois commits

O operador pediu a explicação, e ela se separa limpa porque cada causa está num
commit diferente.

**Causa 1 — as listas deixaram de ser vazias** (`559076d`). O mock antigo devolvia
lista vazia em várias telas, e a sonda fotografava estado de exceção achando que
era a tela. As dez foram refotografadas ali, todas.

**Causa 2 — a data deixou de ser o relógio** (este commit). O `SlaChip` lê
`Date.now()`, e o chip que ele desenha muda conforme as horas passam.
**Evidência que muda entre execuções não é evidência.** Tudo passou a derivar de
uma data-base cravada.

E a segunda causa deixou uma assinatura que confirma o diagnóstico:

| fotos | mudou? | por quê |
|---|---|---|
| `lista`, `lista-larga`, `detalhe` (×2 temas) — **6** | sim | exibem `SlaChip` |
| `formulario`, `painel` (×2 temas) — **4** | **não** | não mostram o relógio |

Se a causa fosse outra — o portão do gráfico, por exemplo — o `painel`, que tem
gráfico, teria mudado. Ele não mudou.

---

## Duas lacunas conhecidas, ditas em voz alta

**O `ChangelogModal` não tem foto.** Ele exige um passo de clique que a sonda não
dá. Se um dia valer, é gatilho por URL — decisão do operador, registrada.

**A trava do gráfico não distingue "vazio por desenho" de "quebrado".** A trava
espera as formas do Recharts assentarem antes de fotografar, e passou a ler
`path`, `circle`, `rect` e `line` — antes lia só `path`, e as séries desenham
`<circle>`, então ela dizia "assentou" com os pontos ainda entrando.

A primeira versão desse conserto lançava exceção quando havia contêiner e
nenhuma forma dentro dele — e derrubou o `painel-tecnico`, que capturava bem.
**Errei o mesmo erro que a trava existe para consertar, no sentido contrário**:
antes eu colapsava dois estados em "seguir", e passei a colapsá-los em "falhar".
Um estado sem sinal próprio não vira erro só porque a alternativa incomoda.

Separá-los de verdade exige um marcador na tela de vazio, que é mudança de
aplicação e não de sonda. Enquanto não houver, a espera é limitada e o silêncio
é aceito.

---

## A lição do dia: mecanismo certo, conjunto com buraco

O mesmo defeito apareceu **quatro vezes**, em contextos sem relação nenhuma:

| onde | a régua estava certa em | e o conjunto estava incompleto em |
|---|---|---|
| tabela de hashes do pacote | comparar SHA256 | a **linha** do `colors.css`, parada por quatro emendas |
| `campos-aria` | as seis afirmações de cada caso | a **lista de implementadores** — o `Select` nunca entrou |
| catraca de contraste | medir par de cor | o **recorte do arquivo** — contava comentário |
| trava do gráfico | comparar duas leituras | a **lista de elementos** — lia `path`, ignorava `circle` |

É mais difícil de ver que uma régua errada, porque **tudo que está dentro do
conjunto passa**: não há falso negativo para investigar, não há alarme. O que
sobra é uma afirmação mais forte que a evidência.

A pergunta que o encontra: **sobre o que exatamente esta régua opera, e quem
decidiu esse conjunto?** Um conjunto nunca se audita sozinho.
