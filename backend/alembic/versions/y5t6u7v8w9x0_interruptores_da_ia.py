"""interruptores da IA por cliente e por chamado

Revision ID: y5t6u7v8w9x0
Revises: x4s5t6u7v8w9
Create Date: 2026-08-26

Segundo tijolo da Helo Fase 1: onde desligar.

O cliente pediu tres niveis -- global, por CNPJ ou cliente, e por chamado. O
global ja existe em configuracao (`LLM_ENABLED`, e agora `HELO_ENABLED`). Esta
revision cria os dois que sao dado:

- `users.ai_enabled`: ha empresa que nao quer robo. Sem isso, a alternativa
  seria pedir para o atendente lembrar de calar a IA em cada chamado dessa
  empresa -- e isso nao e alternativa.
- `tickets.ai_enabled`: o interruptor do tecnico, para quando ele entra na
  conversa e quer a Helo calada dali em diante.

O nivel por CNPJ nao entra aqui: depende de a empresa existir como entidade
confiavel, o que so acontece depois do UNIQUE(companies.cnpj). Ver
docs/superpowers/specs/2026-08-26-empresa-e-aparelho-compartilhado-design.md.

Os dois nascem TRUE. Nao e descuido: nascer false desligaria a classificacao
automatica de todo chamado existente no deploy seguinte, sem ninguem pedir. A
Helo nao comeca a falar por causa disso -- quem decide isso e o HELO_ENABLED,
que nasce DESLIGADO.

`server_default` e obrigatorio aqui, nao estilo: sem ele o ALTER TABLE ... SET
NOT NULL recusa, porque as linhas existentes ficariam nulas. Com ele o
Postgres preenche todas de uma vez.

Upgrade sem risco: duas colunas novas com default. O downgrade derruba as
duas e perde quem estava desligado -- nao ha para onde guardar essa informacao
num schema que nao tem as colunas.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "y5t6u7v8w9x0"
down_revision: str | None = "x4s5t6u7v8w9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabela in ("users", "tickets"):
        op.add_column(
            tabela,
            sa.Column(
                "ai_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    for tabela in ("users", "tickets"):
        op.drop_column(tabela, "ai_enabled")
