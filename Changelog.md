# Changelog — HelpHS (repositório)

Changelog técnico, para desenvolvedores. O changelog do **produto** — o que o
cliente final vê dentro do sistema — vive em
`frontend/src/data/changelog.ts` e é mantido pela skill
`help-changelog-update`; este arquivo não o substitui.

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/).
Datas em DD/MM/AAAA.

## [Não publicado]

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

### Desempenho

- Login não bloqueia mais o event loop (`72f31bc`): o bcrypt, síncrono e de
  ~250 ms, passou a rodar em thread separada — antes, cada tentativa de login
  travava todas as requisições em voo, e a defesa contra enumeração por tempo
  havia estendido esse custo ao caminho do e-mail inexistente.
- Mesma correção nos demais endpoints que mexem com senha (`751bfeb`):
  cadastro, redefinição de senha por e-mail, criação de usuário pelo staff e
  troca de senha — nenhum deles trava mais a API enquanto calcula o hash.
- Equipamentos escopados por dono para o perfil cliente (`724322f`):
  `GET /products/{id}/equipments` passa a filtrar por `owner_id` e
  `GET /equipments/{id}` devolve 403 para equipamento de outro dono — ou sem
  dono (*fail closed*). Antes, qualquer autenticado lia o número de série do
  equipamento de qualquer cliente. Staff mantém acesso total.

### CI
- Vitest passou a rodar no job do frontend, entre o typecheck e o build
  (`1583b8b`).
- Suíte do backend deixou de depender do `.env` local (`e4ec7f2`): um
  `conftest.py` fixa `APP_ENV=testing` antes dos imports, então `pytest` roda
  verde sem variável no comando. Antes, quem rodasse localmente subia o rate
  limiter ligado e via falhas que o CI não tinha.

### Corrigido
- Build do frontend quebrado por typecheck que não checava nada (`882662b`).

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
