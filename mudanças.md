# Mudanças — Rickelme David

Registro do trabalho feito por **Rickelme David** neste repositório, por data.
O changelog do produto (o que o cliente vê) fica em
`frontend/src/data/changelog.ts`; o changelog do repositório, para devs, é o
[Changelog.md](Changelog.md).

---

## 24/08/2026 — Duas fontes de verdade para "empresa", e o começo da reconciliação

Frente nova, aberta pelo próprio trabalho de documentação: escrever a
atualização do `decisoes-e-regras.md` esbarrou numa dívida que ninguém tinha
mapeado — existem **duas** fontes de verdade para "de qual empresa é este
cliente" (`User.cnpj` e `User.company_id`), e elas não conversam. Não é dívida
teórica: foi ela que, três dias antes, empurrou a unicidade de número de série
para "por dono" quando a decisão de negócio correta era "por empresa".

| Commit | O que foi feito |
|---|---|
| `99b0847` | `docs:` **levantamento** das duas fontes de verdade |
| `f7ddadc` | `docs:` **`companies.id` declarado única autoridade** de escopo por empresa |
| `62f022e` | `fix:` **CNPJ com pontuação deixa de chegar ao banco**, com script de backfill |
| `1c414c0` | `fix:` nome de teste que **prometia mais do que provava** |
| `e30968e` | `fix:` **cobertura parava de contar** depois do primeiro `await` no banco |
| `470d56c` | `test:` **domínio de empresa em `groups.py`** sai do descoberto |
| `abdee48` | `feat:` **criar empresa pela sugestão passa a vincular** os clientes |
| `3478bae` | `fix:` **admin de seed deixa de nascer com senha do repositório** 🔴 |
| `b736114` | `test:` as duas defesas do seed de admin |
| `docs:` | Este fechamento |

### O levantamento corrigiu a própria premissa

A suspeita inicial era que nenhum dos dois campos fosse normalizado. O
levantamento provou o contrário, e o contrário é pior: `users.cnpj` **é**
normalizado desde sempre — o `OnboardingUpdate` tira a pontuação, e o front
ainda confere os dígitos verificadores antes de enviar. Quem não normalizava
era `companies.cnpj`, texto livre sem validador nenhum, alimentado por um
`placeholder` que ensinava o admin a digitar `00.000.000/0000-00`.

As duas colunas estavam normalizadas em **direções opostas**. Uma guardava
`11222333000181`, a outra `11.222.333/0001-81`. Nenhuma comparação por string
entre elas jamais daria igual. O `e41684c` do dia anterior afirmava o contrário
e foi corrigido no `f7ddadc`.

Três outras coisas saíram do mapa, e nenhuma era esperada:

- **`company_id` não existe fora da tela de Grupos.** Não está no
  `UserResponse` — o cliente não recebe o próprio vínculo, e nenhuma outra tela
  sabe que o campo existe.
- **Já havia uma ponte**, `GET /groups/companies/suggestions`, que agrupa
  clientes sem vínculo pelos dados de onboarding. Só que criar a empresa a
  partir da sugestão **não vincula ninguém**: os clientes seguem com
  `company_id` nulo, a sugestão reaparece e clicar de novo cria uma empresa
  duplicada.
- **Excluir uma empresa desvincula os clientes em silêncio.** Comprovado em
  Postgres efêmero, rodando o mesmo caminho de código do endpoint: a FK é
  `ON DELETE SET NULL`, o ORM concorda, as notas da empresa somem junto e nada
  avisa quantos clientes foram soltos. Não há teste dizendo qual é a regra —
  **nenhum** teste da suíte referencia `Company`, `company_id` ou qualquer
  endpoint de `/groups`.

### A recomendação não foi nenhuma das três opções

As opções na mesa eram normalizar o CNPJ e derivar a empresa dele (a), vincular
a `Company` no onboarding (b), ou só documentar quem manda (c). A recomendação
foi uma **sequência**, porque (a) sozinha é uma falha de autorização esperando
acontecer: o CNPJ é autodeclarado e o servidor só conta 14 dígitos — quem
confere os dígitos verificadores é o front, que é o cliente. Eleger esse campo
como chave de escopo é deixar o cliente escolher em que escopo ele cai.

Primeiro declarar a fonte de verdade (`f7ddadc`), depois normalizar as duas
pontas para que casar seja **possível** (`62f022e`), depois fechar o laço das
sugestões vinculando por CNPJ normalizado — é ali que (a) e (b) se encontram
sem os defeitos de nenhuma das duas: o casamento usa o CNPJ, a autoridade
continua sendo o clique do admin.

### A normalização, e a decisão de pôr a regra no tipo

O caminho óbvio era repetir o `@field_validator` nos três schemas que não
tinham. Não foi o escolhido: um validador copiado por modelo deixa o **próximo**
campo de CNPJ nascer sem validação nenhuma, que é literalmente o defeito que o
`CompanyCreate` tinha. A regra passou a viajar no tipo — `CnpjOpcional` e
`CnpjObrigatorio` — e esquecer dela agora exige contrariar a anotação.

O cuidado que mais custou pensamento foi o campo opcional. `None` e string
vazia precisam passar e virar `None`, porque limpar o campo no front manda
`""` e não `null`; um validador estrito ali quebraria criar empresa sem CNPJ,
que hoje funciona, e todo `PATCH` que não mexe em CNPJ. Mas `"abc"` não é
campo limpo, é erro de digitação, e virar `None` em silêncio seria perder dado.
São dois testes separados justamente porque a distinção é fácil de errar.

No front, o `placeholder` de empresa passou a pedir dígitos e a máscara voltou
só na exibição. Apareceu de brinde uma terceira duplicação: `OnboardingPage` e
`ProfilePage` tinham a **mesma** máscara de digitação copiada, e foi ela que
colidiu com o import do helper novo. As duas cópias saíram.

### O script que não apaga o que não entende

O backfill é avulso e roda à mão — regra do projeto, e desta vez com um motivo
a mais: o `.env` local aponta para produção. Dry-run por padrão, `--aplicar`
para gravar, e importando a **mesma** normalização do validador, porque uma
cópia própria da regra gravaria linha que a API recusaria depois.

A decisão que importa é o que fazer com a linha que não soma 14 dígitos:
ela é **relatada e deixada como está**. Um script de limpeza que descarta o que
não entende é pior que o problema que veio consertar; quem decide o destino
dela é quem lê o relatório.

Rodar de verdade num Postgres efêmero pagou o preço na hora: o relatório morria
com `UnicodeEncodeError` antes da primeira linha, porque o console do Windows
abre em cp1252 e o script roda na máquina de quem administra, não no container.
Testar só a função pura nunca teria mostrado isso.

### O que fica

O Passo 3 — fechar o laço das sugestões — depende de `groups.py` ganhar
testes, e ele não tem nenhum. O Passo 4, regras "por empresa" de verdade, só
faz sentido depois de medir quantos clientes têm `company_id`; as consultas de
diagnóstico estão prontas no documento de investigação e ainda não foram
rodadas em produção. O backfill também não.

E ficou registrado que o escopo de chamados é provavelmente mais urgente que a
série: hoje o cliente vê só os próprios chamados, então dois funcionários da
mesma empresa não enxergam o que o colega abriu.

### Cobrir antes de mexer, e o que a cobertura revelou

O Passo 3 saiu em duas partes, e a ordem não era formalidade: mexer no
`groups.py` sem teste seria repetir o próprio bug que ele tem — ação que
promete o que não cumpre.

Escrever os testes trouxe duas descobertas que não estavam no plano.

A primeira: **a suíte inteira media cobertura errado.** O relatório dizia que
`update_company` tinha a primeira linha coberta e as sete seguintes não — o
laço inteiro dado como não executado, com teste passando por ele. A mutação
provou o contrário: quebrar aquelas linhas derrubava o teste, então elas
executavam. A causa é o greenlet — o SQLAlchemy async atravessa
`greenlet_spawn` a cada `await` de banco e o coverage perde o rastro na volta.
Uma linha de configuração resolveu, e `groups.py` foi de 43% para 62% **com os
mesmos testes**. Todo número de cobertura que este repositório reportou até
hoje estava abaixo do real.

A segunda: **uma asserção minha não sobreviveu à própria checagem.** Eu tinha
escrito `assert resp.content == b""` para provar que a exclusão de empresa é
silenciosa. Ao mutar o endpoint para devolver um corpo, o teste continuou
passando — o `204` já garante corpo vazio, então a asserção não provava nada.
Foi trocada pelo status, que cai se a exclusão virar bloqueante (`409`) ou
informativa. É a mesma armadilha do teste renomeado no `1c414c0`, e desta vez
quem pegou foi a mutação, não a leitura.

