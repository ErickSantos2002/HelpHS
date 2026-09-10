# A base da Helô passa a ser a Base de Conhecimento

**Plano de 10/09/2026, implementado no mesmo dia.** As decisões tomadas e o
que a implementação encontrou estão na última seção; o texto abaixo é o
plano como foi proposto, com as recomendações que viraram código e as que
mudaram no caminho. Decisão do cliente em
10/09/2026, corrigindo a decisão 3 de 08/09 ("a fonte é a pasta de manuais").

A fonte da Helô deixa de ser arquivo em disco indexado por script e passa a ser
`kb_articles` com `status = published` — os mesmos artigos da barra lateral.
Artigo publicado depois alimenta a Helô **sem ninguém rodar nada**.

---

## O que muda, e o que não muda

Muda **de onde o texto vem**. Sobrevive tudo que custou caro:

| Sobrevive intacto | Onde |
|---|---|
| Serviço de embedding (ONNX, bge-m3, pooling, Dockerfile) | `servico_embedding/` |
| Cliente HTTP, teto de lote, falha silenciosa → `None` | `helo_embedding.py` |
| O turno dela: três blocos, motivos, teto de trocas, SAVEPOINT | `helo.py` |
| O prompt v5, `le_resposta`, `monta_cadastro`, `monta_conversa` | `helo_prompt.py` |
| `NADA ENCONTRADO` literal, `K_TRECHOS`, **teto de 0,25** | `helo_base.py` |
| Corte por seção, detector largo + redator preciso, marcação de credencial | hoje em `scripts/ingere_manuais.py` |

Muda a **procedência** e, com ela, três regras.

---

## 1. O que aproveita, o que vira migration, o que morre

### Morre

**`helo_documents` morre.** Ele existia para responder "de que arquivo veio este
trecho e qual a versão dele". Agora o documento **é** o artigo, e a resposta
está em `kb_articles`.

**`helo_chunk_products` morre.** O vínculo trecho↔produto foi desenhado quando o
trecho era a única unidade que existia; agora quem carrega produto é o artigo,
por `kb_article_products`, que já existe e já é editado pela tela. Manter os
dois seria duas fontes de verdade para a mesma pergunta.

⚠️ **Preço da simplificação, declarado:** perde-se a granularidade de "esta
seção serve a dois aparelhos, o resto do documento só a um". Hoje ninguém usa
isso — os oito manuais casam um-para-um com produto. Se um dia fizer falta, o
caminho de volta é uma tabela de exceção por trecho, não desfazer isto.

**`doc_type` morre**, e com ele o filtro técnico/comercial. As cinco fichas
comerciais **não viram artigo** (decisão 3: têm preço, e publicá-las põe tabela
de preço na tela do cliente). Sem ficha comercial na base, não há o que separar.

**`scripts/ingere_manuais.py` morre na forma atual** — ele lê pasta, casa
produto por nome de arquivo e grava `helo_documents`. Vira duas coisas
separadas (§4).

### Vira migration

| Mudança | Forma |
|---|---|
| `kb_articles.helo_pode_ler` (bool, default `true`) | Aditiva — segura no boot |
| `helo_chunks.article_id` → FK `kb_articles(id)`, `ON DELETE CASCADE` | Coluna nova + `DROP` da antiga |
| `helo_chunks.document_id` sai | Destrutiva |
| `helo_documents`, `helo_chunk_products` saem | Destrutivas |
| `helo_indexacao(article_id PK, content_hash, indexado_em)` | Tabela nova (§3) |

⚠️ **Esta migration NÃO é aditiva como a `b8w9x0y1z2a3`**, e o comentário dela
precisa dizer isso. Ela derruba tabela e coluna. É segura mesmo assim porque
**todo o conteúdo é re-derivável**: os 74 trechos vêm de manuais que continuam
existindo, e a reindexação os refaz. Não é dado de cliente. A régua de "pode
rodar no boot" continua sendo sobre o QUE se faz — aqui, nada que precise de
privilégio que a aplicação não tem, nada que reescreva tabela grande, nenhum
backfill de dado histórico.

### Aproveita, mudando de lugar

