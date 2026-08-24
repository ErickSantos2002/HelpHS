# Duas fontes de verdade para "de qual empresa é este cliente"

**Data:** 24/08/2026
**Origem:** dívida estrutural encontrada ao atualizar `docs/decisoes-e-regras.md`
para a v1.8.0. Custou uma decisão concreta: a unicidade de número de série
virou "por dono" em vez de "por empresa" porque não há chave de empresa
confiável (`backend/app/routers/products.py:150`, docstring de
`_recusa_serie_duplicada`, diz isso com todas as letras).

**Escopo:** levantamento. Nenhuma linha de código de produção foi escrita.

---

## Resumo executivo

O diagnóstico da origem está certo no essencial — existem duas fontes de verdade
e elas não conversam — mas **erra o alvo em dois pontos**, e a correção muda qual
é o conserto barato:

1. `User.cnpj` **é normalizado** no caminho de onboarding, nas duas pontas: o
   front valida os dígitos verificadores e envia `onlyDigits()`; o back rejeita
   o que não tiver 14 dígitos e grava só dígitos. Quem não normaliza é
   `Company.cnpj` — texto livre, sem validador nenhum, e o próprio front ensina
   o admin a digitar com pontuação (`placeholder="00.000.000/0000-00"`).
2. Ou seja: as duas colunas estão normalizadas em **direções opostas**. Não é
   "nenhuma das duas é normalizada"; é que uma guarda `11222333000181` e a outra
   guarda `11.222.333/0001-81`. Comparação por string entre elas nunca dá igual,
   por construção.
3. **Já existe uma ponte entre os dois mundos** que ninguém citou:
   `GET /groups/companies/suggestions` (`groups.py:409`). Ela agrupa clientes sem
   vínculo pelos dados de onboarding e oferece ao admin criar a `Company` a
   partir dali. A ponte está **quebrada pela metade** — ver Parte 1.

---

## Parte 1 — Quem lê cada campo

### `User.cnpj` — `String(18)`, nullable, sem UNIQUE, sem índice

**Escrita**

| Onde | Schema | Normaliza? |
|---|---|---|
| `PATCH /users/me/onboarding` (`users.py:301`) | `OnboardingUpdate` | **Sim.** `cnpj_deve_ter_14_digitos` (`schemas/user.py:78`) tira pontuação e recusa != 14 dígitos |
| `PATCH /users/me` (`users.py:216`) | `UserUpdate` | **Não.** Só `max_length=18` |
| `PATCH /users/{id}` (`users.py:349`) | `UserUpdate` | **Não.** Mesmo buraco, e aqui é admin editando terceiro |

O front reforça o caminho bom: `isValidCnpj` (`frontend/src/lib/documents.ts:10`)
confere os dois dígitos verificadores antes de enviar, e tanto `OnboardingPage`
quanto `ProfilePage` mandam `onlyDigits(cnpj)`. **O furo é o `UserUpdate`, não o
onboarding** — é por ali que entra CNPJ com pontuação ou lixo.

**Leitura**

- `products.py:397` — `data.company_cnpj = owner.cnpj`, exibido em
  `ProductsPage.tsx:388` e `:772`. Só exibição.
- `groups.py:417/431/442` — `/groups/companies/suggestions`, o agrupamento de
  candidatas a empresa.
- `UserResponse.cnpj` → `ProfilePage.tsx:410`, que reformata com regex assumindo
  14 dígitos crus; e `ProfilePage.tsx:291`, o aviso de "cadastro incompleto".

Confirmado o palpite: **fora as suggestions, `User.cnpj` só serve para exibição
e para o gate de cadastro completo.** Nenhuma regra de negócio depende dele.

### `User.company_id` — FK → `companies.id`, `ON DELETE SET NULL`, nullable, indexado

**Escrita** — três caminhos, todos em `groups.py`:

- `POST /groups/{g}/companies/{c}/clients` (`:320`) — atribui
- `DELETE /groups/{g}/companies/{c}/clients/{id}` (`:347`) — volta a NULL
- excluir a `Company` — volta a NULL, **em silêncio** (Parte 3)

**Leitura** — sete pontos, todos em `groups.py`: `_company_client_count` (`:68`),
lista de clientes da empresa (`:240`), `list_unassigned_clients` (`:391`),
`get_company_suggestions` (`:427`), e as guardas de `unassign_client` (`:341`) e
`update_client_notes` (`:365`).

**Achado relevante: `company_id` não existe fora da tela de Grupos.** Ele **não
está em `UserResponse`**. O cliente não recebe o próprio `company_id` em
`/users/me`; nenhuma outra tela do front sabe que esse campo existe. No front, só
`GroupsPage.tsx` e `groupService.ts` o tocam. Palpite confirmado, e mais forte do
que a suspeita: não é "usado só na tela de Grupos", é **invisível para o resto do
sistema**.

