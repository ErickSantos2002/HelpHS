# F1-B-04c — sequência transacional do chat (notas da sessão)

Arquivo exclusivo desta frente. O `Changelog.md`, o `frontend/src/data/changelog.ts`
e o `docs/decisoes-e-regras.md` NÃO foram tocados por haver sessões paralelas;
o texto abaixo é para quem consolidar. Estratégia escolhida pela Sessão 0:
**B — número atribuído pela aplicação, no fim da transação**.

## O defeito

`created_at` é carimbado no INSERT, não no commit. Uma mensagem que fica com a
transação aberta (a do cliente, enquanto a Helô responde) comita DEPOIS de uma
carimbada mais tarde. Quem sincroniza por "depois do último `created_at` que vi"
não a acha nunca. Na prova de conceito, 6 de 6.

## O desenho

- `tickets.chat_seq BIGINT NOT NULL DEFAULT 0` — o contador do chamado.
- `chat_messages.seq BIGINT NULL` — o número da mensagem; nulo no legado.
- `uq_chat_messages_seq` — único em `(ticket_id, seq)` onde `seq IS NOT NULL`.
- `app/services/chat_sequencia.py::numera_mensagens_do_chat(db)` — chamado
  IMEDIATAMENTE antes do commit. Um evento de sessão anota cada `ChatMessage`
  que fica persistente; o helper faz `UPDATE tickets SET chat_seq = chat_seq + n
  ... RETURNING` e numera as anotadas em ordem de gravação. Mensagem de SAVEPOINT
  desfeito (a corrida da chave idempotente) não é numerada.
- Por que a ordem é a do commit: o UPDATE trava a linha do chamado até o commit;
  outro envio no mesmo chamado espera e, em READ COMMITTED, relê o valor já
  comitado. Número maior ⇒ commit depois. Rollback desfaz contador e mensagem
  juntos: não há buraco.

## Ordem global dos bloqueios

1. **Usuário antes de chamado.** Todo `_trava_usuario`/`_trava_para_alterar_conta`
   de `users.py` trava o usuário primeiro e não toca chamado (conferido).
2. **O contador é o ÚLTIMO bloqueio do envio, e nunca antes da Helô.** Durante a
   Helô a linha do chamado está livre (teste com `FOR NO KEY UPDATE NOWAIT`).
3. **Entre chamados, id crescente** (o helper ordena).

O que NÃO é ciclo hoje, mas está escrito para não virar: o envio põe `FOR KEY
SHARE` no remetente e nos destinatários de aviso (FKs) e depois `NO KEY UPDATE`
no chamado (status, contador). Isso é compatível com qualquer UPDATE comum de
usuário; só conflita com `FOR UPDATE`, `DELETE` ou troca de coluna-chave
(`users.email`) de quem já travou o chamado antes. Nenhum caminho do código faz
isso hoje. Há ordens chamado→usuário PRÉ-EXISTENTES dentro do próprio envio (a
escalada da Helô atualiza o chamado antes dos avisos da equipe; a primeira
resposta do técnico é autoflush antes do aviso): não formam ciclo com o código
atual.

**Deadlock (40P01) ou serialização (40001):** o banco desfaz a transação inteira.
Não há repetição automática — repetir chamaria a Helô de novo (efeito externo).
REST: `503` com `Retry-After: 1` e detalhe "A mensagem não foi gravada…".
WebSocket: quadro `error` com a `client_message_id` e `code: "envio_nao_gravado"`;
o socket segue. Nos dois, nada foi gravado e o reenvio com a mesma chave grava.

## Contrato da API

`GET /api/v1/tickets/{id}/messages?after_seq=k[&limit=n]`

- mensagens com `seq > k`, em ordem crescente de `seq`; `limit` até 100;
- `has_more`, `next_after_seq` (de onde continuar), `ultima_seq` (o contador);
- `after_seq` com `before` ou `offset` → `422`; `after_seq` negativo → `422`;
- `after_seq > ultima_seq` → `409 {"code": "ressincronizar", "ultima_seq": …}`;
- mesmo controle de acesso (404 igual ao de id inexistente) e mesma máscara de
  arquivo interno para cliente;
- paginação antiga (`before`, `offset`) intacta; toda resposta passa a trazer
  `ultima_seq`, e toda mensagem `seq` (nulo no legado). Buraco na sequência não
  é erro por si só.

