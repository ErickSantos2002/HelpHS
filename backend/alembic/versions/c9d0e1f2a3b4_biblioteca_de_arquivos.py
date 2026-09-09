"""biblioteca de arquivos frequentes, e o anexo dela na mensagem de chat

Revision ID: c9d0e1f2a3b4
Revises: z6u7v8w9x0y1
Create Date: 2026-09-08

Duas coisas, porque uma nao existe sem a outra: a tabela dos arquivos
recorrentes (manual, guia, formulario) e a coluna que liga um deles a uma
mensagem de chat.

O ANEXO NAO COPIA O ARQUIVO
---------------------------
`chat_messages.library_file_id` aponta para a linha da biblioteca. O arquivo e
gravado e escaneado UMA vez, no envio, e todas as mensagens que o citam
apontam para o mesmo objeto. Copiar por mensagem multiplicaria o mesmo PDF no
disco e criaria a pergunta de qual copia e a boa quando o admin trocar o
manual por uma versao nova.

`ondelete` e SET NULL, e nao CASCADE: apagar um item da biblioteca nao pode
apagar a conversa. A mensagem sobrevive sem o arquivo, que e ruim mas
recuperavel; apagar a fala do tecnico nao e.

POR QUE EXISTE COLUNA DE VISIBILIDADE
-------------------------------------
Porque manual nao e material publico por definicao. O script de ingestao da
Helo, na frente vizinha, registra o motivo em uma frase:

    "os manuais vivem fora de qualquer repositorio porque o do Phoebus traz
     senhas de configuracao avancada em texto aberto, e este repositorio e
     publico"

Aquela frente tem o cuidado de nunca copiar um manual para dentro da arvore.
Esta faz o oposto -- guarda e SERVE --, e o tecnico anexa na conversa, que o
cliente le. Sem a coluna, um upload do manual tecnico do Phoebus entrega senha
de configuracao ao cliente.

O DEFAULT E `internal`, e isso e a decisao inteira. Abrir para o cliente e
acao explicita de quem envia. Assim o esquecimento falha do lado seguro: quem
subir um arquivo sem pensar na visibilidade sobe um arquivo que o cliente nao
ve. O contrario -- default aberto -- faz o descuido vazar.

`server_default` e obrigatorio aqui e nao e estilo: a coluna nasce NOT NULL e
sem ele o ALTER recusaria, porque nao ha linha para preencher. Como a tabela
nasce vazia isso e teorico, mas o default tambem vale para INSERT que nao
declare a coluna -- e e ele que garante o lado seguro em codigo futuro que
esqueca de passa-la.

O downgrade derruba a tabela e a coluna. Os arquivos em disco NAO sao
apagados: o downgrade perde o indice deles, e apagar binario de usuario a
partir de uma migration seria destruir dado que ninguem mandou destruir.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "z6u7v8w9x0y1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NOME_DO_TIPO = "libraryvisibility"
_VALORES = ("internal", "client")

# `create_type=False` na coluna, e a criacao explicita no upgrade.
#
# Sem isso o tipo nasce DUAS vezes e a migration morre com
# "type libraryvisibility already exists": o `create_table` cria o ENUM sozinho
# quando encontra um `sa.Enum` na coluna, e a chamada explicita ja o havia
# criado. Pego rodando a migration do zero contra um PostgreSQL de verdade --
# em producao ela roda no boot do container, entao a falha seria a API sem
# subir.
_TIPO_NA_COLUNA = postgresql.ENUM(*_VALORES, name=_NOME_DO_TIPO, create_type=False)


def upgrade() -> None:
    postgresql.ENUM(*_VALORES, name=_NOME_DO_TIPO).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "library_files",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Nulo = arquivo que nao e de um aparelho especifico (politica,
        # formulario). O filtro por produto e o que evita a lista virar uma
        # rolagem unica onde ninguem acha o manual do Phoebus.
        sa.Column(
            "product_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "visibility",
            _TIPO_NA_COLUNA,
            nullable=False,
            server_default="internal",
        ),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.String(500), nullable=False),
        sa.Column("s3_bucket", sa.String(100), nullable=False),
        sa.Column("virus_scanned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("virus_clean", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "uploaded_by",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_library_files_title", "library_files", ["title"])

    op.add_column(
        "chat_messages",
        sa.Column(
            "library_file_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("library_files.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_chat_messages_library_file_id", "chat_messages", ["library_file_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_library_file_id", table_name="chat_messages")
    op.drop_column("chat_messages", "library_file_id")
    op.drop_index("ix_library_files_title", table_name="library_files")
    op.drop_table("library_files")
    postgresql.ENUM(*_VALORES, name=_NOME_DO_TIPO).drop(op.get_bind(), checkfirst=True)