### `Company.cnpj` — `String(18)`, nullable, sem UNIQUE, sem índice

**Escrita** — `create_company` (`groups.py:221`) e `update_company` (`groups.py:281`,
laço sobre os campos). `CompanyCreate` e `CompanyUpdate` declaram
`cnpj: str | None = None` e **nenhum validador**. Vale qualquer string até 18
caracteres.

**Leitura** — exibição em `GroupsPage.tsx:287`, `:558`, `:1070`; e a busca em
`:196`, que é `(s.cnpj ?? "").includes(search)` — substring crua, então buscar
`11222333000181` não acha a empresa gravada como `11.222.333/0001-81`.

### O cruzamento: existe um, e está pela metade

`GET /groups/companies/suggestions` (`groups.py:409`) agrupa clientes com
`role=client`, `status=active`, `company_name IS NOT NULL` e `company_id IS NULL`
por `(company_name, cnpj, city, state, address)`, e devolve com `client_count`.
O admin vê a lista e clica "Adicionar".

Dois defeitos concretos nessa ponte:

1. **Criar a empresa a partir da sugestão não vincula ninguém.**
   `handleAddFromSuggestion` (`GroupsPage.tsx:199`) chama só `createCompany`, e
   `create_company` (`groups.py:214`) não toca em `User`. Os clientes que
   *geraram* a sugestão continuam com `company_id NULL` — então a sugestão
   **reaparece na próxima abertura do modal**, e clicar de novo cria uma
   `Company` duplicada. O contador "3 clientes" vira uma promessa que a ação não
   cumpre.
2. **O agrupamento é pela tupla inteira**, incluindo endereço. Dois clientes da
   mesma empresa que digitaram o endereço diferente viram duas sugestões. Some-se
   a isso o `key={s.company_name}` do React (`GroupsPage.tsx:283`), que colide
   quando duas sugestões compartilham o nome.

E o efeito de formato: a empresa criada **a partir da sugestão** herda o CNPJ do
cliente (14 dígitos crus); a criada **na aba manual** recebe o que o admin
digitou, com pontuação. `companies.cnpj` é uma mistura dos dois formatos.

---

## Parte 2 — O estado do dado

Não toquei em produção. As consultas abaixo foram **validadas** contra um
Postgres efêmero (`pgserver`, Rota B do `desenvolvimento-local.md`) com as
migrations reais aplicadas até `u1p2q3r4s5t6` e dados sintéticos montados para
disparar cada caso. São só `SELECT`. Para rodar no DBeaver, apontando para
produção:

```sql
-- 1. Panorama: quantos clientes estão em cada estado
SELECT
  count(*) FILTER (WHERE cnpj IS NOT NULL AND company_id IS NULL)     AS so_cnpj,
  count(*) FILTER (WHERE cnpj IS NOT NULL AND company_id IS NOT NULL) AS ambos,
  count(*) FILTER (WHERE cnpj IS NULL     AND company_id IS NOT NULL) AS so_vinculo,
  count(*) FILTER (WHERE cnpj IS NULL     AND company_id IS NULL)     AS nenhum,
  count(*)                                                            AS total_clientes
FROM users WHERE role = 'client';
```

```sql
-- 2. Divergência: entre os vinculados que têm os dois CNPJs, quantos discordam
--    (normalizando pontuação dos dois lados antes de comparar)
SELECT
  count(*) AS vinculados_com_os_dois_cnpjs,
  count(*) FILTER (
    WHERE regexp_replace(u.cnpj, '\D', '', 'g')
       <> regexp_replace(c.cnpj, '\D', '', 'g')
  ) AS divergentes
FROM users u JOIN companies c ON c.id = u.company_id
WHERE u.role = 'client' AND u.cnpj IS NOT NULL AND c.cnpj IS NOT NULL;
```

```sql
-- 3. Formato: comprova (ou desmente) a assimetria de normalização
SELECT 'users' AS tabela,
       count(*) FILTER (WHERE cnpj ~ '^[0-9]{14}$')  AS so_digitos,
       count(*) FILTER (WHERE cnpj !~ '^[0-9]{14}$') AS com_pontuacao_ou_invalido,
       count(*) AS preenchidos
FROM users WHERE role = 'client' AND cnpj IS NOT NULL
UNION ALL
SELECT 'companies',
       count(*) FILTER (WHERE cnpj ~ '^[0-9]{14}$'),
       count(*) FILTER (WHERE cnpj !~ '^[0-9]{14}$'),
       count(*)
FROM companies WHERE cnpj IS NOT NULL;
```