Os testes usam banco de verdade, não mock, e isso foi decisão e não gosto: a
desvinculação silenciosa **não dá para provar com mock**. Quem desvincula o
cliente é o SQLAlchemy com a FK `ON DELETE SET NULL` por baixo; um mock
afirmaria que `db.delete` foi chamado e passaria mesmo que a regra fosse a
oposta. SQLite em memória reproduz o mesmo resultado do Postgres efêmero do
levantamento e roda no CI sem subir serviço.

### O laço fechado, e o defeito que virou cosmético

Criar empresa pela sugestão agora vincula quem a gerou. As três decisões:

**Endpoint próprio**, e não parâmetro no `create_company`. Cadastro manual não
pode ganhar efeito colateral de vínculo em massa — uma empresa criada à mão
que, por coincidência de CNPJ, arrastasse clientes junto seria o inverso exato
do defeito consertado aqui: ação que faz **mais** do que diz.

**Reaproveitar em vez de duplicar**, mas só dentro do mesmo grupo. Isso não
foi preferência: `Company.group_id` é `NOT NULL` e único, então "reusar" uma
empresa de outro grupo seria *mudá-la de grupo*. A pergunta se dissolveu no
schema.

**Lista explícita e prévia.** O vínculo vai pelos `client_ids` que a tela
mostrou, não por uma consulta que o servidor refaz, e o modal ganhou um passo
de confirmação com nome e e-mail de cada um. Vincular em massa sem ver quem é
ação que ninguém desfaz. De brinde, some a janela entre a tela e o clique:
cliente que mudou de estado no meio derruba tudo com `409`, e nada é gravado
— nem a empresa.

O agrupamento das sugestões pela tupla inteira **ficou como está**. Rechaveá-lo
no CNPJ exige decidir qual nome vence quando dois clientes da mesma empresa
digitaram nomes diferentes, e o que fazer com quem tem `company_name` mas não
tem CNPJ — decisões de produto, não de implementação. Mas o estrago acabou: com
o reaproveitamento por CNPJ, os dois cards caem na mesma empresa. O defeito
virou cosmético — dois cliques em vez de um — em vez de gerar duplicata.

### O achado do dia: o boot de produção criava um admin com senha pública

Verificação de segurança pedida no fim do dia, e o resultado foi o pior tipo:
não era hipótese, era cadeia confirmada em três arquivos. `Dockerfile` chama
`start.sh`; `start.sh` roda `python -m app.seeds` a cada boot; `seed_admin`
criava `admin@healthsafety.com` com `Admin@123456` — senha escrita no código
deste repositório — como administrador **ativo**, sem nenhuma guarda de
ambiente.

O detalhe que mais incomoda é que o projeto **já sabia**. O `app.seeds_e2e`
tem guarda de produção, tem teste, e a docstring dele diz com todas as letras
que colocar conta de teste no `app.seeds` criaria "logins com senha em texto
claro conhecida por qualquer um que leia este repositório". O raciocínio certo
foi escrito, aplicado à conta de teste, e não à de admin — que é a mais
poderosa das duas.

A correção tem duas defesas, e elas não são a mesma coisa dita duas vezes.
`APP_ENV` de produção não cria a conta; **e** sem `SEED_ADMIN_PASSWORD` não
cria a conta. A segunda existe porque a primeira falha **aberta**: `app_env`
tem default `development`, então variável ausente ou digitada errada
desligaria a guarda de ambiente sozinha. Tirar a senha do código é a correção;
a guarda de ambiente é só a defesa.

E uma decisão que contraria a letra do pedido, de propósito: **nenhuma das
duas levanta exceção.** O pedido era "mesmo fail-fast do `seeds_e2e`", mas
`run_seeds` está no caminho do boot, e o `start.sh` roda com `set -e` — um
`RuntimeError` ali deixaria o container sem subir. Seria trocar um vazamento
de credencial por uma indisponibilidade. No `seeds_e2e` o `raise` é seguro
justamente porque nada chama aquele módulo em produção. A recusa vai para o
log e a execução segue; produto e SLA continuam sendo semeados, porque são
catálogo e não credencial.

Efeitos colaterais que precisaram vir junto: o workflow de e2e passou a
definir a variável (senão o Playwright perde o login do admin, contra o banco
efêmero do job) e a receita de ambiente local ganhou o `export` — com uma
pegadinha documentada, porque "subiu e o admin não loga" agora é sintoma
esperado de variável esquecida. Tem teste guardando o acoplamento entre o
workflow e o `helpers.ts`.

**O incidente não está fechado.** Falta verificar se a conta existe hoje em
produção e com que senha; a consulta está proposta e nada foi executado contra
o banco real. E note a assimetria que a idempotência cria: ela protege quem já
trocou a senha, mas em compensação apagar o usuário deixou de ser forma de
reiniciá-lo — sem a variável, ele não volta.

### O que continua na fila

O backfill e as cinco consultas de diagnóstico seguem sem rodar em produção.
O Passo 4 — regras "por empresa" de verdade — continua dependendo de medir
quantos clientes têm `company_id`. E limpar o CNPJ de uma empresa pela tela
segue sem funcionar: a guarda `if val is not None` do `update_company` vale
para os sete campos, então mexer nela é frente própria. Tem teste segurando
o comportamento atual para que a mudança seja escolha.

---

## 21/08/2026 — Fila técnica, oráculos e um tema que passa a perguntar

Dia sem frente de produto. Produção estável, `main` em `5fc10ce`, e as três
pendências do painel (`CORS_ORIGINS`, porta 8000, SMTP) paradas com o Rickelme
e o Erick. Sobrou o que estava na fila.

| Commit | O que foi feito |
|---|---|
| `f7945e0` | `test:` **FilterSelect, FormDropdown e ThemeContext** saem do descoberto |
| `3f3af90` | `feat:` **filtro de equipamentos sem dono** na listagem de Produtos |
| `77a8e9c` | `fix:` **/onboarding** deixa de abrir para quem não tem onboarding |
| `7371bc7` | `fix:` **chamado alheio deixa de denunciar que existe** |
| `902d331` | `fix:` **e-mail sai da frente da resposta** no forgot-password |
| `0e1a917` | `refactor:` duas linhas mortas — comentário e guard do dropdown |
| `8542183` | `feat:` **tema segue a preferência do sistema operacional** |
| `d5fa7a6` | `feat:` **número de série único por dono**, com migration |
| `32fc736` | `fix:` **chip de SLA** para de dizer Vencido para resposta já dada |
| `d361e78` | `ci:` **Playwright em workflow separado**, acionado à mão |
| `docs:` | Este fechamento |

### Três componentes que o CI protegia sem saber

O Vitest é gate do CI desde `1583b8b`. Isso significa que tudo que **tem**
teste está protegido — e que tudo que não tem passa como se estivesse. Os três
apontados pela rodada de test review não eram casca: são o dropdown de filtro
das listagens, o dropdown dos formulários e o tema.

O que justifica teste próprio em cada um é o que um `<select>` nativo daria de
graça e aqui é código nosso:

- **FilterSelect** renderiza o painel em portal no `document.body`, para não
  ser cortado pelo `overflow` da barra de filtros. O preço é que ele flutua
  ancorado a uma posição calculada **uma vez** na abertura, e por isso precisa
  fechar sozinho em clique fora, scroll e resize. Também reancora pela direita
  quando abriria fora da janela — sem isso, o filtro do fim da barra mostra
  metade das opções cortadas.
- **FormDropdown** é o irmão de dentro dos formulários: sem portal (dentro de
  um modal o portal escaparia da pilha de foco), com rótulo, erro de validação
  e desabilitado. Nos dois, a linha do placeholder devolve `""` — e esse é o
  contrato com quem consome.
- **ThemeContext** guarda a preferência em dois lugares que precisam
  concordar: a classe `dark` no `<html>`, que é o que o Tailwind lê, e a chave
  `helphs-theme`. Um sem o outro dá o bug clássico de escolher claro, dar F5 e
  voltar escuro — então tem um teste que fecha o ciclo escolher/sair/voltar,
  que é onde a divergência apareceria.

Um achado de escopo, registrado no próprio teste: **o padrão é o escuro, não a
preferência do sistema operacional**. O `ThemeContext` não lê
`prefers-color-scheme`; quem chega sem nada salvo — e quem chega com um valor
estragado — vê o escuro. Isso agora está afirmado por teste em vez de
subentendido, e se um dia virar decisão mudar, o teste é onde a conversa começa.

Teste escrito depois do código passa na primeira execução, o que não prova
nada. Cada arquivo foi então verificado por mutação: quebrar o fechamento do
painel do filtro, o fechamento do dropdown e a gravação da preferência derruba
exatamente os testes correspondentes, e só eles.

### O órfão que ninguém achava

O `3efb0cf` subiu o seletor de dono. Mas para usar o seletor o staff precisa
primeiro **achar** o equipamento órfão, e não tinha como: a listagem só
oferecia busca por nome e situação.

