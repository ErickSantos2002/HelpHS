"""interruptores da IA por cliente e por chamado

Revision ID: z6u7v8w9x0y1
Revises: y5t6u7v8w9x0
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

Upgrade sem risco: duas colunas novas com default.

DOWNGRADE: derruba as duas colunas, e nao ha para onde guardar quem estava
desligado num schema que nao tem as colunas. Como o re-upgrade recria tudo com
default TRUE, um ciclo de descer e subir RELIGARIA a IA de quem a desligou.
Por isso o downgrade ABORTA quando existe qualquer opt-out — preferimos parar a
religar em silencio. Ver docs/decisoes-e-regras.md, regra 5.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "z6u7v8w9x0y1"
down_revision: str | None = "y5t6u7v8w9x0"
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
    # Guarda acrescentada em 02/09/2026. Descer apaga a coluna; o re-upgrade a
    # recria com `server_default` TRUE. Quem tinha desligado a IA volta LIGADO
    # — o estado nao volta neutro, volta ligado.
    #
    # Nao ha de onde reconstruir. Procurei: `_audit()` em app/routers/users.py
    # grava o AuditLog so com action/entity_type/entity_id, deixando `old_data`
    # e `new_data` nulos, entao o valor anterior de `users.ai_enabled` nao
    # existe em lugar nenhum do banco. Para `tickets.ai_enabled` o
    # `ticket_history` registra a troca, mas e log de mudanca e nao retrato de
    # estado: some junto com o chamado por CASCADE.
    #
    # Sem fonte confiavel, nao se inventa restauracao. Aborta.
    bind = op.get_bind()
    desligados = {
        tabela: bind.execute(
            sa.text(f"SELECT count(*) FROM {tabela} WHERE ai_enabled = false")  # noqa: S608
        ).scalar_one()
        for tabela in ("users", "tickets")
    }

    if any(desligados.values()):
        raise RuntimeError(
            "ROLLBACK BLOQUEADO: "
            f"{sum(desligados.values())} opt-out(s) de IA seriam religados.\n"
            "\n"
            f"    users.ai_enabled = false  : {desligados['users']}\n"
            f"    tickets.ai_enabled = false: {desligados['tickets']}\n"
            "\n"
            "Descer apaga a coluna e o re-upgrade a recria com default TRUE — quem\n"
            "desligou a IA de proposito volta com ela ligada, sem ser avisado.\n"
            "\n"
            "Nao ha de onde reconstruir esse valor: o AuditLog de usuario e gravado\n"
            "sem old_data/new_data. Este downgrade nao inventa restauracao e nao\n"
            "religa em silencio. A saida e manual — anote quem esta desligado antes\n"
            "de descer e reponha depois de subir:\n"
            "\n"
            "    SELECT id, email FROM users WHERE ai_enabled = false;\n"
            "    SELECT id, protocol FROM tickets WHERE ai_enabled = false;\n"
        )

    for tabela in ("users", "tickets"):
        op.drop_column(tabela, "ai_enabled")