```sql
-- 4. Quantos clientes se agrupariam por CNPJ normalizado (o "por empresa" que
--    a opção (a) entregaria), e se o nome bate entre eles
SELECT regexp_replace(cnpj, '\D', '', 'g') AS cnpj_norm,
       count(*)                            AS clientes,
       count(DISTINCT company_name)        AS nomes_distintos
FROM users WHERE role = 'client' AND cnpj IS NOT NULL
GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC;
```

```sql
-- 5. Companies duplicadas pelo mesmo CNPJ normalizado
--    (o sintoma do defeito 1 da Parte 1). Responde se dá para pôr UNIQUE.
SELECT regexp_replace(cnpj, '\D', '', 'g') AS cnpj_norm,
       count(*)                            AS empresas,
       array_agg(name)                     AS nomes
FROM companies WHERE cnpj IS NOT NULL
GROUP BY 1 HAVING count(*) > 1;
```

**O que cada número decide:**

- **(1)** dimensiona o problema. Se `so_cnpj` for a esmagadora maioria, `company_id`
  hoje é decorativo e qualquer regra "por empresa" baseada nele cobre quase ninguém.
- **(2)** diz se o dado já está *contraditório*, não só disperso. `divergentes > 0`
  significa que existe cliente vinculado a uma empresa cujo CNPJ não é o que ele
  declarou — e é exatamente esse cliente que a Parte 5 mostra aparecendo com o
  CNPJ errado na tela de equipamentos.
- **(3)** confirma a assimetria de formato no dado real.
- **(4)** é o teto de ganho da opção (a).
- **(5)** decide se `UNIQUE` em `companies.cnpj` é sequer viável hoje.

---

## Parte 3 — O que acontece quando uma empresa é excluída

**Resposta: os clientes sobrevivem e o `company_id` vira NULL, em silêncio.**

Comprovado empiricamente, não deduzido: subi o Postgres efêmero, apliquei as
migrations reais e executei o **mesmo caminho de código** do endpoint
(`db.delete(c)` numa sessão async, como em `groups.py:294`). Resultado:

```
FK users.company_id -> [('users_company_id_fkey', 'SET NULL')]
antes  -> user.company_id = 20a4333d-...  | notas = 1
depois -> user existe? True  | company_id = None
depois -> nota existe? False
depois -> empresa existe? False
```

As duas camadas concordam: a FK no banco é `ON DELETE SET NULL`
(`models.py:220`) e o ORM, com `Company.clients` sem cascade de exclusão,
também anula. **Não fica órfão e não é bloqueado** — a terceira hipótese é a
certa. As `CompanyNote` são apagadas junto (`cascade="all, delete-orphan"`,
`models.py:178`).

**Não há teste dizendo qual é a regra.** A suspeita da origem está certa e é pior
do que "34% de cobertura": `grep` na suíte inteira mostra que **nenhum teste
referencia `Company`, `company_id`, nem qualquer endpoint de `/groups`**. Os
únicos aparecimentos de "company" em `backend/tests/` são `company_name`,
`company_cep` e `company_cnpj` — colunas de onboarding do `User`. `groups.py` é
o maior router sem um único teste.

**Agravantes de UX**, já que a regra é silenciosa:

- `delete_company` não avisa quantos clientes vai desvincular. `_company_client_count`
  existe (`groups.py:65`) e é exibido na listagem, mas não é consultado na exclusão.
- Um detalhe que salva parcialmente: como `User.cnpj` e `company_name` sobrevivem,
  os clientes desvinculados **reaparecem em `/companies/suggestions`**. O sistema
  meio que se autocura — mas em silêncio, e alimentando direto o bug de empresa
  duplicada da Parte 1.

---

## Parte 4 — Opções de reconciliação

### (a) Normalizar `User.cnpj` e derivar a empresa a partir dele

**Custo:** baixo. Migration: **nenhuma** — `String(18)` já comporta 14 dígitos.
Backfill: script avulso normalizando as duas colunas.

**Por que não resolve sozinha:** o CNPJ é **autodeclarado e não verificado no
servidor**. O back só conta 14 dígitos; quem confere os dígitos verificadores é o
front (`documents.ts`), que é o cliente. Eleger esse campo como chave de
*tenancy* significa deixar o cliente escolher em que escopo ele cai — digitar o
CNPJ de outra empresa passa a ser um caminho de acesso. Para exibição isso é
inofensivo; para escopo de série, de chamado ou de relatório, é uma falha de
autorização. **Elimina (a) como resposta única.**

### (b) Vincular a `Company` no onboarding

**Custo:** alto, e maior do que parece. `Company.group_id` é `NOT NULL`
(`models.py:157`): uma empresa criada pelo cliente não tem grupo. Exige decidir
onde ela cai — grupo "sem classificação", ou `group_id` nullable — o que é
mudança de schema **e** muda o significado do modelo de Grupos, hoje uma
ferramenta de organização interna do admin. Some-se o mesmo problema de (a):
quem escolhe é o cliente, autodeclarando.