`busca_trechos` continua com dois filtros obrigatórios, mas eles trocam de
tabela **e um deles inverte**:

```
hoje:   helo_chunk_products.product_id == ticket.product_id
        AND helo_documents.doc_type == 'tecnico'
        AND embedding IS NOT NULL
        AND distância <= 0,25

vira:   kb_articles.status == 'published'
        AND kb_articles.helo_pode_ler IS TRUE
        AND (artigo SEM produto vinculado  OR  vinculado ao produto do chamado)
        AND embedding IS NOT NULL
        AND distância <= 0,25
```

⚠️ **A inversão é a mudança mais perigosa deste plano, e é deliberada.** Hoje o
filtro de produto é a única coisa que impede o passo a passo do Phoebus de
chegar a quem tem um Titan na mão. Passando a valer "sem vínculo vale para
todos", um artigo genérico mal marcado alcança todos os aparelhos.

A justificativa é boa: no arquivo, vínculo ausente era **casamento falhado** —
erro, e por isso fatal. No artigo, vínculo ausente é **escolha de quem
escreveu**, e é o que o próprio modelo documenta ("trecho sem produto vinculado
vale para todos"). **Não replicar o zero fatal.**

O que isso exige em teste: o `test_chamado_de_titan_nunca_recebe_trecho_de_iblow`
continua valendo palavra por palavra, e entra um irmão — artigo sem vínculo
aparece nos dois chamados, e artigo vinculado ao Titan não aparece no do iBlow.

---

## 2. Como marcar artigo que a Helô não deve ler

Você pediu a análise, não a conclusão. As cinco formas que considerei:

### (a) Coluna booleana `helo_pode_ler`, default `true` — **recomendada**

Explícita, tipada, com default, visível no schema, na API e na tela. Erro
possível: esquecer de desmarcar, e aí o artigo entra — mas o erro é **visível**,
porque o campo está na tela ao lado do botão de publicar.

Custo: migration aditiva, campo no schema Pydantic, campo no formulário da KB
(front — outra árvore).

### (b) Convenção de tag — **rejeitada**

`kb_articles.tags` já existe e é `ARRAY(String)`. Custo zero de migration.

⚠️ **É texto livre.** `nao-helo`, `não-helo`, `naohelo` e `no-helo` são quatro
strings diferentes, e escolher a errada muda o comportamento **em silêncio** —
o artigo que alguém achou que tinha excluído continua alimentando as respostas.
É exatamente a classe de defeito que esta fase inteira vem eliminando: a marca
de escalada virou constante acoplada por teste, o `NADA ENCONTRADO` virou
literal com teste dos dois lados, nome de produto duplicado virou erro fatal.
Reintroduzi-la aqui, no campo que decide o que a IA lê, seria andar para trás.

### (c) Derivar de `category` — **rejeitada**

`category` é `TicketCategory` (hardware, software, geral). Não responde à
pergunta, e amarraria duas coisas que mudam por motivos diferentes.

### (d) Tabela de exclusão (`helo_artigos_excluidos`) — **rejeitada**

Default correto por construção (ausência = pode ler) e não toca `kb_articles`.
⚠️ Mas é **invisível para quem edita o artigo**: a pessoa publica e nada na tela
diz que a Helô vai passar a citar aquilo. O problema deste plano é justamente
gente não saber o que ganhou; uma solução invisível o agrava.

### (e) Coluna com default `false` (opt-in) — **a alternativa séria**

Mais segura: nada entra sem alguém dizer que sim. Elimina de vez o risco do §5.

⚠️ Contraria a decisão que motiva a mudança de fonte — "artigo publicado depois
alimenta a Helô sem ninguém rodar nada" — e reintroduz o passo manual que ela
quer eliminar. A base começaria vazia e ficaria vazia até alguém marcar artigo
por artigo.

**Recomendo (a), com uma ressalva que precisa da sua decisão:**

O default vale para o **futuro**. O que acontece com os artigos **que já
existem publicados** é outra pergunta, e não pode ser respondida por
`server_default` — corrigir linha existente em migration é proibido aqui
(`docs/decisoes-e-regras.md`). Se hoje já houver artigo publicado sobre
procedimento interno, ele vira fonte da Helô no instante do deploy.

Antes de decidir, um número que eu não tenho: **quantos artigos publicados
existem em produção hoje.** Se for zero, (a) é seguro e acabou. Se não for, a
saída é a mesma coisa em duas partes — coluna com default `true`, e um script
avulso que marca os pré-existentes como `false` para alguém revisar um a um.

---

## 3. Reingestão quando o artigo é publicado ou editado

Quatro opções, com o custo de cada uma.

### (A) Síncrona no request — descartada por você, e por um motivo melhor

O motivo não é latência. Um artigo de 18 trechos são 5 chamadas HTTP ao serviço
de embedding (lote de 4), IO puro — não é o caso dos 151 segundos, que era CPU
no event loop, e com IO o worker único atende outras requisições enquanto
espera.

O motivo é **acoplamento de falha**: com o serviço de embedding fora, o `PATCH`
do artigo falharia, e o suporte não conseguiria salvar texto por causa de uma
funcionalidade que é acessório. É a mesma regra que fez a Helô inteira rodar em
SAVEPOINT.

### (B) `asyncio.create_task` fire-and-forget

Precedente no repositório: `_classify_ticket_async`, em `tickets.py`.

- **Ganho:** instantâneo, zero infraestrutura nova.
- **Custo:** morre com o processo — deploy no meio da indexação deixa o artigo
  desatualizado **calado**. Sem retry, sem visibilidade, sem forma de saber que
  ficou para trás.

### (C) Varredura periódica por hash — **recomendada**

Precedente no repositório: `auto_close_loop`, subido no `lifespan`, com
intervalo configurável, `except` que não deixa o laço morrer e lock no Redis
para quando forem dois workers.

Cada rodada: um `SELECT` que compara `hash(kb_articles.content)` com
`helo_indexacao.content_hash` para os publicados com `helo_pode_ler`. O que
diferir (ou faltar) é reindexado; o que sumiu da lista tem os trechos apagados.

- **Ganho:** **auto-curativa.** Deploy no meio, serviço de embedding fora, erro
  de rede, artigo editado enquanto o worker estava caindo — a próxima rodada
  conserta. Sem tabela de fila, sem dead-letter, sem retry para escrever.
- **Custo:** latência até um intervalo (sugiro 5 minutos). O artigo publicado
  agora entra nas respostas dali a alguns minutos, não no mesmo segundo.

⚠️ **Por que hash e não `updated_at`:** `kb_articles.updated_at` tem
`onupdate=func.now()`, e `view_count`, `helpful` e `not_helpful` são
incrementados em rota de leitura. Cada visualização de artigo mexeria no
carimbo e dispararia reindexação de um texto que não mudou — pagando embedding
por clique. O hash olha o que interessa.

### (D) Outbox (tabela de fila com estado)

O mais robusto e o mais caro: tabela, worker, retry, dead-letter, e um estado a
mais para alguém entender quando algo trava. É o desenho certo para volume
alto; aqui são três artigos e um punhado de edições por semana.

**Recomendo (C) sozinha.** Se a latência de minutos incomodar, (B) entra
**junto** como atalho — dispara a indexação daquele artigo na hora, e a
varredura continua sendo a rede embaixo. O que não recomendo é (B) sozinha:
seria a única forma de a base ficar errada sem ninguém saber.

---

## 4. O import dos três manuais, e onde a redação entra

**Só as três técnicas viram artigo:** Phoebus, Titan, iBlow10 Pro.

Script avulso `scripts/importa_manuais_para_kb.py`, no molde do
`redefine_senha.py`: dry-run por padrão, `--aplicar` para gravar, e o mapa
manual↔produto **declarado no script**, não adivinhado por nome de arquivo. O
casamento por aproximação existia porque eram oito arquivos e ninguém queria
digitar; são três, e digitar é mais barato que uma heurística.

### A redação acontece AQUI, e é isto que muda tudo

Publicado quer dizer **visível para o cliente**. Se o manual do Phoebus virar
artigo publicado sem tratamento, as duas senhas de configuração avançada ficam
na tela da Base de Conhecimento — e toda a redação que construímos protege a
base vetorial, não a página.

Então o artigo **nasce já redigido**. O detector largo roda no import, com a
mesma fatalidade que ele tem hoje: detector disparou e o redator não redigiu →
aborta nomeando arquivo e linha. Falso positivo é barato e visível; falha muda
não é.

A marcação `exige_credencial_admin` continua existindo no trecho, para a Helô
dizer "esse passo precisa de credencial de administrador" em vez de ensinar o
caminho.

### O artigo nasce em `draft`, e isso é recomendação minha

Você não pediu, e é uma decisão sua.

O import cria os três como **rascunho**, e uma pessoa lê e publica. O passo
custa uma vez e é exatamente o passo em que alguém confirma, olhando, que as
senhas sumiram do texto que vai para o cliente. Publicar direto significa que a
primeira pessoa a ler o manual redigido é o cliente.

Como a publicação é o gatilho da indexação (§3), o fluxo fecha sozinho: publicou
→ a varredura seguinte indexa.

### Duas coisas que o import precisa e ainda não têm dono

- **Autor.** `kb_articles.author_id` é obrigatório. Argumento `--autor <email>`,
  e o script aborta se o e-mail não existir — nada de escolher um admin
  qualquer.
- **Slug.** A regra de slug único vive em `_slugify`/`_unique_slug` dentro do
  router. Mesma situação do gravador de histórico: o script não pode importar do
  router. Move para `app/utils/`, como o `registra_historico` foi.

---

## 5. A consequência que precisa ir para o Changelog

> **Publicar artigo na Base de Conhecimento passa a mudar o que a Helô diz para
> o cliente.** Até aqui, publicar artigo colocava um texto na barra lateral para
> quem fosse procurar. A partir desta versão, o mesmo botão alimenta as respostas
> que a IA dá no chat — citando o artigo como fonte, para clientes que nunca
> abriram a Base de Conhecimento. O suporte não tinha esse poder e não foi
> avisado de que passou a ter.
>
> O que isso significa na prática, para quem escreve artigo:
> - Passo a passo errado num artigo publicado vira procedimento errado ditado
>   ao cliente, **com a fonte citada** — o que faz parecer conferido.
> - **Artigo sem produto vinculado vale para TODOS os aparelhos.** Um
>   procedimento que só serve ao Phoebus, publicado sem vínculo, alcança quem
>   tem Titan.
> - Para deixar um artigo fora da IA e mantê-lo na barra lateral, existe a
>   marcação própria no formulário — não é tag, e não é despublicar.

Isto precisa de mais do que uma linha no Changelog técnico: é aviso para quem
opera. Sugiro (e depende de você, e da árvore do front) um texto curto na
própria tela de edição do artigo, ao lado da marcação.

---

## O que eu preciso decidido antes de escrever código

1. **Marcação:** confirma a coluna `helo_pode_ler` com default `true`?
2. **Artigos já publicados hoje:** quantos são, e o que fazer com eles — entram
   na Helô no deploy, ou nascem marcados como "não ler" para revisão?
3. **Reingestão:** (C) sozinha, ou (C) + (B)?
4. **Os três manuais nascem `draft`** para alguém publicar, ou já publicados?
5. **`helo_documents` e `helo_chunk_products` podem morrer**, aceitando a perda
   de granularidade trecho↔produto?

## O que este plano não resolve

- **A hipótese B** (o trecho genérico dominando a busca) continua valendo, e o
  gatilho dela — manual técnico para mais de três produtos — fica mais fácil de
  atingir agora, porque publicar artigo é barato.
- **A medição do teto de 0,25** foi feita contra os manuais. Artigo escrito pelo
  suporte tem outra voz, e a medição precisa ser refeita quando houver artigo de
  verdade na base. O viés já registrado (perguntas escritas por quem leu o
  manual) continua valendo.
- **Citação rastreável.** Com o artigo como fonte, passa a existir um alvo
  estável para apontar (`article_id`), e a Helô poderia linkar o artigo em vez
  de só citar o nome. Não está neste plano; fica anotado porque ficou barato.

---

## Decidido em 10/09/2026, e o que a implementação encontrou

**As cinco decisões.** Quatro foram respondidas pelo Rickelme no mesmo dia; a
quinta ficou sem resposta e seguiu a recomendação deste plano.

1. **Reingestão por varredura periódica com hash — aprovada.** Auto-curativa é
   o requisito certo para uma base que ninguém olha.
2. **Os três manuais nascem como rascunho — aprovada.**
3. **`helo_pode_ler` booleano, padrão `true`.** O número que faltava veio do
   Rickelme, e é dele — não foi medido por mim: **em 10/09/2026 havia UM artigo
   publicado em produção, nenhum rascunho, nenhum arquivado.** Com um acervo de
   uma linha, o opt-in (padrão `false`) protegeria de nada e custaria o passo
   manual que a mudança de fonte existe para eliminar. O argumento está datado
   de propósito: se o acervo crescer e alguém reabrir, ele vale para um artigo,
   não para centenas.
4. **A inversão da regra de produto, com uma exceção explícita.** Na Base de
   Conhecimento, vínculo ausente é escolha de quem escreveu e vale para todos.
   Na IMPORTAÇÃO dos manuais, vínculo ausente é FATAL — ali quem cria é
   máquina, e ninguém escolheu nada. Duas regras, dois lugares; o comentário
   está nos dois (`scripts/importa_manuais_para_kb.py` e
   `_set_article_products` em `app/routers/kb.py`), cada um apontando o outro.
5. **`helo_documents` e `helo_chunk_products` morrem** — sem resposta; seguiu a
   recomendação.

**O que mudou em relação ao plano, e por quê:**

- **Nenhuma migration destrutiva.** O plano previa derrubar as duas tabelas
  numa migration nova. A `a7v8w9x0y1z2` nunca rodou em produção (a extensão
  nem existe lá), então, pelo critério de imutabilidade, ela foi REESCRITA no
  formato final: as tabelas antigas simplesmente não chegam a existir em
  produção. A única migration nova é a `c9x0y1z2a3b4`, aditiva.
- **O hash é do resultado do corte, não do `content`.** Hash do texto cru não
  enxerga mudança de receita — a lição do `_hash_do_resultado` da ingestão por
  arquivo.
- **Os cortes das fichas comerciais morreram** com o script de ingestão
  (`_corta_regua`, `_corta_markdown`, `_corta_emoji`): só as fichas os usavam.
- **O slug saiu do router** (`app/utils/slug.py`), pelo mesmo motivo do
  gravador de histórico: script não importa de router.

**O que foi MEDIDO:**

- **`updated_at` anda a cada visualização** — o argumento que escolheu hash em
  vez de carimbo. A primeira tentativa de medir caiu numa armadilha do próprio
  teste: o `now()` do Postgres é o início da transação, e o teste inteiro roda
  numa só. Refeita contra uma data plantada, confirmou.
- **Ponta a ponta, contra banco local com os manuais reais:** a importação
  criou 3 rascunhos, cada um vinculado exatamente ao seu produto; o manual do
  Phoebus tinha 3 linhas com cara de senha, e o artigo tem 3 marcas de redação e
  0 dígitos sobreviventes; rodar de novo é recusado. Varredura com os artigos
  em rascunho: 0 indexados, 0 chamadas ao embedding. Publicados: 46 trechos (18
  Phoebus, 16 Titan, 12 iBlow), 2 marcados com credencial. Varredura seguinte:
  3 inalterados, 0 chamadas. A cadeia inteira de migrations, de `z6u7` a
  `c9x0`, rodou no mesmo banco, que já tinha dados.
- **O teto de 0,25 continua valendo, e ficou mais apertado.** Remedido com as
  mesmas 40 perguntas contra a base nova: as 13 sem resposta continuam 100%
  barradas (mínimo 0,2570, contra 0,2590), e 21 das 27 com resposta ainda
  recebem trecho (eram 22). A margem caiu de 0,009 para 0,007: a primeira linha
  dos trechos agora é o título limpo, sem o emoji e a pontuação do manual, e a
  distância mexeu em até oito milésimos.