**Primeira âncora:** `ultima_seq` é lido ANTES da página, em comando separado.
Tudo até ele já estava comitado; uma página recente seguida de
`after_seq=ultima_seq` não perde nada que comitar entre as duas (pode repetir,
e a tela deduplica por id). Teste com commit injetado entre as duas leituras.
**A tela não deve ligar o modo incremental só porque `ultima_seq` existe**:
servidor antigo não manda o campo, e servidor com o legado manda `ultima_seq = 0`
num chamado com histórico inteiro sem número.

### Interruptor (contrato definitivo)

- `CHAT_SINCRONIZACAO_INCREMENTAL` (`chat_sincronizacao_incremental`), **padrão
  `false`**. Desligado, a rota não faz consulta nenhuma a mais.
- Toda resposta da listagem traz `sincronizacao_incremental: bool`. **É o único
  sinal que a tela pode usar** para entrar no modo incremental — por chamado,
  em cada leitura. Ausente (servidor antigo) ou `false` → histórico
  tradicional. Tela antiga ignora o campo e não quebra.
- `true` só quando TUDO vale: interruptor ligado, marco do corte presente
  (`chat_seq_corte`), e nenhuma mensagem do chamado com `seq` nulo e
  `created_at >= marco − 15 min`. Na dúvida, `false`.
- `after_seq` quando não está disponível → `409 {"code":
  "incremental_indisponivel", "detail": …}`, antes de qualquer leitura de
  mensagem. A tela volta ao histórico (página recente) e não insiste.
- O interruptor NÃO é a segurança: é o banco que decide. Ligado num banco sem a
  migration ou depois de um recuo com imagem antiga, o próprio chamado se
  desliga até o script numerar o que entrou sem número.
- Não ligado em produção nesta frente; ligar é decisão da Sessão 0, depois do
  front.

### O marco do corte

A `n0i1` cria `chat_seq_corte` (uma linha, `id = 1`) e grava `migrada_em =
clock_timestamp()` como ÚLTIMO comando — a transação já segura `ACCESS
EXCLUSIVE` em `chat_messages`, então nenhuma mensagem comita entre o marco e o
commit da migration. Ele substitui o "instante registrado no deploy": não
depende de alguém anotar, e sobrevive a recuo de imagem (a tabela fica).

Por que a margem de 15 min: a imagem antiga monta a mensagem (com
`created_at`) ANTES e só grava depois — a Helô leva até ~40 s (modelo 30 s +
embedding 10 s), mais o tempo parado esperando a migration. Uma mensagem dela
pode ter `created_at` ANTERIOR ao marco e comitar depois. Olhar só "depois da
primeira mensagem numerada", ou só "depois do marco", deixaria passar essa. Na
janela de 15 min antes do marco não dá para distinguir histórico de imagem
antiga; por isso o chamado com nulo na janela fica no legado, e o script não a
numera sem `--incluir-janela`.

### Guarda do commit

`before_commit` da `Session` (só no commit raiz — o SAVEPOINT de
`_grava_uma_vez` dispara o evento antes da numeração): mensagem nova, ou
anotada e já gravada, com `seq` nulo → `logger.error` com ids e chamado. **Só
avisa**: não barra, não numera, não consulta o banco (lê o estado do objeto,
sem lazy load) — nada que precise de await dentro do evento síncrono. Pega o
escritor novo que esquecer `numera_mensagens_do_chat`; o escritor velho (imagem
antiga) não passa por ela, e para ele valem o marco e o script.

## Legado

**Decisão definitiva da Sessão 0 (04/11/2026): o histórico NÃO é numerado.**
Nenhuma mensagem anterior à migration recebe `seq` — nem na migration, nem por
script, nem depois. Ela fica com `seq` nulo, aparece no histórico tradicional
(página recente e cursor `before`, por `created_at`) e nunca no incremental. O
contador de todo chamado existente nasce 0; a primeira mensagem nova é a 1.

O `numera_mensagens_sem_seq.py` NÃO é ferramenta de backfill: serve só para o
que for gravado sem número DEPOIS da migration (imagem antiga servindo durante
a troca ou num recuo). Não há `--desde`: o corte é o marco da própria migration
(`chat_seq_corte`), e sem ele o script não faz nada (saída 2). Numera só
`created_at >= marco`; a janela ambígua dos 15 min anteriores só com
`--incluir-janela`, decisão de quem implanta. Sem `--aplicar`, só conta (por
chamado: depois do marco e na janela). Cada chamado é uma transação com o
bloqueio do envio — testado esperando um envio que trava o chamado e rodando
junto com 10 envios: sem número repetido nem buraco.

