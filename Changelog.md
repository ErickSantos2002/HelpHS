# Changelog — HelpHS (repositório)

Changelog técnico, para desenvolvedores. O changelog do **produto** — o que o
cliente final vê dentro do sistema — vive em
`frontend/src/data/changelog.ts` e é mantido pela skill
`help-changelog-update`; este arquivo não o substitui.

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/).
Datas em DD/MM/AAAA.

## [Não publicado]

### Segurança
- O hash descartável do login passa a acompanhar `BCRYPT_ROUNDS` sozinho
  (`a1bbd94`). Ligar a variável ao `pwd_context` na v1.7.0 deixou o knob vivo e
  criou uma armadilha: o dummy seguia fixado em 12 por literal, então
  `BCRYPT_ROUNDS=14` no painel fazia o e-mail desconhecido custar 486 ms e o
  cadastrado 1777 ms — o oráculo de tempo reabria **maior** do que era antes de
  ser fechado. O teste de paridade não pegava porque comparava contra o
  contexto do processo de teste, que nunca tem a variável no ambiente. Agora o
  import compara o custo embutido no literal com o do contexto e só regera
  quando divergem: o caminho normal não paga bcrypt nenhum.
- `POST`, `PATCH` e `DELETE /equipment/my*` passam a exigir perfil `client`
  (`b1ab978`). Com qualquer autenticado, staff criava equipamento pertencente a
  staff — o mesmo estado que os endpoints de staff recusam com `400`, invisível
  a todo cliente e impossível de vincular a chamado. A **leitura** fica aberta
  de propósito, para não esconder equipamento legado de quem virou staff depois
  de ter sido cliente.

### Adicionado
- Seletor de dono no cadastro de equipamento pela tela de Produtos
  (`3efb0cf`), fechando o ciclo do `51a9cb8`: o backend aceitava `owner_id`
  desde então, mas o `productService` omitia o campo e o equipamento continuava
  nascendo órfão. Novo componente `SearchSelect` com busca no servidor — um
  dropdown pré-carregado quebraria em silêncio ao passar de 100 clientes, que é
  o teto de `GET /users`. O campo aparece ao criar **e** ao editar, com
  "— Sem dono —", o que também conserta os órfãos existentes um a um.

### Documentação
- Guia de desenvolvimento local (`f27f38c`, `3485092`) e mini-Redis de dev em
  `backend/scripts/` (`5fc7562`); skill de test review atualizada sobre o
  Vitest no CI (`b1f10b7`).

## [v1.7.0] — 19/08/2026

Fechada com o deploy de 19/08 (backend e frontend). Versão correspondente no
changelog do produto: `docs: changelog da v1.7.0` (`1c0399d`).

### Segurança
- Sanitização com DOMPurify do markdown renderizado da Base de Conhecimento,
  fechando XSS armazenado (`0c7164f`).
- Rate limiting com slowapi (5 tentativas / 15 min) nos endpoints de
  autenticação: login, register, forgot-password e resend-confirmation
  (`464d9be`). Desligado por padrão sob `APP_ENV=testing`.
- Login deixa de vazar, pelo tempo de resposta, quais e-mails têm conta
  (`f8e6013`): e-mail inexistente passa a ser conferido contra um hash
  descartável de 12 rounds, igualando o custo dos dois caminhos.
- Boot em `APP_ENV=production` passa a exigir `CORS_ORIGINS` com o domínio real
  do front e a recusar `*` (`8ab84c8`) — antes, a ausência da variável fazia a
  API subir em silêncio com origem de desenvolvimento. **Recriar o serviço sem
  `CORS_ORIGINS`, `FRONTEND_URL` e `APP_ENV` impede o boot** (vale também para
  `alembic upgrade` avulso, que instancia as mesmas configurações).
- Guard de produção endurecido (`ef636fe`): lista de origens vazia passava a
  valer como configuração válida; `APP_ENV=Production`/`prod` desligava **todas**
  as validações, inclusive a da `SECRET_KEY`; `[::1]` e `0.0.0.0` escapavam do
  filtro de loopback enquanto um domínio legítimo contendo "localhost" era
  barrado; `FRONTEND_URL` — que monta os links dos e-mails — passou a ser
  validada igual.
- Paridade de custo do hash descartável do login virou contrato de teste
  (`9634d7e`): se ele ficar mais barato que os hashes reais, a enumeração por
  tempo reabre.
- Equipamentos escopados por dono para o perfil cliente (`724322f`):
  `GET /products/{id}/equipments` passa a filtrar por `owner_id` e
  `GET /equipments/{id}` recusa equipamento de outro dono — ou sem dono
  (*fail closed*). Antes, qualquer autenticado lia o número de série do
  equipamento de qualquer cliente. Staff mantém acesso total.
