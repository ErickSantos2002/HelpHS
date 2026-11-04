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

## Legado

**Decisão definitiva da Sessão 0 (04/11/2026): o histórico NÃO é numerado.**
Nenhuma mensagem anterior à migration recebe `seq` — nem na migration, nem por
script, nem depois. Ela fica com `seq` nulo, aparece no histórico tradicional
(página recente e cursor `before`, por `created_at`) e nunca no incremental. O
contador de todo chamado existente nasce 0; a primeira mensagem nova é a 1.

O `numera_mensagens_sem_seq.py` NÃO é ferramenta de backfill: serve só para o
que for gravado sem número DEPOIS da migration (imagem antiga servindo durante
a troca ou num recuo). O `--desde` é o instante em que a migration rodou em
produção, registrado no deploy — nunca uma data anterior. Um `--desde` antigo
numeraria histórico depois do contador, e a tela receberia mensagens de meses
atrás como se fossem novas.

## Migration `n0i1j2k3l4m5` (down `m9h0i1j2k3l4`)

- Medido em PG descartável, 200 mil mensagens: colunas ~0,2 s (só metadado,
  `relfilenode` de `tickets` e `chat_messages` inalterado), índice ~0,3 s.
- Bloqueios: `ADD COLUMN` pega `ACCESS EXCLUSIVE` por instantes; o `CREATE
  INDEX` (sem `CONCURRENTLY`, pelo mesmo motivo da m9h0: o `env.py` roda tudo
  numa transação) segura `SHARE` em `chat_messages` durante a varredura —
  bloqueia gravação, não leitura. O volume de produção NÃO foi medido.
- `upgrade → downgrade → upgrade` não perde mensagem; o contador volta a 0.

## Rollback

- **Preferido: rollback da IMAGEM mantendo a migration.** A imagem antiga não
  conhece `seq` e grava com `seq` nulo; o resto funciona. Ao voltar a imagem
  nova, rodar `python -m scripts.numera_mensagens_sem_seq --desde <instante da
  migration em produção>` (sem `--aplicar` primeiro): numera, depois do último número, o
  que entrou sem número após o corte, com o mesmo bloqueio do envio. Telas que
  já passaram daquele ponto as acham na próxima releitura.
- **⚠️ A imagem anterior NÃO sobe com o banco no head novo** se não tiver o
  arquivo da revision (o `start.sh` morre no `alembic upgrade head`, ver o
  incidente de 03/11). Produção (v1.23.0, `0450129`) está em `l8g9h0i1j2k3`:
  o próximo boot aplica `m9h0i1j2k3l4` E `n0i1j2k3l4m5`, numa transação só. A
  imagem de recuperação é a v1.23.0 com os DOIS arquivos de revision e nada
  mais — ver o plano entregue à Sessão 0 em 04/11.
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
- Mutações, todas mortas: sem numeração; numeração antes da Helô; contador lido
  depois da página; deadlock sem tratamento.
- NÃO rodados: suíte completa e gate de cobertura (exigem coordenação de
  recursos), E2E/Chrome.

## Depende de / para a B-04b

- A B-04b já trata o quadro `error` com chave (limpa o pendente, mantém o
  rascunho) e o erro REST com resposta (recusa definitiva, rascunho mantido):
  `envio_nao_gravado` e o `503` caem nesses caminhos sem mudança.
- Adotar `after_seq` na tela é trabalho de front POSTERIOR (não feito): âncora
  por `ultima_seq` só depois de validar a continuidade inicial, 409 → recarregar.
