"""base vetorial da Helô

Revision ID: a7v8w9x0y1z2
Revises: z6u7v8w9x0y1
Create Date: 2026-09-08

Três tabelas e uma extensão, para a Helô deixar de só triar e passar a
responder com o manual do aparelho na mão.

`helo_documents` é o arquivo de origem, `helo_chunks` é o trecho recuperável —
a unidade que a busca devolve e que a resposta cita como fonte — e
`helo_chunk_products` liga o trecho ao produto, no mesmo padrão de
`kb_article_products`: trecho sem produto vinculado vale para todos, trecho
vinculado ao Phoebus só aparece em chamado de Phoebus. Esse filtro é a única
coisa que impede a busca de entregar o passo a passo do Phoebus para quem tem
um Titan na mão, porque todos os manuais falam de sopro, LED e calibração.

O VÍNCULO É DO TRECHO, e não do documento, de propósito. O que a busca devolve
é o trecho; amarrar no documento obrigaria toda consulta a passar pelo join
para descobrir de quem o trecho é, e impediria o caso real de uma seção que
serve a mais de um aparelho.

ESTA MIGRATION NÃO CRIA A EXTENSÃO — ela EXIGE que já exista, e é a decisão
mais importante do arquivo.

Criar extensão é ato administrativo de uma vez, não trabalho de migration. O
`pgvector` não é extensão *trusted*: criá-la pede superusuário, e não apenas
CREATE no banco como as trusted (pgcrypto, pg_trgm, unaccent). Se a migration
tentasse criar, o usuário da aplicação precisaria ser superusuário — e as
migrations rodam sozinhas no boot do container pelo `start.sh`, então isso
colocaria privilégio de superusuário no caminho do boot, permanentemente, por
causa de um comando que roda uma vez na vida do banco.

Verificar em vez de criar tira o superusuário do caminho do boot de vez. O
preço é um passo manual antes do primeiro deploy desta versão:

    CREATE EXTENSION vector;      -- uma vez, com superusuário, no banco alvo

E é um preço que se paga uma vez. A verificação continua no boot para sempre,
mas ela é uma consulta a `pg_extension` que qualquer usuário faz.

A mensagem de falha é o resto do desenho. Migration que falha não é teste
vermelho: é a API que não sobe, no meio de um deploy — já aconteceu em 19/08
com o guard de CORS. Um erro cru de `type "vector" does not exist` na terceira
tabela não diz o que fazer; a mensagem daqui diz, nomeia o banco (sem a senha)
e cabe numa linha de log.

Vale notar que a extensão é POR BANCO, não por servidor: instalar o pacote no
servidor, ou usar a imagem `pgvector/pgvector`, coloca os arquivos lá, mas o
`CREATE EXTENSION` ainda precisa rodar dentro de cada banco que for usá-la.

SEM ÍNDICE VETORIAL, e não é esquecimento. A base inteira são oito manuais e
cerca de 80 trechos. `ivfflat` e `hnsw` são estruturas APROXIMADAS, desenhadas
para dezenas de milhares de vetores: nessa escala elas trocam um pouco de
precisão por muito tempo. Com 80 linhas a conta inverte — a varredura completa
é exata e custa menos de um milissegundo, e um `ivfflat` com as listas padrão
seria ao mesmo tempo mais lento para construir e capaz de **não achar** o
trecho certo. O gatilho para criar o índice é a base crescer uma ordem de
grandeza, que é o que acontece no dia em que a base da Helô antiga for
migrada; até lá, índice aqui seria perda de recall comprada com trabalho.

`exige_credencial_admin` existe por causa de duas senhas. O manual do Phoebus
traz, em texto aberto, as senhas de dois menus de configuração avançada — e um
deles ativa "nenhum resultado de teste e aviso exibido", ou seja, desliga a
exibição do resultado num equipamento de medição legal usado em controle de
acesso. A Helô não pode entregar isso a quem perguntar.

A saída não é excluir o trecho. Excluir joga fora o procedimento inteiro e
produz uma **escalada cega**: a busca não acha nada, a Helô escala por NADA
ENCONTRADO e ninguém — nem ela, nem o técnico que receber — sabe por quê. Com
a marca, a busca acha o trecho, a Helô lê a marca e escala dizendo o motivo
exato: essa configuração exige senha de administrador.

O valor da senha é redigido na ingestão; o procedimento fica. Marca e redação
são as duas metades da mesma decisão: a marca sem a redação entregaria a senha
mesmo assim, e a redação sem a marca produziria a escalada cega.

A coluna `embedding` nasce NULA porque recortar e embutir são duas passagens.
Recortar é barato e determinístico; embutir custa e depende do modelo local
estar carregado. Separadas, trocar o modelo de embedding é re-embutir o que já
está recortado, e não reler e recortar os oito manuais de novo.

A DIMENSÃO 1024 é a do `bge-m3` e da `multilingual-e5-large`, os dois modelos
locais em avaliação. Ela é tipo de coluna, não configuração: um modelo de
dimensão diferente exige migration nova. Está dito aqui e no `models.py` para
que a troca seja decisão consciente, e não a descoberta de um INSERT recusado.

SEM BACKFILL, e não é omissão: não há passado para reescrever. As três tabelas
nascem vazias e quem as popula é o script de ingestão da etapa seguinte, que
roda à mão e lê os manuais de uma pasta FORA do repositório.

O DOWNGRADE derruba as três tabelas e leva junto os trechos e os embeddings.
Não há como preservar: as tabelas somem. Reconstruir é rodar a ingestão de
novo, que é barata (oito manuais) desde que a pasta ainda exista — ela não
está no repositório e não volta com o código.

O downgrade **não remove a extensão**, e agora por um motivo mais simples do
que antes: esta migration não a criou. Desfazer o que não se fez é apagar
trabalho de outra pessoa.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

from alembic import op

revision: str = "a7v8w9x0y1z2"
down_revision: str | None = "z6u7v8w9x0y1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A mesma dimensão declarada em `app/models/models.py`. Repetida aqui, e não
# importada de lá: migration é registro do que foi aplicado naquele dia, e
# importar do código faria uma migration antiga mudar de significado quando
# alguém trocasse a constante.
EMBEDDING_DIM = 1024

_SEM_EXTENSAO = (
    "A migration a7v8w9x0y1z2 exige a extensão `vector` (pgvector), que NÃO "
    "está criada no banco {alvo}.\n"
    "\n"
    "Esta migration não cria a extensão de propósito: criá-la exige "
    "superusuário, e as migrations rodam no boot do container — criar aqui "
    "colocaria privilégio de superusuário no caminho do boot para sempre, por "
    "causa de um comando que roda uma vez na vida do banco.\n"
    "\n"
    "O que fazer, UMA VEZ, com um superusuário, conectado a este banco:\n"
    "    CREATE EXTENSION vector;\n"
    "\n"
    "A extensão é POR BANCO, não por servidor: ter o pgvector instalado na "
    "máquina (ou usar a imagem `pgvector/pgvector:pg16`) põe os arquivos no "
    "lugar, mas o CREATE EXTENSION ainda precisa rodar dentro deste banco.\n"
    "\n"
    "Se o CREATE EXTENSION falhar com `could not open extension control "
    "file`, o pgvector não está instalado no servidor e o conserto é de "
    "infraestrutura, não de banco."
)


def upgrade() -> None:
    conexao = op.get_bind()
    # Verificar, e não criar. A consulta é a `pg_extension`, que qualquer
    # usuário lê — nenhum privilégio especial fica exigido no boot.
    presente = conexao.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
    if not presente:
        alvo = conexao.engine.url.render_as_string(hide_password=True)
        raise RuntimeError(_SEM_EXTENSAO.format(alvo=alvo))

    op.create_table(
        "helo_documents",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "doc_type",
            sa.Enum("tecnico", "comercial", name="helodoctype"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Único: o nome do arquivo é a identidade do documento, e é o que torna a
    # ingestão idempotente. Rodar de novo tem de reconhecer o arquivo, não
    # criar um segundo.
    op.create_index("ix_helo_documents_filename", "helo_documents", ["filename"], unique=True)
    op.create_index("ix_helo_documents_doc_type", "helo_documents", ["doc_type"], unique=False)

    op.create_table(
        "helo_chunks",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("secao", sa.String(length=255), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column(
            "exige_credencial_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_id"], ["helo_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_helo_chunks_document_id", "helo_chunks", ["document_id"], unique=False)
    # A ordem do arquivo é a ordem do procedimento, e ela precisa ser estável
    # na leitura. Único por documento para a ingestão não conseguir gravar dois
    # trechos disputando a mesma posição.
    op.create_index(
        "ix_helo_chunks_documento_ordem", "helo_chunks", ["document_id", "ordem"], unique=True
    )

    op.create_table(
        "helo_chunk_products",
        sa.Column("chunk_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["helo_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id", "product_id"),
    )
    # Índice pelo lado do PRODUTO. A chave primária já cobre buscas que partem
    # do trecho; a consulta da Helô parte do produto do chamado e pergunta
    # quais trechos servem — o lado que a PK composta não indexa sozinha.
    op.create_index(
        "ix_helo_chunk_products_product_id", "helo_chunk_products", ["product_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_helo_chunk_products_product_id", table_name="helo_chunk_products")
    op.drop_table("helo_chunk_products")
    op.drop_index("ix_helo_chunks_documento_ordem", table_name="helo_chunks")
    op.drop_index("ix_helo_chunks_document_id", table_name="helo_chunks")
    op.drop_table("helo_chunks")
    op.drop_index("ix_helo_documents_doc_type", table_name="helo_documents")
    op.drop_index("ix_helo_documents_filename", table_name="helo_documents")
    op.drop_table("helo_documents")
    # O enum é tipo nomeado do Postgres e não some com a tabela que o usa.
    # Deixá-lo para trás faria o upgrade seguinte falhar com "type already
    # exists" — o mesmo tropeço que a n4i5j6k7l8m9 já teve com o
    # `calendareventtype`.
    sa.Enum(name="helodoctype").drop(op.get_bind(), checkfirst=True)