- A recusa acima deixa de denunciar o que existe (`637ad0f`): para o cliente
  ela sai como `404`, com o mesmo texto de um id inexistente, em vez do `403`
  que confirmava a existência do equipamento. Vale também para os
  `/equipment/my*`. Para staff continua `403`, que já enxerga o parque inteiro.
- `BCRYPT_ROUNDS` deixou de ser configuração morta (`b06228f`): a variável
  estava documentada e lida, mas nunca chegava ao `pwd_context` — quem subisse
  com `14` no painel não mudava nada. O teste de paridade do hash descartável
  passou a comparar contra o custo efetivo, então subir os rounds sem regerar
  o dummy fica vermelho na suíte.
- `FORWARDED_ALLOW_IPS` passa a existir como configuração explícita
  (`701df8e`), com aviso no boot de produção quando está vazia. Sem ela, atrás
  de um proxy o rate limit de login enxerga sempre o IP do proxy e vira um
  limite único para todos os usuários. **Ligar exige confirmar a topologia
  antes** — ver `mudanças.md`.
- `APP_ENV` normalizado na origem (`a06daa4`): a tolerância a caixa e espaço
  valia só no ramo de produção, então `APP_ENV=Testing` num job de CI subia o
  rate limiter ligado contra o Redis e `Development` desligava o `/docs` em
  silêncio.

### Adicionado
- Staff pode atribuir o dono do equipamento (`51a9cb8`): `owner_id` opcional no
  `POST /products/{id}/equipments` e no `PATCH /equipments/{id}`, recusando com
  `400` quem não existe ou não é cliente. Sem isso o equipamento cadastrado
  pela tela de Produtos nascia órfão e ficava assim — invisível ao cliente
  real, sem poder virar chamado e sem poder ser recadastrado, porque o número
  de série já estava tomado. O campo **não** existe nos corpos aceitos pelos
  `/equipment/my*`. Falta a tela (seletor de dono na ProductsPage).

### Desempenho

- Login não bloqueia mais o event loop (`72f31bc`): o bcrypt, síncrono e de
  ~250 ms, passou a rodar em thread separada — antes, cada tentativa de login
  travava todas as requisições em voo, e a defesa contra enumeração por tempo
  havia estendido esse custo ao caminho do e-mail inexistente.
- Mesma correção nos demais endpoints que mexem com senha (`751bfeb`):
  cadastro, redefinição de senha por e-mail, criação de usuário pelo staff e
  troca de senha — nenhum deles trava mais a API enquanto calcula o hash.

### CI
- Vitest passou a rodar no job do frontend, entre o typecheck e o build
  (`1583b8b`).
- Backend reformatado com o black pinado (`57ca9d9`), devolvendo o CI ao verde:
  o Black format check reprovava no main desde 06/08 e, por rodar antes do
  pytest, impedia a suíte do backend de rodar — o gate de testes estava morto
  sem ninguém perceber. Reformatação mecânica, sem mudança de lógica.
- Chaves JWT efêmeras geradas pelo conftest (`4449ce2`): com o pytest de volta
  no CI, 54 testes que assinam RS256 morriam com `FileNotFoundError` porque
  `keys/` é gitignored e nada as gerava. Par RSA por sessão em diretório
  temporário — `pytest` roda em máquina zerada, e a suíte nunca toca as chaves
  reais do dev. Primeiro CI verde de ponta a ponta desde antes de 06/08.
- Suíte do backend deixou de depender do `.env` local (`e4ec7f2`): um
  `conftest.py` fixa `APP_ENV=testing` antes dos imports, então `pytest` roda
  verde sem variável no comando. Antes, quem rodasse localmente subia o rate
  limiter ligado e via falhas que o CI não tinha.
- Testes de configuração deixaram de depender das variáveis exportadas no
  shell (`4d8fbbf`): o `_env_file=None` calava o `.env`, mas não o ambiente —
  quem tivesse `CORS_ORIGINS` exportado, o caso de dentro dos containers de dev
  e staging, via os testes de default quebrarem sem ter mexido em nada.
- Suíte do front reforçada nos pontos de maior risco (`0cd019a` … `6049181`,
  192 → 229 testes): o interceptor do axios — refresh no 401, guards anti-loop
  e fila de chamadas concorrentes — saiu de 0% para 100%, junto com os três
  guards de rota (`AuthGuard`/`RoleGuard`/`OnboardingGuard`), o
  `equipmentService`, o `toastError` e os ramos restantes do `cn`.
  `src/components/layout/` entrou no `include` de cobertura do Vitest, que não
  enxergava a camada; `frontend/coverage/` entrou no `.gitignore` (`3ae937c`).