O ponto que decidiu a forma da solução: **`list_equipments` é paginada no
servidor**. Filtrar no navegador varreria só a página aberta — com 200
equipamentos e 20 por página, o órfão da página 7 ficaria invisível para
sempre, que é exatamente o caso que o filtro existe para resolver. Precisava
ser parâmetro novo do endpoint.

Entre um `without_owner: bool` e um filtro de dono genérico, ficou o booleano.
Não por ser menor: as duas coisas **não são alternativas**, são ortogonais.
"Sem dono" é a *ausência* de `owner_id` e não caberia num `owner_id=<uuid>` sem
inventar um valor sentinela para o nulo — e sentinela em query param é o tipo
de contrato que ninguém lembra seis meses depois. Um filtro por dono
específico, se fizer falta, entra ao lado deste sem renegociar nada.

O detalhe que virou teste: o filtro **soma** ao escopo por dono do cliente,
nunca substitui. Cliente pedindo `without_owner=true` recebe `owner_id = <ele>`
**E** `owner_id IS NULL`, que não casa com nada — lista vazia. A versão errada
dessa mesma linha seria uma enumeração do parque órfão inteiro por qualquer
cliente autenticado, então ela tem teste próprio dizendo isso.

### Uma porta que já estava trancada por dentro

`/onboarding` ficava sob o `AuthGuard` e fora do `OnboardingGuard`. Qualquer
autenticado abria a tela digitando a URL: o staff, que não tem onboarding
nenhum, e o cliente que já completou — para quem refazer significaria
sobrescrever dados de cadastro já revisados.

Ficar fora do `OnboardingGuard` era proposital: ele redireciona *para*
`/onboarding`, então colocá-la dentro apontaria o redirecionamento para si
mesmo. O que faltava não era mover a rota, era o **par**: o `OnboardingGuard`
empurra para a tela quem ainda deve preencher, o `OnboardingOnlyRoute` novo
tira de lá todo o resto.

Vale dizer o que isto **não** é: não é correção de segurança. A porta que
importava — o endpoint — já foi fechada no `b1ab978`. Isto é higiene de rota,
só no front.

### Doze cópias de uma regra que dizia demais

Aprovado o levantamento, foi execução. O `403` de chamado alheio dizia
"existe, mas não é seu" — meia resposta a mais do que quem só tem o id deveria
conseguir. Com uma lista de UUIDs dava para enumerar o sistema sem ler um
chamado sequer.

O tamanho real do problema só apareceu no levantamento: a regra estava copiada
em **quatro arquivos sob três nomes** — `_check_ticket_access` nos anexos,
`_get_ticket_or_403` no chat e mais quatro cópias inline em tickets e
avaliações. Doze pontos de entrada. A premissa de que o helper dos anexos era
compartilhado entre routers não se sustentou: ele nunca saiu do arquivo dele;
o que viajou foi a *ideia*, recopiada à mão cada vez.

Passa a existir `ensure_ticket_visible` em `app/utils/`. **Ele não abre exceção
para staff** — quem decide isso é o call site, e essa foi a decisão explícita
do Rickelme. O motivo tem precedente no `2ad773c`: um helper que "sabe" que
admin passa vira passe-livre invisível no dia em que alguém o chamar de um
endpoint novo sem ler o corpo dele. Aqui a regra é só "é seu?", e cada endpoint
diz em voz alta quem submete a ela.

**Só para cliente.** Técnico e admin já listam o sistema inteiro sem escopo, de
modo que `404` entre eles não fecharia oráculo nenhum e quebraria
assumir/atender — escopo entre técnicos seria regra de acesso nova, conversa de
produto. E onde a recusa é de **papel**, o `403` fica: técnico na observação do
cliente, staff que não abriu o chamado na avaliação. Trocar por `404` ali não
esconderia existência de nada e trocaria "seu perfil não faz isso" por uma
mentira que manda o admin caçar um bug que não há. Os dois casos têm teste
dizendo isso.

#### Três coisas que uma varredura de status HTTP não acharia

1. **`GET /attachments/{id}` vazava duas vezes** — pelo id do anexo *e* pelo do
   chamado pai, com três respostas distinguíveis. O cliente agora recebe a
   mesma nos três casos, e ela fala do **anexo**: responder "chamado não
   encontrado" a quem pediu o anexo já confirmaria que o anexo existe.
2. **O WebSocket tinha o mesmo oráculo em código de fechamento** — `4003`
   contra `4004`. Quem tivesse a lista de ids enumerava o sistema pelo chat sem
   nunca receber um HTTP `403`. Fecha `4004` nos dois casos, com o mesmo
   motivo. Não havia teste nenhum de WS no repositório; agora há, com um
   harness que dispensa o lifespan da app (que abre conexão real com o
   Postgres).
3. **`"Attachment not found"` não tinha tradução** em `apiError.ts`. O
   Rickelme pegou isso conferindo o dicionário antes de aprovar. Sem somar a
   entrada, a correção de backend entregaria ao cliente um toast cru em inglês
   — exatamente o bug que o `2db8dfa` consertou para equipamento. Foi no mesmo
   commit: o texto só passa a chegar ao cliente por causa da mudança do
   backend, e separar deixaria uma janela com a tela em inglês.

#### O que impede a regra de divergir de novo

O texto da recusa e o do id inexistente saem de **uma constante por recurso**
em cada router. Não é enfeite: dois `404` com mensagens diferentes continuariam
separando "não é seu" de "não existe", só que com mais disfarce. Além disso,
cada arquivo ganhou um teste de paridade no molde do
`test_ownership_refusal_message_is_the_same_everywhere` que já guardava os
equipamentos — a versão anterior desta regra divergiu justamente por uma cópia
esquecida, então o contrato agora é executável.

Cobertura nova nos três ramos que não tinham teste nenhum: `observation`,
`GET /attachments/{id}` e o WebSocket. Sem migration, sem backfill. **471 → 490
testes no backend.**

### O oráculo que ainda não existe

O envio de e-mail do `forgot-password` era aguardado dentro do handler, e o
SMTP só é chamado no ramo da conta existente. Enquanto for assim, os dois ramos
respondem em tempos diferentes e o **relógio diz o que a mensagem cala** — o
mesmo oráculo de enumeração que o `f8e6013` fechou no login, renascendo ao lado
dele.

O que torna o caso interessante é que **ele não existe em produção hoje**. Não
por cuidado nosso: só porque não há SMTP configurado. O oráculo nasceria pronto
no dia em que o Erick ligasse o SMTP, sem ninguém ter tocado numa linha de
código. É a diferença entre uma dívida e uma armadilha com data marcada — e o
motivo de o Rickelme ter mandado entrar antes.

`BackgroundTasks` nos dois endpoints com o mesmo formato — `forgot-password` e
`resend-verification`. A resposta sai antes de o envio começar.

O teste não mede relógio. Mock de rede não tem latência real, e teste de tempo
em CI compartilhado é instável por natureza — ele mediria o runner, não o
código. Mede a **ordem**: chamando a app pelo ASGI cru dá para ver os eventos
que saem. Antes da correção a sequência era
`['envio', 'response.start', 'response.body']`; agora o envio vem por último.
Mais dois testes garantem que os ramos neutros não agendam envio nenhum —
agendar seria pior que aguardar, porque mandaria e-mail a quem não tem conta.

Ficou de fora, de propósito: o `register` também envia inline. Lá a resposta já
difere por ramo (`409` de e-mail duplicado), então o relógio não acrescenta
nada ao que o status já conta. Quando o **#3.1** tornar o register neutro, este
mesmo tratamento precisa ir junto — senão a neutralidade nasce furada pelo
tempo.

### O tema passa a perguntar antes de decidir

Ontem o teste do `ThemeContext` registrou que o padrão era escuro fixo e que o
app não lia `prefers-color-scheme`. Registrar em vez de consertar foi o certo:
era decisão de produto, não bug. O Rickelme decidiu mudar.

Agora quem nunca escolheu recebe a preferência do sistema operacional; quem já
escolheu manda, contra o sistema inclusive — o SO é o palpite inicial, não uma
ordem. Duas consequências que a mudança de regra arrastou junto, e que não eram
óbvias no enunciado:

1. **A gravação saiu do efeito de montagem.** O código antigo gravava o tema no
   `localStorage` a cada montagem. Mantendo isso, o valor do SO seria capturado
   na primeira visita e **congelado ali**: quem trocasse o tema do sistema
   depois nunca mais veria a mudança refletida, e "seguir o sistema" valeria
   por uma visita só. A gravação foi para o `toggleTheme` — só escolha de gente
   é gravada.