## Migration `n0i1j2k3l4m5` (down `m9h0i1j2k3l4`)

- Medido em PG descartável, 200 mil mensagens: colunas ~0,2 s (só metadado,
  `relfilenode` de `tickets` e `chat_messages` inalterado), índice ~0,3 s.
- Bloqueios: `ADD COLUMN` pega `ACCESS EXCLUSIVE` por instantes; o `CREATE
  INDEX` (sem `CONCURRENTLY`, pelo mesmo motivo da m9h0: o `env.py` roda tudo
  numa transação) segura `SHARE` em `chat_messages` durante a varredura —
  bloqueia gravação, não leitura. O volume de produção NÃO foi medido.
- `upgrade → downgrade → upgrade` não perde mensagem; o contador volta a 0.

### Limites de espera (`alembic/env.py`)

- `ALEMBIC_LOCK_TIMEOUT` e `ALEMBIC_STATEMENT_TIMEOUT`, duração simples
  (`3s`, `500ms`, `2min`, inteiro = ms). **Sem as variáveis, nada muda**: a
  migration espera como hoje (testado: segue na fila da transação alheia).
- Com elas: `SET LOCAL` dentro da transação da migration, antes da primeira
  revision. Estourou → erro, rollback da transação INTEIRA (nem a `m9h0`, que
  roda antes, fica: sem colunas, índices, `chat_seq_corte`, versão em
  `l8g9`), processo sai ≠ 0. Sem retry: com o `set -e` do `start.sh`, o
  contêiner novo não sobe e o antigo segue atendendo. A tentativa seguinte,
  sem concorrência, passa (testado com 1 s, para os dois limites).
- Valor inválido (inclusive tentativa de injeção) é recusado ANTES de conectar.
- `start.sh` não mudou. Onde e com que valor definir as variáveis no EasyPanel
  é decisão da Sessão 0 (sugestão: `ALEMBIC_LOCK_TIMEOUT=5s`; statement sem
  limite ou folgado, porque o `CREATE INDEX` varre a tabela).

## Rollback

- **Preferido: rollback da IMAGEM mantendo a migration.** A imagem antiga não
  conhece `seq` e grava com `seq` nulo; o resto funciona. Ao voltar a imagem
  nova, rodar `python -m scripts.numera_mensagens_sem_seq` (só conta) e depois
  com `--aplicar`: numera, depois do último número, o que entrou sem número após
  o marco, com o mesmo bloqueio do envio. Até lá, os chamados afetados anunciam
  `sincronizacao_incremental: false` e ficam no histórico; telas que já passaram
  daquele ponto as acham pelo `after_seq` depois do script.
- **⚠️ A imagem anterior NÃO sobe com o banco no head novo** se não tiver o
  arquivo da revision (o `start.sh` morre no `alembic upgrade head`, ver o
  incidente de 03/11). Produção (v1.23.0, `0450129`) está em `l8g9h0i1j2k3`:
  o próximo boot aplica `m9h0i1j2k3l4` E `n0i1j2k3l4m5`, numa transação só. A
  imagem de recuperação é a v1.23.0 com os DOIS arquivos de revision e nada
  mais — procedimento abaixo.

### Imagem de recuperação (procedimento, NÃO executado)

Reproduzível e isolado; não altera a imagem implantada, não publica no
EasyPanel, não faz downgrade.

```sh
git worktree add ../recuperacao-v1.23.0 0450129
cd ../recuperacao-v1.23.0
git switch -c recuperacao/v1.23.0-seq
for r in m9h0i1j2k3l4 n0i1j2k3l4m5; do
  f=$(git ls-tree --name-only <SHA da main mesclada> backend/alembic/versions/ | grep "/${r}_")
  git show "<SHA da main mesclada>:$f" > "$f"
done
git add backend/alembic/versions && git commit -m "recuperação: v1.23.0 + revisions m9h0 e n0i1"
git diff --name-status 0450129   # tem de mostrar SÓ os 2 arquivos (A)
(cd backend && python -m alembic heads)   # n0i1j2k3l4m5, um head só
docker build -t helphs-backend:v1.23.0-recuperacao backend
```

- Os arquivos saem byte a byte do commit que for implantado (não desta
  branch), para o `down_revision` e o corpo serem os mesmos do banco.
- A imagem resultante conhece o head, então sobe; grava mensagens SEM `seq`
  (é a v1.23.0) — exatamente o caso do marco e do script.