### Corrigido
- Build do frontend quebrado por typecheck que não checava nada (`882662b`).
- Toast em inglês para o cliente ao tentar equipamento alheio ou inexistente
  (`2db8dfa`): com a recusa por dono virando `404` (`637ad0f`), a mensagem que
  chega é "Equipment not found" — e ela não estava no dicionário de traduções
  do `apiError.ts`. A entrada antiga cobria o fluxo que deixou de existir.
- Login travava com "Confirme seu e-mail" sem nenhum e-mail chegar (`1b3d355`):
  a exigência de confirmação era inferida de `SMTP_USER`/`SMTP_FROM_EMAIL`
  preenchidos — e o `.env.example` vem com os dois preenchidos. A adoção agora
  é explícita via `EMAIL_VERIFICATION_ENABLED` (default `false`) junto do SMTP;
  em produção, flag ligada sem SMTP recusa o boot. Contas criadas presas voltam
  a entrar sem intervenção no banco.

### Documentação
- 11 skills `help-*` de revisão, segurança e deploy em `.claude/skills/`
  (`1d6e766`).
- Desenho do atendimento por IA (Helo) em 3 fases (`9f0aec1`).

## [v1.6.0] — 10/08/2026

### Adicionado
- Vários equipamentos por chamado: N:N entre ticket e equipamentos, com busca
  pelo número de série de qualquer aparelho vinculado e sugestão de artigos
  considerando todos os produtos envolvidos (`b58bfd8`).

## [v1.5.0] — 07/08/2026

### Adicionado
- Pergunta de recomendação (1 a 10) na pesquisa de satisfação e card
  Recomendação nos relatórios (`58f6773`).

## [v1.4.0] — 07/08/2026

### Adicionado
- Ciclo de encerramento do chamado (RN-005 e RN-006): reabertura pelo cliente
  em até 5 dias úteis e fechamento automático após 3 dias úteis sem
  manifestação, com prazo de SLA renovado na reabertura (`0e00a31`).

### Corrigido
- Chat espremido quando a pesquisa de satisfação aparecia no chamado.
- Tempo médio de resolução contava os dias de espera até o fechamento.
- Convite de avaliação era enviado duas vezes ao resolver o chamado.

## [v1.3.0] — 06/08/2026

### Adicionado
- Confirmação de e-mail no cadastro e recuperação de senha, com tokens,
  e-mails transacionais e telas próprias (`79469a6`, `b1a15e4`, `03830df`).
- Armazenamento de anexos e avatares em disco com volume, substituindo o
  MinIO (`8f93b37`).
- Visualização de anexo no navegador sem download (`84be869`).
- Produto e equipamento visíveis no ticket (`04e01c2`); busca de tickets pelo
  número de série (`3b0cd45`).

### Corrigido
- Anexos escolhidos na abertura do chamado eram descartados (`d44351d`).
- Base de conhecimento quebrava quando a API não mandava `products`
  (`6f7440c`).

## [v1.2.0] — 05/08/2026

### Adicionado
- Base de conhecimento por produto: vínculo artigo–produto, sugestões por
  produto/categoria do ticket, aba de KB no chamado e filtro por produto
  (`d752431`).
- Qualquer técnico pode concluir e responder qualquer ticket (`986d48d`).
- 16ª cor na paleta da agenda (`0d16819`).

### Corrigido
- Etiquetas do ticket legíveis e sem vazar da coluna (`49e6986`).

## [v1.1.0] — 04/08/2026

### Adicionado
- Respostas rápidas no chat com atalho `/` e página de gestão (`9f60877`).
- Técnico pode excluir comentários na base de conhecimento (`bfebbfc`).
- CNPJ e CEP obrigatórios no cadastro do cliente, com validação (`eb08065`).
- Paleta fixa de cores na agenda (`2a300e4`); mensagens de erro explicativas
  (`639bc2d`).

### Corrigido
- Escala do CSAT unificada em 1 a 10 (`d8fd1a2`).
- Ortografia, encoding corrompido e bug de hooks na KB (`b88ac2d`).
- Suíte do backend recuperada: 37 falhas → 0 (`fae7b95`); pipeline devolvido
  ao verde com ruff e cobertura de 80% (`98fd0e6`).

## [v1.0.0] — 20/05/2026

- Acesso completo de técnicos a Grupos, Usuários, Produtos e Etiquetas;
  interface responsiva para mobile e tablet; detalhes de equipamentos; audit
  logs adaptados para tablet.

## [v0.9.0] — 01/05/2026

- Módulo de Audit Logs; SLA por prioridade com alertas; etiquetas coloridas;
  performance do dashboard; correção de notificações no Safari.

## [v0.8.0] — 15/04/2026

- Base de Conhecimento com busca; gestão de grupos e empresas; modo
  escuro/claro; relatórios com gráficos.