2. **O `index.html` tinha a regra duplicada.** Existe ali um script anti-flash,
   que roda antes do bundle, com a lógica antiga ("se não for `light`,
   escurece"). Sem acompanhar, quem usa o SO no claro veria um flash escuro em
   **toda** visita — exatamente o que aquele script existe para evitar. Ele
   precisa repetir a regra à mão porque roda antes do JS da aplicação; os dois
   lados agora apontam um para o outro em comentário, e está escrito no arquivo
   que essa cópia não tem teste que a segure.

No teste, o ciclo escolher/sair/voltar continua — agora com o SO fingindo o
tema **oposto** ao escolhido. Sem isso ele passaria pelo motivo errado, caindo
no padrão do sistema em vez de ler o que foi gravado.

E as duas linhas mortas que ontem ficaram registradas viraram remoção: o
comentário de `products.py` citando um helper que o `7371bc7` apagou, e o
`!disabled &&` do `FormDropdown` que a verificação por mutação mostrou nunca
rodar — o atributo `disabled` do `<button>` já impede o navegador de disparar o
clique.

### O serial deixa de ser único no mundo

A unicidade de número de série era global. Duas coisas erradas: empresas
diferentes podem ter aparelhos de mesmo número — fabricantes repetem séries
entre lotes e linhas — e o `409` global era um oráculo: contava ao cliente que
**outra** empresa tinha cadastrado aquele serial.

**Uma correção na minha análise, que precisa constar.** Na proposta eu descrevi
o custo do escopo por `owner_id` invertido: escrevi que dois usuários da mesma
empresa *não* poderiam cadastrar o mesmo serial. É o contrário. Com unicidade
por `owner_id`, cada colega tem o próprio escopo, então **dois usuários da mesma
empresa podem cadastrar o mesmo aparelho físico, um por cabeça**. Esse é o
**furo aceito** — o Rickelme decidiu com o trade-off já corrigido: `owner_id`
agora, porque a migration é segura e sem backfill; a evolução para escopo por
empresa/CNPJ fica na fila, **condicionada à normalização do campo CNPJ**, que
hoje é texto livre digitado no onboarding (dois usuários da mesma empresa podem
ter gravado `12.345.678/0001-90` e `12345678000190`). Rodada própria.

A migration tem **dois índices**, porque em SQL `NULL` não conflita com `NULL`:
só o composto `(owner_id, serial_number)` deixaria dois equipamentos sem dono
com o mesmo serial passarem em silêncio — e órfão é estado transitório que
alguém vai consertar, então o conflito apareceria tarde. O índice parcial
`WHERE owner_id IS NULL` fecha isso sem depender de `NULLS NOT DISTINCT`
(Postgres 15). O índice simples por serial fica, não-único: a busca de chamados
usa a coluna.

O upgrade é seguro por construção: a regra nova é estritamente mais fraca que a
antiga, então nada que existia viola o índice novo — raciocínio que dispensa
consultar produção. O **downgrade pode falhar** se, depois do upgrade, dois donos
cadastrarem o mesmo serial; é a natureza da volta e está no docstring.

**Testado num Postgres efêmero (`pgserver`), não no banco do `.env`** — que
aponta para produção. Upgrade com os três índices; mesmo dono repetindo
recusado; donos distintos aceitos; órfão × com-dono aceito; dois órfãos
recusados; downgrade recusado com duplicado entre donos e OK depois de limpar;
upgrade de volta. Dois tropeços meus no caminho, ambos antes do commit: escolhi
o `down_revision` pela data do arquivo e acertei numa revisão que já existia
(`s9n0…`) — o Alembic acusou "present more than once"; e o detector de erro do
meu script lia só stdout enquanto o `psql` mandava as violações para stderr, o
que produziu dois "inesperado" que eram, na verdade, o banco recusando
corretamente.

No código, as quatro cópias da checagem viram `_recusa_serie_duplicada`. O
`PATCH` de staff valida o **par final** (dono, serial): mover um equipamento
para um dono que já tem aquele serial não muda o serial, e um check de "o serial
mudou?" deixaria passar. A suíte mocka o banco, então o mock **emula a tabela**
— lê os parâmetros compilados da consulta e só devolve a linha se o par bater.
É o que permite provar "dois donos com o mesmo serial passa" sem Postgres.

### O chip que dizia Vencido para quem já tinha respondido

A hipótese do Rickelme estava certa, e o mecanismo era mais simples do que ela.
O `SlaChip` recebia `dueAt` e `breached` e usava cada um para uma coisa: o
**texto** vinha do relógio, a **cor** vinha do backend. Chamado respondido no
prazo e reaberto: âmbar (certo) com "Resposta: Vencido" (errado). E sem
reabertura nenhuma: respondeu às 9h, prazo às 14h, às 15h dizia Vencido.

A causa real: `sla_first_response` **não era enviado ao front**. O chip não
tinha como saber. Passou a ser exposto (leitura, sem migration), e o chip
ganhou `respondedAt` — preenchido, diz "Respondido" e para o relógio.

Por que **não** silenciar pelo `breached`, que seria o reflexo: `check_breaches`
só roda em caminhos de **escrita**, nunca na leitura nem num timer. Um chamado
que venceu há duas horas e ninguém tocou chega com `breached = false`, e a
contagem ao vivo é o único lugar que conta a verdade sobre ele. Esconder o
Vencido pela flag trocaria uma mentira por outra, na direção mais perigosa. Está
em comentário no chip e em teste.

O chip saiu de dentro da `TicketDetailPage` para `components/ui`, onde dá para
testar; verificado por mutação. A lista de chamados tinha o mesmo bug em outra
roupa — a barra de "1ª Resposta" virava "SLA Vencido" por `timeLeft <= 0`, e o
chamado respondido pelo chat, que desde o `230d670` não sai de `open`, ficava
vermelho com a resposta dada há horas. Mesmo tratamento.

**O que fica para depois, registrado:** dar ao ciclo reaberto um prazo de
resposta próprio. Hoje o chip diz "Respondido" com base no ciclo 1 — verdade,
mas não a medição que a operação vai querer um dia. Campo por ciclo.

### O Playwright ganha um lugar para rodar — com um veto no meio

Ordem combinada: seed do cliente → `e2e.yml` só com `workflow_dispatch` → duas
execuções manuais verdes → ligar o `schedule`. O arquivo já traz o bloco de
agendamento comentado com essa instrução.

O **veto do Rickelme** mudou onde o seed mora, e é o ponto mais importante da
frente: os usuários do e2e **não podem** entrar no `app/seeds.py`. Ele roda no
boot de produção (`start.sh`), e isso criaria contas de teste com senha em
texto claro conhecida no banco real. O cliente e2e vive em `app.seeds_e2e`,
módulo separado que só o workflow chama e que **se recusa a rodar em produção
antes de abrir sessão** — nem para ler. Dois testes são o contrato: em produção
levanta e não toca no banco; `app.seeds` rodado num banco vazio não cria conta
nenhuma com e-mail de teste, e o código-fonte dele não menciona e2e.

O resto do levantamento virou linha do workflow, cada uma com o motivo escrito
no arquivo: `APP_ENV=testing` porque a suíte faz ~16 logins do mesmo IP contra
um limite de 5 por 15 minutos; chaves JWT efêmeras geradas no job com `openssl`
(nenhum segredo do repositório); Redis como service mesmo o boot só avisando,
porque chat e blacklist de token usam; o cliente nasce com
`onboarding_completed`, senão o guard o joga em `/onboarding` e o spec que
espera `/403` morre no primeiro passo.

A credencial de técnico saiu do `helpers.ts` em vez de ganhar usuário: nenhum
spec loga como técnico. Um teste no backend garante que `helpers.ts` e
`seeds_e2e` têm os mesmos valores — se um lado mudar e o outro não, o e2e
falharia no login sem dizer por quê.

**Fase 3 (k6): sem mudança, e de propósito.** Teste de carga contra os
`services` de um runner do GitHub mede o runner, não a aplicação — Postgres em
container efêmero, sem volume, sem os dois workers do `start.sh`, sem a rede do
EasyPanel. O número que saísse teria aparência de medição, e isso é pior que
nenhum número. Segue aguardando staging.

### Decisões registradas, sem código

- **Guard de produção: fica como está.** O `fail-fast` do boot quando falta
  `CORS_ORIGINS` já pegou configuração errada duas vezes. O silêncio custou
  semanas; o barulho custou minutos. Não vira aviso.
- **Reunião da Helô** segue com o Rickelme. Fase 1 continua bloqueada por ela,
  sem ação técnica nossa.

### O que fica na mesa

- **`CORS_ORIGINS`, porta 8000 e SMTP** seguem no painel, com o Rickelme e o
  Erick.
- **`register` neutro (#3.1)** — quando entrar, o `BackgroundTasks` precisa ir
  junto, senão a neutralidade nasce furada pelo tempo de resposta.
- **Serial único por empresa/CNPJ** — evolução do escopo por `owner_id`, para
  fechar o furo aceito (colegas da mesma empresa duplicando o mesmo aparelho).
  Condicionada à normalização do campo CNPJ; rodada própria.
- **SLA por ciclo de reabertura** — o chip agora diz a verdade sobre o ciclo 1;
  dar prazo próprio ao ciclo reaberto é outra conversa.
- **`e2e.yml`: duas execuções manuais verdes e depois ligar o `schedule`** (o
  bloco está comentado no arquivo). O primeiro run vai dizer se a estimativa de
  8–12 min por execução bate.
- **k6 / Fase 3** aguarda staging. Não tocar.

---

## 20/08/2026 — O SLA passa a medir conversa, não clique

Primeira frente da Helô — e a única que não depende da reunião com o cliente.
O Welton desenhou o atendimento por IA em
[`2026-08-11-helo-atendimento-ia-design.md`](docs/superpowers/specs/2026-08-11-helo-atendimento-ia-design.md);
a revisão contra o código (`87dd05a`) achou um pré-requisito que ninguém tinha
previsto, porque **já estava quebrado sem a Helô**.

| Commit | O que foi feito |
|---|---|
| `230d670` | `fix:` **primeira resposta do SLA passa a exigir uma fala ao cliente** |
| `docs:` | Desenho da regra nova + fechamento |

### O indicador media o tempo até alguém clicar

`sla_first_response` era gravado em três lugares, sempre sob
`old_status == TicketStatus.open`. Como o mapa de transições só deixa `open`
virar `in_progress` ou `cancelled`, "primeira resposta" queria dizer, na
prática, **"alguém assumiu ou cancelou o chamado"**.

O levantamento dos treze caminhos (tabela completa no
[desenho](docs/superpowers/specs/2026-08-20-primeira-resposta-sla-design.md))
achou distorções nas duas direções ao mesmo tempo:

- **Dois falsos negativos, no caminho mais usado.** `chat.py` não tocava no
  SLA — zero ocorrências. Técnico que responde pelo chat sem mexer no status
  não registrava nada. Pior: o `_apply_chat_transition` nem transiciona a
  partir de `open`, então o chamado ficava parado e mudo para o indicador.
- **Três falsos positivos.** Atribuir marcava. Assumir marcava. E **cancelar
  pelo `PATCH /status` marcava** — chamado cancelado entrava no tempo médio de
  resposta com poucos segundos. Cancelar pelo `DELETE`, o outro caminho, não
  marcava: dois jeitos de cancelar, dois resultados de SLA.
- **Um buraco.** Resolver um chamado que já saíra de `open` não marcava nada.
  Atendido, resolvido, e invisível para a métrica.

### O achado que apareceu no meio do caminho

Melhor que o problema original. Nos três pontos a ordem era esta:

```
ticket.sla_first_response = now
check_breaches(ticket, now)      # ← já vê o campo preenchido
```

E `check_breaches` só avalia o prazo **enquanto `sla_first_response` é nulo**.
Um chamado assumido três dias depois do prazo saía limpo, com
`sla_response_breach = False`. A condição viva do dashboard também exige o
campo nulo, então a violação sumia dos dois lados. **Na prática, primeira
resposta atrasada quase nunca era contada como violação.**

O conserto é a ordem: `register_first_response` avalia o prazo e só então
carimba. Autocontida, a ordem nos call sites deixou de importar.

### A regra nova não menciona status nenhum

Marca a **primeira mensagem de chat de quem não é o autor do chamado**, mais a
resolução como rede de segurança — a nota de resolução é texto que o cliente
lê, e sem ela o buraco continuaria.

"Não é o autor" em vez de "é staff" foi decisão deliberada: é o mesmo critério
que o `_notify_other_party` já usa para decidir a quem notificar. Mesma
pergunta — há alguém do outro lado? —, uma só resposta no código. Cobre de
graça o admin que abre chamado interno e responde a si mesmo.

Mudança de status **não conta**, nem para `awaiting_client` manual. Se a
equipe atende por telefone, a fala tem que virar mensagem no chamado de
qualquer jeito — para o SLA e para o próximo técnico que pegar o caso.

Não olhar para status é o que torna a correção pré-requisito da Helô, e não
consequência dela: o chamado que nasce em `ai_handling` e nunca passa por
`open` funciona igual. E a mensagem da IA é excluída por dois filtros
independentes, `is_ai` e remetente nulo — o teste do remetente nulo já está no
repositório, antes de a Helô existir.

### Sem migration e sem backfill

A regra decide quando gravar; não reescreve o que já está gravado. Chamado
fechado mantém o valor, relatório antigo não muda, e chamado vivo se corrige
na próxima mensagem.

O backfill era possível — `chat_messages` tem `sender_id` e `created_at` — e
foi recusado por dois motivos. Migration roda sozinha no boot do container, e
um `UPDATE` varrendo `tickets × chat_messages` é a categoria de coisa que
derruba a API na subida, como o guard de CORS derrubou na véspera. E
**reescrever números que a equipe já viu em relatório é pior do que ter um
passado torto e datado**.

### O número vai piorar, e foi combinado antes

O card de violação de resposta sobe e o tempo médio sobe, porque o indicador
deixa de apagar violação atrasada e deixa de contar clique como conversa. Não
é regressão — é ele parando de mentir. Como o deploy é manual, a comunicação
com a equipe acontece no tempo de quem sobe.

### Fica na fila: a reabertura entrega metade do que anunciou

Conferido de passagem, e é contradição de verdade. O changelog do produto da
v1.4.0 diz que "reabrir um chamado devolve um prazo de atendimento novo, em
vez de trazê-lo de volta já vencido". O `reopen_ticket` renova só o prazo de
**resolução** — o de resposta fica no dia da abertura original.

Dá para ver na tela: o `TicketDetailPage` desenha dois chips lado a lado, e o
chamado reaberto volta com "Resolução" contando de novo e **"Resposta:
Vencido"**, permanentemente. Metade da promessa.

Não é conserto trivial, e por isso não entrou: renovar o prazo de resposta
obriga a decidir o que fazer com o `sla_first_response` do ciclo anterior —
zerá-lo apaga o único registro que existe dele, o que provavelmente pede um
campo por ciclo em vez de um campo por chamado. Decisão de produto própria.

### Testes

17 novos, nenhum dependendo do relógio: `now` é sempre injetado por parâmetro
e a função não chama `datetime.now()`. Dez sobre o núcleo puro (incluindo
resposta atrasada preservando a violação, pausa esticando o prazo e o
remetente nulo da Helô), dois nas rotas de chat e cinco de regressão — assumir,
cancelar e atribuir **não** marcam; resolver fora de `open` marca. Suíte
completa em 466 testes, cobertura 82,65%.

---

## 19/08/2026 (noite) — Terceira rodada da revisão

Um `/code-review` sobre 51 arquivos desde `154ec74` verificou token a token que
a reformatação do black (`57ca9d9`) é semanticamente idêntica e aprovou o
403→404, o `field_validator` do `APP_ENV`, o guard do
`EMAIL_VERIFICATION_ENABLED` e os testes novos do front. Sobraram três achados,
todos fechados aqui.

| Commit | O que foi feito |
|---|---|
| `a1bbd94` | `fix:` **o dummy do login dessincronizava de `BCRYPT_ROUNDS`** — a única piora que a rodada anterior introduziu, e ela veio justamente de consertar outra coisa |
| `b1ab978` | `fix:` **staff criava equipamento pertencente a staff** em `POST /equipment/my` |
| `3efb0cf` | `feat:` **seletor de dono na ProductsPage**, fechando o ciclo do `51a9cb8` |

### O knob vivo virou armadilha (`a1bbd94`)

Ligar `bcrypt_rounds` ao `pwd_context` (`b06228f`) tirou a configuração morta —
e criou uma pior: o dummy seguia fixado em 12 por literal. Medido antes de
corrigir, com `BCRYPT_ROUNDS=14`: **o e-mail desconhecido custava 486 ms e o
cadastrado 1777 ms**. O oráculo de tempo que o `f8e6013` fechou reabria maior
do que era originalmente (1 ms contra 250 ms).

O teste de paridade não pegava, e a razão importa: ele comparava o dummy com o
`pwd_context` **do processo que roda a suíte**, que nunca tem `BCRYPT_ROUNDS`
no ambiente. Afirmava 12 == 12 e passava verde enquanto produção divergia — um
teste verdadeiro sobre o ambiente errado.

Agora o import se encarrega: `_dummy_no_custo_do_contexto` compara o custo
embutido no literal com o do contexto e **só regera quando divergem**. No
caminho normal não paga bcrypt nenhum, que era o motivo de o hash ser fixo;
quem sobe os rounds paga um hash por processo, uma vez. O contrato de teste
passa a ser contra `settings.bcrypt_rounds`, não contra o contexto do processo.
Depois da correção: **1846 ms contra 1796 ms**.

### `/equipment/my` é do cliente, nos verbos que escrevem (`b1ab978`)

`POST /equipment/my` fazia `owner_id = actor.id` com qualquer perfil, então
técnico e admin criavam equipamento pertencente a staff — o mesmo estado que o
`_valida_dono` recusa com 400 nos endpoints de staff. Equipamento assim some da
listagem escopada e nunca vira chamado.

`POST`, `PATCH` e `DELETE` passam a exigir `authorize(UserRole.client)`. A
**leitura fica aberta de propósito**: se algum usuário virou staff depois de ter
sido cliente, o equipamento antigo continua existindo, e negar o `GET`
esconderia dele o que já era seu. Verificado antes que nenhuma tela quebra —
`/equipment` não tem `RoleGuard`, mas o link da sidebar é `roles: ["client"]` e
a `EquipmentPage` não ramifica por perfil; staff só chegava lá digitando a URL.

Efeito colateral saudável: o ramo de 403 para staff no `_check_equipment_owner`
virou código morto e saiu junto, com o teste que o cobria — ele passava, mas
por um motivo que deixou de existir.

### Seletor de dono (`3efb0cf`)

O `productService` omitia `owner_id` nos tipos de payload, então o backend
aceitava o campo desde `51a9cb8` e nenhum caller o enviava.

Entra um `SearchSelect` em `components/ui`, com **busca no servidor**. Um
dropdown pré-carregado não serve: `GET /users` tem `limit` máximo de 100 e
ordena por `created_at desc`, então quebraria em silêncio ao passar de 100
clientes — mostrando os 100 mais recentes, ordem que não ajuda a procurar um
nome. O componente não conhece a API (recebe `onSearch`), o que mantém `ui/`
apresentacional.

O campo aparece ao criar **e** ao editar, com "— Sem dono —": é o que conserta
os órfãos existentes um a um, sem migration. Sem backfill automático — o
sistema não tem como adivinhar dono.

Detalhe que só aparece implementando: o RED do service foi no **`tsc`**, não no
Vitest. O runtime já repassava o payload inteiro; quem barrava era o tipo.

### Fila desta rodada

- **Higiene de rota**: `/onboarding` está sob `AuthGuard` mas **fora** do
  `OnboardingGuard`, então staff consegue abrir a tela de onboarding digitando
  a URL. O bloqueio no backend (`b1ab978`) já fechou a porta que importava — a
  `OnboardingPage` chama `createMyEquipment` —, mas a rota em si continua
  aberta. Higiene, sem urgência.
- **Filtro "sem dono"** na listagem de equipamentos da ProductsPage, para o
  staff encontrar os órfãos remanescentes sem varrer página por página.

---

## 19/08/2026 — Push, ressurreição do CI e destrave do login

O push dos 24 commits da frente de segurança revelou que **o CI do main
estava vermelho desde 06/08** — e como o black rodava antes do pytest, **a
suíte do backend nunca rodava**: o gate de testes estava morto sem ninguém
perceber. Duas causas empilhadas, corrigidas em sequência, e um bug de
produção reportado pelo Rickelme no mesmo dia.

| Commit | Tipo | O que foi feito |
|---|---|---|
| `57ca9d9` | style | Reformata o backend com o black pinado (27 arquivos, zero lógica) — decisão do Rickelme; era a 1ª causa do CI vermelho |
| `4449ce2` | test | 2ª causa, revelada quando o pytest voltou a rodar: `keys/` é gitignored e o CI não tinha chaves JWT — 54 testes com `FileNotFoundError`. O conftest agora gera par RSA efêmero por sessão; `pytest` roda em máquina zerada |
| `1b3d355` | fix | **Login travado em produção** ("Confirme seu e-mail" sem e-mail chegar): a exigência era *inferida* de `SMTP_USER`/`SMTP_FROM_EMAIL` preenchidos — e o `.env.example` vem com os dois preenchidos (senha `CHANGE_ME`). Agora a adoção é explícita: `EMAIL_VERIFICATION_ENABLED` (default `false`) **e** SMTP presente; flag ligada sem SMTP recusa o boot em produção. Contas presas voltam a entrar sem mexer no banco |

Resultado: **CI verde de ponta a ponta no `4449ce2`** — o primeiro do main
desde antes de 06/08, com a suíte do backend (agora 435 testes, 82,35%)
rodando como gate de verdade.

**Fica na fila para quando o SMTP for adotado**: ligar
`EMAIL_VERIFICATION_ENABLED=true` no painel e decidir o que fazer com as
contas antigas criadas como não-verificadas (backfill ou reenvio de link).

**Aviso ao time**: a reformatação tocou 27 arquivos — trabalho local em
andamento terá conflitos cosméticos ao puxar (resolver com pull +
reaplicar `black .`). Código novo no backend deve passar pelo black antes
do commit, senão o CI volta a ficar vermelho.

### Segunda rodada da revisão (`51a9cb8` … `701df8e`)

Um segundo `/code-review`, agora sobre o diff completo contra o upstream (13
arquivos), confirmou o núcleo dos commits anteriores e trouxe seis achados mais
um fora do diff. Todos resolvidos nesta rodada.

| Commit | O que foi corrigido |
|---|---|
| `51a9cb8` | `feat:` **equipamento órfão** — staff criava equipamento sem `owner_id` e nenhum endpoint atribuía dono depois. Com o escopo por dono, esse equipamento ficava invisível ao cliente real *para sempre*: fora da listagem, barrado no `GET`, recusado no vínculo de chamado, e recadastrar batia no `409` do número de série. `owner_id` opcional entra nos endpoints de **staff**, validando que o dono existe e é cliente |
| `b06228f` | `fix:` **`BCRYPT_ROUNDS` era knob morto** — documentado no `.env.example`, lido pelo `Settings` e nunca passado ao `pwd_context`. Subir para `14` no painel não mudava nada, e a paridade de custo do hash descartável seguia dependendo de coincidência |
| `a06daa4` | `refactor:` **normalização do `APP_ENV` só existia em produção** — `is_development` e o rate limiter comparavam a string crua: `APP_ENV=Testing` num job de CI subia o limiter **ligado** contra o `redis_url`, e `Development` desligava o `/docs` calado. Vira `field_validator` no campo, com três propriedades irmãs lendo o valor já normalizado |
| `4d8fbbf` | `test:` **`_env_file=None` não isola do ambiente** — só do `.env`. Variável exportada vence o default do pydantic-settings, então quem tivesse `CORS_ORIGINS` no shell via os testes de default quebrarem. O helper passa a limpar as quatro sensíveis enquanto constrói |
| `637ad0f` | `fix:` **oráculo 403/404** — equipamento alheio devolvia `403` e inexistente `404`, o que dizia ao cliente quais ids existem. Ver a decisão revista abaixo |
| `701df8e` | `feat:` **`FORWARDED_ALLOW_IPS`** — o achado fora do diff. Ver o aviso de topologia abaixo |
| — | `docs:` este registro e o `Changelog.md`, com a entrada do escopo de equipamento movida de **Desempenho** para **Segurança**: o texto dela descreve vazamento de número de série entre clientes, e quem varresse o changelog atrás de mudanças de segurança antes de um deploy passaria batido |

O `owner_id` ficou em `EquipmentStaffCreate`/`EquipmentStaffUpdate`, herdados
dos schemas compartilhados, e **não** nos corpos aceitos pelos
`/equipment/my*`. Colocá-lo no schema comum daria ao cliente o controle do
dono, porque o `PATCH /equipment/my/{id}` aplica o corpo inteiro com `setattr`
— há dois testes só para acusar isso se alguém unificar os schemas mais tarde.
Falta a tela: o seletor de dono na `ProductsPage` não entrou nesta rodada, a
API veio primeiro.

#### Decisão revista: `404` no lugar do `403` para equipamento alheio

Na rodada anterior o `403` foi mantido por **consistência com o `403` dos
chamados**. A revisão apontou que isso deixa em pé um oráculo de existência
dentro da própria mudança feita para fechar oráculos, e o argumento novo vence:
distinguir "não é seu" de "não existe" não entrega nada ao usuário legítimo e
custa zero para fechar.

Agora, para o perfil **cliente**, a recusa sai como `404` com o mesmo texto de
um id inexistente — constante única, porque mensagens diferentes devolveriam
pelo detalhe o que o status parou de contar. Vale também para os
`/equipment/my*`. Para **staff** continua `403`: quem já enxerga o parque
inteiro pelo `GET /equipments/{id}` não ganha nada com o `404`, que ali seria
só uma resposta enganosa.

Os **chamados seguem como estão**. Aplicar o mesmo critério lá é refactor
maior, com mais call sites e mais perfis envolvidos — fica na fila.

> ⚠️ **TOPOLOGIA RESPONDIDA — a porta 8000 do backend ESTÁ PUBLICADA na
> internet** (confirmado pelo Rickelme em 19/08/2026). **Não definir
> `FORWARDED_ALLOW_IPS` enquanto isso for verdade.**
>
> O contexto: o `start.sh` sobe o uvicorn sem autorizar proxy nenhum, e o
> default do uvicorn (`FORWARDED_ALLOW_IPS=127.0.0.1`) faz o
> `get_remote_address` do rate limiter enxergar o IP do **proxy**, não o de
> quem chamou. Para o tráfego que entra pelo proxy, o
> `RATE_LIMIT_LOGIN=5/15minutes` é hoje **um balde único**: cinco senhas
> erradas de qualquer pessoa travam o login de todos os usuários.
>
> Ligar a variável resolveria isso — e, com a porta publicada, abriria coisa
> pior: quem chamasse a porta direto forjaria o `X-Forwarded-For` e **furaria o
> rate limit por completo**, uma chave por requisição. Trocar um limite fraco
> por nenhum limite não é troca.
>
> **Plano, nesta ordem — a ordem é a correção:**
>
> 1. **Fechar a publicação da porta 8000 no EasyPanel**, deixando só o proxy
>    alcançar o container. Conferir antes que nada legítimo dependa da porta
>    direta — o front chama a API pelo domínio, via proxy.
> 2. **Só então** definir `FORWARDED_ALLOW_IPS=*` no painel. Com a porta
>    fechada, o único que consegue mandar `X-Forwarded-For` é o próprio proxy,
>    e o rate limit passa a valer por IP real.
>
> Inverter os passos é o cenário ruim descrito acima. Enquanto o passo 1 não
> acontecer, o balde global fica — é o estado seguro dos dois.
>
> O passo 1 vale por si, além do rate limit: com a porta aberta, a API é
> alcançável passando por fora do proxy, e com ela tudo o que o proxy faz na
> frente.
>
> O `start.sh` de propósito não ganhou flag: o uvicorn já lê essa variável do
> ambiente, e uma flag criaria duas fontes que podem divergir. O boot em
> produção avisa no log enquanto a variável estiver vazia — o aviso é
> **esperado** até o passo 2, não é regressão.

### Rodada de testes do front (`0cd019a` … `3ae937c`)

Um test review do frontend (skill `help-test-review`) mapeou a suíte Vitest
contra o código e priorizou os gaps por risco. O review corrigiu de passagem
uma informação da própria skill: **Vitest RODA no CI** desde `1583b8b` — teste
de front quebrado bloqueia merge. O que segue fora do CI é só Playwright e k6.

| Commit | O que entrou |
|---|---|
| `0cd019a` | `test:` **interceptor do axios** (`api.ts`, era 0%) — o código que governa toda requisição: Bearer, refresh no 401, fila de chamadas concorrentes durante o refresh. 11 casos cobrindo os três guards anti-loop, os dois desfechos de logout forçado e a concorrência (dois 401 → UM refresh). Dois mutantes nos guards confirmaram que a suíte pega regressão |
| `f51685f` | `test:` **guards de rota** (`AuthGuard`, `RoleGuard`, `OnboardingGuard`, eram 0% e invisíveis) — `src/components/layout/` estava fora do `include` de cobertura do Vitest, então o relatório nem sabia que a camada existia. 10 casos + o include corrigido no `vite.config.ts` |
| `d792686` | `test:` **equipmentService** (era 0%) — superfície de front da mudança de dono de equipamento. Fixa o `product_id` na query do POST, o desempacote de `items`, o `is_active=false` na query e a limpeza de máscara do CNPJ/CEP |
| `2db8dfa` | `fix:` **"Equipment not found" sem tradução** — achado do review cruzando a mudança `637ad0f` do backend com o `TRANSLATIONS` do `apiError.ts`: desde o 403→404, essa é a mensagem que o cliente recebe para equipamento alheio, e o toast mostrava a string crua em inglês. A entrada antiga `Not your equipment` cobria o fluxo que deixou de existir |
| `6049181` | `test:` **toastError** (caminho de erro da aplicação inteira, era 0%) e os ramos de objeto/array do `cn` |
| `3ae937c` | `chore:` `frontend/coverage/` no `.gitignore` — o relatório do `test:coverage` ficava commitável e o eslint tropeçava nos js gerados |

Suíte do front: **192 → 229 testes** (30 arquivos), tudo verde; lint e
typecheck limpos (os 3 warnings restantes do eslint pré-existem em
`ChatPanel`, `ThemeContext` e `GroupsPage`). Cobertura da parte medida:
50,6% → 54,4% — com `api.ts`, os 3 guards, `equipmentService`, `toastError` e
`utils` em 100%.

**Deixado de fora de propósito:** os serviços 0% restantes (`groupService`,
`reportService`, `chatService`, `calendarService`, `auditService`,
`dashboardService`, `slaService`, `tagService`) são wrappers finos de
`api.get/post` — testá-los daria cobertura sem dar confiança; cobrir apenas
quando ganharem transformação (o padrão `withAvatarUrl` do `userService`).
Componentes de apresentação (`Alert`, `Avatar`, `Card`, `Textarea`) idem. Os
que têm lógica real e seguem descobertos: `FilterSelect`, `FormDropdown` e
`ThemeContext` — fila de prioridade baixa.

---

## 18/08/2026 — Auditoria de segurança, correções e CI

Primeira rodada com as skills do projeto: auditoria de segurança completa,
correção dos dois achados graves e primeira fase do reforço de testes no CI.

### Commits

| Commit | Tipo | O que foi feito |
|---|---|---|
| `1d6e766` | docs | 11 skills `help-*` em `.claude/skills/` — revisão de código, segurança, endpoints, migrations, env, testes, deploy, commit, PR, refactor e changelog (adicionadas via `git add -f`, pois `.claude/` é gitignored) |
| `0c7164f` | fix | 🟠 Fecha XSS armazenado na Base de Conhecimento — `frontend/src/lib/markdown.ts` sanitiza o HTML renderizado com DOMPurify; 7 testes provam a neutralização |
| `464d9be` | fix | 🟠 Liga rate limiting (slowapi, 5/15min) nos endpoints de autenticação — login, register, forgot-password e resend-confirmation; teste prova o 429 e que o limiter desligado (padrão em `APP_ENV=testing`) não afeta a suíte |
| `1583b8b` | ci | Vitest no job do frontend, entre o typecheck e o build (Fase 1 do plano de testes no CI) |
| `ec3a86b` | docs | Este registro de mudanças e o [Changelog.md](Changelog.md) do repositório |
| `724322f` | fix | 🟡 Fecha o achado #5 — `GET /products/{id}/equipments` e `GET /equipments/{id}` deixam de vazar equipamento (e número de série) entre clientes: listagem filtrada por dono e 403 no detalhe alheio. Escrito em TDD — os testes falharam antes da correção |
| `f8e6013` | fix | 🟡 Fecha o achado #3.2 — o login pulava o bcrypt para e-mail inexistente e o tempo de resposta (~1 ms contra ~250 ms) denunciava quais contas existem. Passa a verificar contra um hash descartável de 12 rounds |
| `8ab84c8` | fix | 🟡 Fecha o achado #4 — o boot em `APP_ENV=production` passa a exigir `CORS_ORIGINS` com domínio real e a recusar `*`, ao lado da validação que já existia para a `SECRET_KEY` |

### Auditoria (Passo 1)

Varredura estática dos 17 routers do backend:

- **Nenhuma rota desprotegida** — o padrão de alias enganava o grep, mas a
  verificação manual confirmou a cobertura de autenticação.
- **2 achados 🟠** (graves): XSS armazenado na KB e ausência de rate limiting
  na autenticação — ambos confirmados e corrigidos nesta mesma rodada.
- **2 achados 🟡** (médios) e **1 🔵** (informativo) — registrados na fila
  abaixo.
- Controles corretos reconhecidos: `/files/{token}` com JWT assinado e guarda
  de path traversal; escopo do client consistente; resposta neutra no
  login/forgot; anonimização LGPD preservando o AuditLog.

### Verificação

- Backend: **399 testes passando**, cobertura **81,90%** (gate de 80% mantido).
  `pytest` roda verde **sem variável de ambiente no comando** desde o
  `e4ec7f2`.
- Frontend: **192 testes passando**, `tsc` e `ruff` limpos.
- Todo conserto veio acompanhado do teste que o prova.

### Achado #5 — equipamento escopado por dono (`724322f`)

Fechado ainda nesta data, depois da rodada inicial, com o ciclo invertido a
pedido: **os testes vieram antes da correção e falharam** (`200` onde se
esperava `403`), provando que exercitavam a lacuna real.

- **Regra**: cliente vê apenas o próprio equipamento; equipamento **sem dono**
  também é negado (*fail closed*, mesmo critério do `/equipment/my`). Staff
  (admin e técnico) continua com acesso total, porque precisa para suporte.
- **403, não 404** — consistência com o `_check_ticket_access` de tickets e
  anexos. A preocupação de enumeração está registrada no #3 e será tratada lá.
- **Nenhuma tela mudou**: verificado antes de codificar que o cliente só usa
  `/equipment/my*`, que a `ProductsPage` (única consumidora da listagem) está
  sob `RoleGuard` de staff e que o GET singular não é consumido pelo front.
- `test_get_equipment` foi atualizado para ator staff: como cliente, ele
  afirmava justamente o acesso que esta correção fecha.

### Investigado e documentado (sem esconder)

- **`black --check .` reprova no main** — não é culpa do `auth.py`: com o
  `black==25.1.0` pinado, 24 arquivos reprovam. Causa: muitas linhas acima de
  100 caracteres que o black quebraria, e o ruff do projeto ignora `E501`
  (`pyproject.toml`) — então ruff passa e black não. Decisão de time pendente:
  reformatar tudo de uma vez ou alinhar ruff/black. Os arquivos novos desta
  rodada são black-limpos.

  **Resolvido em 19/08/2026 (`57ca9d9`)**: o primeiro push da frente revelou a
  gravidade real — **o CI do main estava vermelho desde 06/08** (seis runs
  seguidos), e como o black roda antes do pytest no job, **a suíte do backend
  nunca rodava no CI**: o gate de testes estava morto sem ninguém perceber.
  Decisão do Rickelme: reformatação mecânica com o black pinado — 27 arquivos,
  zero mudança de lógica, suíte verde (431/82,34%) e ruff limpo depois.

### Achados #3.2 e #4 — enumeração por tempo e CORS (`f8e6013`, `8ab84c8`)

Mesma disciplina do #5: investigação primeiro, aprovação, testes falhando
antes da correção.

**#3.2 — tempo de resposta do login.** A mensagem de erro já era neutra, mas o
relógio não: com e-mail inexistente o `or` curto-circuitava, o bcrypt nunca
rodava e a resposta voltava em ~1 ms contra ~250 ms de um e-mail cadastrado
(`BCRYPT_ROUNDS=12`). Agora a senha é conferida contra um hash descartável
(`DUMMY_PASSWORD_HASH`, 12 rounds, em `app/core/security.py`) e os dois
caminhos custam o mesmo. **O teste não cronometra nada** — medir tempo seria
instável; ele afirma que a verificação de senha roda também no caminho do
usuário inexistente, e falha se alguém reintroduzir o curto-circuito.

**#4 — CORS.** O boot em `app_env=production` passa a recusar `CORS_ORIGINS`
apontando para localhost/127.0.0.1 ou contendo `*`, ao lado da validação da
`SECRET_KEY`. O que motivou o rigor: o `frontend/nginx.conf` **não faz proxy**
para a API, então o navegador fala com outro domínio e o CORS é obrigatório —
com o default, o front ficaria bloqueado sem nenhum erro no backend.

> ⚠️ **Dependência de ambiente no deploy:** o boot de produção agora depende de
> **`CORS_ORIGINS`** (com o domínio real do front), de **`FRONTEND_URL`** e de
> **`APP_ENV`**. Hoje as duas primeiras existem no EasyPanel — confirmado antes
> da mudança —, mas **recriar o serviço sem elas derruba a API na subida**, com
> o container reiniciando em loop. Se algum dia o serviço for recriado do zero,
> configure-as antes do primeiro boot.
>
> Vale também para **migração avulsa**: `alembic/env.py` instancia `Settings`,
> então rodar `alembic upgrade` num shell de produção sem essas variáveis falha
> do mesmo jeito — não é só o boot da API.

Registrado como possibilidade futura, sem ação nesta rodada: o
`CORSMiddleware` usa `allow_credentials=True`, dispensável porque a
autenticação é por Bearer token no header, não por cookie. Remover reduziria
superfície, mas mexe em comportamento de rede.

### Correções da revisão de código (`e4ec7f2` … `53312aa`)

Um `/code-review` profundo sobre os commits locais confirmou que os fixes
funcionam como testados, mas achou bordas que valia fechar antes do push,
enquanto o histórico ainda era local.

| Commit | O que foi corrigido |
|---|---|
| `e4ec7f2` | `test:` **suíte dependia do `.env` local** — `pytest` na máquina de quem desenvolve pegava `APP_ENV=development` e subia o rate limiter **ligado**, fazendo os testes de login competirem com o limite de 5/15min. Verde no CI, intermitente local. Agora um `conftest.py` fixa o ambiente antes dos imports, e `pytest` sem env explícito roda verde |
| `72f31bc` | `fix:` **bcrypt no event loop** — o mais sério: `verify_password` é síncrono (~250 ms) e travava o loop, com todas as requisições em voo; o hash de custo igualado tinha estendido o bloqueio ao caminho do e-mail inexistente. Vai para `run_in_threadpool`, e os dois pontos de verificação viraram um |
| `ef636fe` | `fix:` **cinco bordas do guard de produção** — lista vazia passava (`any()` sobre lista vazia é falso); `APP_ENV=Production`/`prod` pulava **todas** as validações, inclusive a da `SECRET_KEY`; o formato JSON não fazia strip e estourava `JSONDecodeError` cru; `localhost` como substring barrava domínio legítimo e deixava passar `[::1]`/`0.0.0.0` (agora compara o host via `urlparse`); e `FRONTEND_URL` ganhou o mesmo guard |
| `9634d7e` | `test:` **paridade de custo do hash descartável** — os 12 rounds batiam por coincidência (`settings.bcrypt_rounds` nunca foi aplicado ao `pwd_context`). Se o dummy ficar mais barato, a enumeração por tempo reabre sem nenhum teste perceber; agora é contrato |
| `2ad773c` | `refactor:` **recusa de equipamento alheio unificada** — o check de dono estava inline em três endpoints, e o 403 mais novo divergia no texto. Vira `_check_equipment_owner`, no espírito do `_check_ticket_access`, sem ampliar permissão: `/equipment/my` segue estrito até para admin |
| `53312aa` | `test:` limpeza — harness duplicado que pagava dois bcrypts reais, e mock que decidia o retorno pela ordem das chamadas |
| `751bfeb` | `fix:` **bcrypt no event loop nos endpoints restantes** — o mesmo defeito do `72f31bc` nos pontos que sobraram: `register`, `reset-password`, `POST /users` e `change-password`. Cinco chamadas, quatro endpoints, todas para `run_in_threadpool` |

O `reset-password` não estava na lista da revisão: apareceu ao varrer todos os
call sites de bcrypt antes de corrigir, e entrou porque é o mesmo defeito. O
espião de thread virou utilitário no `conftest.py`, agora que três arquivos de
teste precisam dele.

### Fila para a próxima rodada

Decisões de produto levantadas pela revisão, registradas sem correção:

- **Unicidade global de número de série** — o `409` do `POST`/`PATCH
  /equipment/my` responde por seriais de qualquer dono, então serve de oráculo:
  dá para descobrir se um serial existe no sistema. Decidir primeiro a regra de
  negócio: serial é único global, ou a unicidade deve ser por dono?
- ~~**Equipamento sem dono fica órfão**~~ — **API resolvida em `51a9cb8`**
  (`owner_id` opcional nos endpoints de staff). Falta a **tela**: seletor de
  dono na `ProductsPage`, para o staff atribuir sem chamar a API na mão.
- **Oráculo de timing em `forgot-password`/`resend-verification`** — o envio de
  e-mail é síncrono e só acontece no ramo da conta existente, então o tempo de
  resposta vai denunciar quais e-mails têm conta **quando o SMTP entrar**.
  Correção natural: `BackgroundTasks`. Agrupar com a rodada do SMTP/#3.1.
- ~~`hash_password` e `verify_password` fora do login~~ — **resolvido em
  `751bfeb`** (aprovado depois de registrado aqui).

- 🟢 **#3.1 Register neutro — aprovado em desenho, aguardando SMTP em
  produção.** O SMTP ainda não está configurado, e sem ele a resposta neutra
  criaria um beco sem saída: o usuário legítimo que digitasse um e-mail já
  cadastrado ficaria sem conta e sem aviso, porque o e-mail de "você já tem
  conta" não sairia. O `409` do register fica como está por enquanto. Quando o
  SMTP entrar, a implementação **já está pré-autorizada** neste formato, sem
  rediscutir UX: resposta `201` neutra + tela "Falta um passo" (que já existe
  em `RegisterPage.tsx`) + e-mail "você já tem conta"; sai o bloco
  `if (status === 409)` do front.
- **Recusa por dono nos chamados** — o `403` de `_check_ticket_access` tem o
  mesmo formato de oráculo que o de equipamentos acabou de perder. Aplicar o
  mesmo critério lá é refactor maior, com mais call sites e mais perfis
  envolvidos; fica para uma rodada própria.
- **CI Fase 2/3** — Playwright em `e2e.yml` separado (workflow_dispatch +
  noturno) e k6 contra staging; proposta escrita, aguardando decisão de
  investir no ambiente.
