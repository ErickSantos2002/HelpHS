"""base vetorial da Helô

Revision ID: a7v8w9x0y1z2
Revises: c9d0e1f2a3b4
Create Date: 2026-09-08

RE-PARENTADA duas vezes em 10/09/2026, pelo mesmo motivo. Primeiro de
z6u7v8w9x0y1 para b8c9d0e1f2a3, quando a main mesclou as migrations de SLA
(a7b8c9d0e1f2, b8c9d0e1f2a3); depois de b8c9d0e1f2a3 para c9d0e1f2a3b4, quando
a main ganhou a da biblioteca de arquivos, filha do mesmo b8c9d0e1f2a3. Nas duas
vezes uma migration da main nasceu do MESMO pai que esta, e dois heads fazem o
`alembic upgrade head` recusar — o `start.sh` morre antes do uvicorn com o
EasyPanel mostrando build verde. A segunda foi pega pelo CI, que testa o PR
mesclado com a main, e não pelo `alembic heads` local, que só via a branch.

Editar o pai é seguro porque esta revision só existe nesta branch: ela não está
no `main`, de onde produção sobe (conferido no remoto em 10/09/2026). As da
main NÃO foram tocadas.

REESCRITA em 10/09/2026, pelo mesmo critério. A fonte da base deixou de ser uma
pasta de manuais e passou a ser a Base de Conhecimento
(`docs/superpowers/specs/2026-09-10-helo-base-de-conhecimento-design.md`). A
versão anterior criava `helo_documents` e `helo_chunk_products`; as duas
morreram com a mudança de fonte. O plano previa derrubá-las numa migration
nova — uma migration DESTRUTIVA rodando no boot de produção. Como esta revision
nunca esteve no `main`, reescrevê-la no formato final troca aquilo por nenhum
`DROP` em produção, nunca: as tabelas antigas simplesmente não chegam a existir
lá. Banco local que as tinha precisa ser refeito; ele só guardava dado derivado
dos manuais.

O QUE ESTA MIGRATION CRIA
-------------------------
`helo_chunks` é o trecho recuperável — a unidade que a busca devolve e que a
resposta cita como fonte —, agora apontando para o ARTIGO de onde saiu. O
produto do trecho é o produto do artigo, por `kb_article_products`, que já
existe e já é editado pela tela: um vínculo por trecho seria uma segunda fonte
de verdade para a mesma pergunta.

`helo_indexacao` diz o que já foi indexado e de qual versão do texto. É o que
permite à varredura periódica reindexar SÓ o artigo que mudou, sem pagar
embedding por texto igual. O hash não é de `updated_at`: aquele carimbo anda a
cada visualização do artigo (o `view_count` é incrementado por UPDATE), e cada
clique pagaria embedding de um texto que não mudou.

As duas tabelas caem junto com o artigo (`ON DELETE CASCADE`). Na prática o
artigo quase nunca é apagado — excluir pela tela ARQUIVA —, e a varredura
limpa os trechos de artigo arquivado; a cascata cobre o apagamento de verdade,
que acontece fora da tela.

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
com o guard de CORS. Um erro cru de `type "vector" does not exist` não diz o
que fazer; a mensagem daqui diz, nomeia o banco (sem a senha) e cabe numa
linha de log.

Vale notar que a extensão é POR BANCO, não por servidor: instalar o pacote no
servidor, ou usar a imagem `pgvector/pgvector`, coloca os arquivos lá, mas o
`CREATE EXTENSION` ainda precisa rodar dentro de cada banco que for usá-la.

SEM ÍNDICE VETORIAL, e não é esquecimento. A base são três manuais e cerca de
80 trechos. `ivfflat` e `hnsw` são estruturas APROXIMADAS, desenhadas para
dezenas de milhares de vetores: nessa escala elas trocam um pouco de precisão
por muito tempo. Com 80 linhas a conta inverte — a varredura completa é exata e
custa menos de um milissegundo, e um `ivfflat` com as listas padrão seria ao
mesmo tempo mais lento para construir e capaz de **não achar** o trecho certo.
O gatilho para criar o índice é a base crescer uma ordem de grandeza — que
agora depende de quantos artigos o suporte publicar.

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

O valor da senha é redigido na IMPORTAÇÃO do manual para a Base de
Conhecimento — antes de o artigo existir, porque artigo publicado é visível
para o cliente. A indexação reconhece a marca de redação e acende a coluna.

A coluna `embedding` nasce NULA porque recortar e embutir são duas passagens.
Recortar é barato e determinístico; embutir custa e depende do serviço de
embedding estar de pé. Separadas, uma varredura com o serviço fora deixa o
trecho velho no lugar em vez de gravar trecho sem vetor.

A DIMENSÃO 1024 é a do `bge-m3`, o modelo do serviço de embedding. Ela é tipo
de coluna, não configuração: um modelo de dimensão diferente exige migration
nova. Está dito aqui e no `models.py` para que a troca seja decisão
consciente, e não a descoberta de um INSERT recusado.

SEM BACKFILL, e não é omissão: não há passado para reescrever. As tabelas
nascem vazias e quem as popula é a varredura periódica, a partir dos artigos
publicados.

O DOWNGRADE derruba as duas tabelas e leva junto os trechos e os embeddings.
Reconstruir é deixar a varredura rodar: os artigos continuam existindo.

O downgrade **não remove a extensão**: esta migration não a criou. Desfazer o
que não se fez é apagar trabalho de outra pessoa.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

from alembic import op

revision: str = "a7v8w9x0y1z2"
down_revision: str | None = "c9d0e1f2a3b4"
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
        "helo_chunks",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", sa.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["article_id"], ["kb_articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_helo_chunks_article_id", "helo_chunks", ["article_id"], unique=False)
    # Único por artigo: a indexação não pode gravar dois trechos disputando a
    # mesma posição, senão a ordem de leitura vira sorteio.
    op.create_index(
        "ix_helo_chunks_artigo_ordem", "helo_chunks", ["article_id", "ordem"], unique=True
    )

    op.create_table(
        "helo_indexacao",
        sa.Column("article_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "indexado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["article_id"], ["kb_articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("article_id"),
    )


def downgrade() -> None:
    op.drop_table("helo_indexacao")
    op.drop_index("ix_helo_chunks_artigo_ordem", table_name="helo_chunks")
    op.drop_index("ix_helo_chunks_article_id", table_name="helo_chunks")
    op.drop_table("helo_chunks")
