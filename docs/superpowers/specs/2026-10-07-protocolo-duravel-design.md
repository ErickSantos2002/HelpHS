# Protocolo de chamado durável — design

**Data:** 07/10/2026
**Branch:** `feat/protocolo-duravel`
**Migration:** `0a17fd87823c` (filha de `k7f8g9h0i1j2`)

## Por que existe

A sanitização de produção antes do piloto quer começar com `tickets = 0`.
O gerador fazia `max()+1` sobre `tickets`. Medido em produção em 07/10/2026:
25 chamados, protocolos até `HS-2026-0026`, um já apagado. Com a tabela vazia,
o próximo seria `HS-2026-0001`, reusando um protocolo que já saiu por e-mail
(15 envios na outbox) e que segue no texto de notificações, que não fazem
cascata com o chamado.

O defeito não é só zerar: apagar o chamado mais recente também devolvia o
número dele.

## A regra

**O próximo protocolo é o último EMITIDO no ano + 1.** "Emitido" é o que já foi
commitado, exista o chamado ou não.

- O formato `HS-AAAA-NNNN` continua igual (4 dígitos com zero à esquerda, sem
  teto).
- A semântica anual continua: o ano é o do relógio em UTC, como antes, e cada
  ano começa em 0001.
- Buraco pode existir; reuso, não. Um número só volta se a transação que o
  alocou reverteu, e aí ele nunca saiu.

## Mecanismo

Uma tabela `ticket_protocol_counters (year PK, last_number)`, com
`CHECK last_number >= 0`. A alocação é uma instrução só, na transação do
chamado:

```sql
INSERT INTO ticket_protocol_counters (year, last_number)
VALUES (:ano, :piso + 1)
ON CONFLICT (year) DO UPDATE SET last_number =
    CASE WHEN ticket_protocol_counters.last_number + 1 > excluded.last_number
         THEN ticket_protocol_counters.last_number + 1
         ELSE excluded.last_number END
RETURNING last_number
```

- **Concorrência:** o `DO UPDATE` trava a linha do ano até o commit. A segunda
  abertura espera e recebe o número seguinte. Não há lock no Redis.
- **Rollback:** o incremento reverte junto com o chamado. Nada vaza antes do
  commit, porque notificação e e-mail (outbox) estão na mesma transação.
- **Piso:** o maior protocolo do ano em `tickets` só eleva o contador, nunca o
  rebaixa. Ele cobre dois casos: o contêiner antigo abrindo chamados com
  `max()+1` durante o deploy, depois da migration, e seed ou script que grava
  protocolo por fora. `CASE`, e não `GREATEST`, porque a suíte roda o gerador
  também no SQLite.
- **Duração do lock:** a transação de abertura não faz chamada de rede (a
  triagem da Helô só consulta o banco; a classificação por LLM é disparada
  depois do commit). O lock dura o tempo de algumas instruções.

## Migration

- Cria a tabela e semeia cada ano com o maior número presente em `tickets`,
  considerando só protocolos `^HS-[0-9]{4}-[0-9]+$`. Linha manual fora do
  formato não derruba a migration.
- Não altera nem renumera nenhum chamado: só lê `tickets`.
- Número emitido e apagado ACIMA do maior que restou não é recuperável. Em
  produção isso não acontece, porque o 0026 existe. Por isso **a migration
  precisa rodar antes da limpeza**.
- O downgrade remove a tabela. O código antigo volta a `max()+1`.

## A corrida do mecanismo antigo

Além do reset, havia corrida. Duas aberturas simultâneas liam o mesmo máximo; o
índice único recusava uma delas, que gastava uma das 5 retentativas do
`create_ticket`. Duplicata nunca houve. Medido num Postgres efêmero, com o
gerador da `main` e 50 ms entre gerar e commitar:

| Simultâneas | Sucesso | Falharam após 5 tentativas |
|---|---|---|
| 2 | 2 | 0 |
| 10 | 7 | 3 |
| 20 | 7 | 13 |

Quem falha recebe 500. Com o contador, as 10 simultâneas do teste recebem
0001..0010 na primeira tentativa.

## Provas

- `tests/test_protocol.py` (SQLite): sequência, formato, `0001..0026 → 0027`,
  apagar tudo não reinicia, apagar o último não devolve o número, piso de
  chamado gravado por fora, piso baixo não regride, fronteiras de 9999 e
  99999, ano novo, ano em UTC, rollback não emite, chamados existentes
  intactos.
- `tests/test_protocolo_contador_postgres.py` (Postgres real): 10 criadores
  simultâneos; o segundo espera o lock e herda o número revertido; o commit do
  primeiro faz o segundo avançar; semente com buraco, ano anterior e linha
  manual; zerar depois da migration segue em 0027/0028;
  upgrade/downgrade/upgrade; banco vazio; CHECK.
- Mutação: tirar o piso, ignorar o contador, ordenar o piso só por texto,
  fixar o ano no relógio, tirar a semente da migration e voltar a `max()+1`
  sem lock. Cada uma derruba o teste correspondente.

## Ordem no deploy

1. Deploy do backend: a migration roda no boot e semeia 2026 = 26.
2. Conferir em produção:
   `SELECT * FROM ticket_protocol_counters` → `(2026, 26)`, ou maior se
   chamados foram abertos no intervalo.
3. Só então a limpeza dos chamados.