### (c) Manter os dois e declarar a fonte de verdade de cada uso

**Custo:** zero de código. Mas sozinha não destrava nada — toda regra "por
empresa" continua esbarrando na mesma pedra.

### Recomendação

**Nenhuma das três isolada. A sequência abaixo, nesta ordem** — (c) primeiro
porque é o que destrava o *desenho*, depois a parte de (a) que é segura, e a
parte de (b) que mantém a autoridade com o admin.

**Passo 1 — declarar a fonte de verdade (é (c), e é o entregável imediato).**
Em `docs/decisoes-e-regras.md`:

> `companies.id` é a **única** autoridade sobre "de qual empresa é este cliente".
> `users.cnpj` é dado de onboarding autodeclarado: serve para exibir, sugerir e
> casar candidatos — **nunca** para escopo, permissão ou unicidade.

Uma frase. É ela que teria tornado a decisão de hoje sobre o serial uma escolha
explícita em vez de uma imposição, e é ela que dá critério para as próximas.
Custo: nenhum. Migration: nenhuma.

**Passo 2 — normalizar os dois lados, para que casar seja possível.**
Aplicar o validador que já existe (`cnpj_deve_ter_14_digitos`) aos três pontos
que hoje não têm: `UserUpdate`, `CompanyCreate`, `CompanyUpdate`. Ajustar o
`placeholder` do front e mascarar na exibição, não no armazenamento.
Migration: **nenhuma**. Backfill: **script avulso** em `backend/scripts/`,
rodado à mão, que normaliza as linhas existentes e relata o que mudou — nunca em
migration, conforme a regra que já vale aqui. A regra nova é prospectiva; o
script é que corrige o passado.

**Passo 3 — fechar o laço das sugestões.**
Ao criar empresa a partir de uma sugestão, vincular os clientes que a geraram,
casando por CNPJ normalizado. É aqui que (a) e (b) se encontram sem os defeitos
de nenhuma das duas: **o casamento usa o CNPJ, a autoridade continua sendo o
clique do admin.** Conserta de quebra o bug de empresa duplicada. Migration:
nenhuma. Pré-requisito: `groups.py` precisa ganhar testes antes — hoje tem zero.

**Passo 4 — só então, regras "por empresa".**
Com a consulta (1) mostrando cobertura de `company_id` alta o bastante, aí sim
faz sentido chavear regra por empresa, sempre com o comportamento de
`company_id IS NULL` documentado. Migration só quando uma regra específica pedir
(serial por empresa, por exemplo, precisa de `company_id` alcançável a partir de
`equipments`).

**Não fazer agora:** `UNIQUE` em nenhuma das duas colunas de CNPJ.
`users.cnpj` repete legitimamente (vários funcionários da mesma empresa).
`companies.cnpj` talvez devesse ser único por grupo, mas a consulta (5) pode
mostrar que o dado atual já viola. Decidir com o número na mão.

---

## Parte 5 — O que isso destrava

**Conhecido — série por empresa.** `products.py:150` já registra a dependência:
*"A evolução para escopo por empresa/CNPJ depende de normalizar o campo CNPJ, que
hoje é texto livre digitado no onboarding."* O furo aceito hoje é que dois
colegas da mesma empresa cadastram o mesmo aparelho, cada um no próprio escopo.

**Novo, e provavelmente o mais urgente — escopo de chamados.**
`tickets.py:433`: `if actor.role == UserRole.client: base = base.where(Ticket.creator_id == actor.id)`.
O cliente vê **só os próprios chamados**. Dois funcionários da mesma empresa não
enxergam os chamados um do outro — quem abriu sai de férias e o colega não
acompanha, nem consegue responder. Isso não é hipótese de arquitetura, é
reclamação de cliente esperando para acontecer, e depende exatamente da mesma
chave de empresa confiável. Mesmo padrão em `:278`, `:509`, `:534`, `:542`,
`:608`, `:1083`.

**Novo — relatórios e dashboard por empresa.** `dashboard.py` não tem **nenhuma**
dimensão de empresa: agrupa por status, prioridade, categoria, produto, técnico,
dia da semana e hora. "Chamados por empresa", "SLA por empresa" e "satisfação por
empresa" são impossíveis hoje, não difíceis.

**Novo, e já quebrado em produção — CNPJ errado na tela de equipamentos.**
`products.py:397` monta `company_cnpj` a partir de `owner.cnpj`, o autodeclarado,
**ignorando a `Company` vinculada**. Se o cliente estiver vinculado a uma empresa
com CNPJ diferente do que ele digitou, a lista de equipamentos mostra o CNPJ
errado. Não é dívida futura: é uma inconsistência viva, e a consulta (2) da
Parte 2 diz quantos registros estão nesse estado.