- O `env.py` dela é o da v1.23.0: sem os limites de espera, o que não importa,
  porque ela não tem nada a aplicar.
- **Ensaio funcional obrigatório antes do deploy**: PG descartável em `l8g9` →
  imagem nova sobe (aplica as duas) → troca pela de recuperação (sobe, envia,
  `seq` nulo, chamado anuncia `false`) → volta a nova → script conta e numera →
  chamado anuncia `true`.
- **Downgrade não é estratégia de rollback**: apaga os números, zera o contador,
  e toda tela com âncora > 0 recebe 409 e recarrega. Nada se perde, mas todo
  mundo ressincroniza. Não automatizado.
- Instâncias misturadas (nova e antiga ao mesmo tempo, durante a troca): a
  antiga grava sem número; ver o script acima.
- Restauração de backup: o contador volta junto com as mensagens; uma tela com
  âncora maior que o contador restaurado recebe 409. Se o backup for de antes da
  migration, cai no caso do downgrade.

## Socket fantasma (commit separado)

`entregar_local` tirava da sala o socket cujo envio falhava e parava aí: ele
seguia aberto e em `_por_usuario`, e a tela, sem fechamento, ficava surda. E um
quadro não serializável fazia todos falharem e esvaziava a sala. Agora:
- quadro que não vira JSON é registrado (`logger.error`) e descartado ANTES do
  laço, sem tocar em socket nenhum;
- falha de envio tira o socket dos DOIS índices e depois tenta `close(1011)`;
  falha ao fechar não impede a limpeza;
- a B-04b trata 1011 pelo caminho padrão (reconecta e sincroniza — lido no
  código de `useConversaDoChat.ts`, não executado).
- Backplane/Redis não mudou: `publicar` segue sem levantar.

## Testes

- `tests/test_chat_sequencia_postgres.py` (16): commit tardio com `created_at`
  fora de ordem e contador livre durante a Helô; rollback depois da numeração;
  idempotência concorrente; ciclo usuário/chamado com as DUAS vítimas
  (`deadlock_timeout` por conexão); ordem segura sem vítima; dois chamados;
  250 mensagens em 100/100/50; reconexão longa; legado; primeira âncora;
  acesso e arquivo interno; 422/409; WebSocket (quadros, ack, deadlock pelo
  socket); saudação da abertura.
- `tests/test_chat_sequencia_migracao_postgres.py` (6), `tests/test_chat_socket_fantasma.py`
  (6), `tests/test_chat_escritores_de_mensagem.py` (4, por AST: os 4 escritores
  de `ChatMessage(`, nada de `insert(ChatMessage)`/SQL cru, donos numeram depois
  da Helô e antes de todo commit).
- `tests/test_migrations_limite_postgres.py` (14): upgrade conjunto desde
  `l8g9`, espera sem limite, desistência com rollback total e nova tentativa,
  valor inválido, head único.
- `tests/test_chat_sequencia_reforcos_postgres.py` (7): Helô REAL com o
  cliente do modelo atrasado (resposta e escalada), script esperando envio e
  concorrendo com 10 envios, ordem de id entre chamados, guarda (aponta a
  mensagem montada depois da numeração; quieta nos escritores reais).
- Interruptor e marco, em `test_chat_sequencia_postgres.py`: desligado não
  anuncia e `after_seq` é 409 estruturado; sem marco não anuncia; mensagem de
  imagem antiga (depois do marco e na janela) desliga só aquele chamado e volta
  por `after_seq` depois do script.
- Mutações, todas mortas: sem numeração; numeração antes da Helô; contador lido
  depois da página; deadlock sem tratamento; `SET LOCAL` fora do `env.py`; sem
  a margem; sem o filtro de nulo; guarda sem o teste de SAVEPOINT; guarda
  muda; sem o `sorted`.
- NÃO rodados: suíte completa e gate de cobertura (exigem coordenação de
  recursos), E2E/Chrome.

## Depende de / para a B-04b

- A B-04b já trata o quadro `error` com chave (limpa o pendente, mantém o
  rascunho) e o erro REST com resposta (recusa definitiva, rascunho mantido):
  `envio_nao_gravado` e o `503` caem nesses caminhos sem mudança.
- Adotar `after_seq` na tela é trabalho de front POSTERIOR (não feito): âncora
  por `ultima_seq` só depois de validar a continuidade inicial, 409 → recarregar.
