"""desfecho da chamada em ticket_calls

Revision ID: k7f8g9h0i1j2
Revises: c8b8d6994fae
Create Date: 2026-10-02

A Fase 2D.2 provou em producao que `metadata.ticket_call_id` correlaciona o CDR
com a nossa linha. Esta revision cria o lugar onde o desfecho dessa chamada pode
ser guardado quando um evento de encerramento for encaminhado ao HelpHS.

Quatro colunas, todas NULLABLE, e a nulidade nao e descuido:

- `duration_seconds`: a unidade esta no nome, nao num comentario. Foi a licao
  que `provider_call_id` cobrou -- um campo cujo significado vivia so na cabeca
  de quem o criou precisou de correcao documental meses depois.
- `hangup_cause`: VARCHAR(40) sem CHECK e sem enum nativo. O vocabulario e do
  fornecedor; medimos NORMAL_CLEARING, ORIGINATOR_CANCEL e NUMBER_CHANGED, e a
  documentacao nao publica o conjunto fechado. Fechar uma lista que ninguem
  prometeu faria o HelpHS recusar um desfecho legitimo no dia em que ele
  aparecesse. Mesmo criterio de `creation_status` nao ser enum do PostgreSQL --
  so que aqui nem o CHECK cabe.
- `recording_available`: TRES estados reais. True, False e NULL para "o evento
  nao informou". NOT NULL DEFAULT false apagaria o terceiro, e "nao sabemos"
  viraria "nao existe gravacao".
- `hangup_event_received_at`: o relogio e NOSSO -- quando o HelpHS recebeu e
  processou o evento, nao o instante de encerramento que o fornecedor informa.
  Medimos divergencia sistematica de ~3h entre os dois relogios, e esta coluna e
  trava de idempotencia: NULL significa "evento ainda nao chegou", e e a
  condicao do UPDATE atomico que faz a primeira entrega vencer.

O que esta revision deliberadamente NAO cria: `record_url`, audio, transcricao,
`caller`, `called`, telefone e metadata bruto. O endereco da gravacao e tratado
como credencial de acesso ao audio e nao entra no banco do HelpHS -- ver a secao
"Fases 2D.1 e 2D.2" em docs/decisoes-e-regras.md.

Nenhuma linha existente e alterada: as 21 tentativas em producao ficam com as
quatro colunas em NULL, que e a verdade -- elas foram criadas antes de haver
evento de encerramento, e a correlacao e prospectiva.

O downgrade remove exatamente as quatro colunas e nada mais.
"""

import sqlalchemy as sa

from alembic import op

revision = "k7f8g9h0i1j2"
down_revision = "c8b8d6994fae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ticket_calls", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.add_column("ticket_calls", sa.Column("hangup_cause", sa.String(length=40), nullable=True))
    op.add_column("ticket_calls", sa.Column("recording_available", sa.Boolean(), nullable=True))
    op.add_column(
        "ticket_calls",
        sa.Column("hangup_event_received_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ticket_calls", "hangup_event_received_at")
    op.drop_column("ticket_calls", "recording_available")
    op.drop_column("ticket_calls", "hangup_cause")
    op.drop_column("ticket_calls", "duration_seconds")
