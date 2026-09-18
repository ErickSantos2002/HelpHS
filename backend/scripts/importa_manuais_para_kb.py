"""
Importa os três manuais técnicos para a Base de Conhecimento, como RASCUNHO.

COMO RODAR
----------
    # relatório, sem tocar no banco (padrão — é o modo seguro)
    python scripts/importa_manuais_para_kb.py --pasta "C:/caminho/Memoria da Helo"

    # grava de verdade
    python scripts/importa_manuais_para_kb.py --pasta "..." --autor quem@empresa --aplicar

O caminho também pode vir de `HELO_MANUAIS_DIR`. **Não há padrão apontando para
dentro do repositório**: os manuais vivem fora de qualquer repositório porque o
do Phoebus traz senhas de configuração avançada em texto aberto, e este
repositório é público. Nenhum .txt é copiado, movido ou gravado para dentro da
árvore — nem temporariamente.

O QUE ELE FAZ
-------------
Lê os três manuais, reestrutura cada um em markdown — o título numerado do
manual vira `##`, a subseção vira `###` — e cria um artigo por manual na Base de
Conhecimento, vinculado ao produto dele, em RASCUNHO. Uma pessoa lê e publica;
publicar é o que faz a varredura periódica indexá-lo para a Helô.

O markdown não é enfeite. Sem ele, "6. Passo a Passo" no começo de uma linha
seria renderizado pela página como item de lista numerada começando em 6, e a
régua de `===` do Phoebus viraria cabeçalho gigante no meio da seção.

POR QUE RASCUNHO
----------------
Publicado quer dizer visível para o cliente. Publicar direto significaria que a
primeira pessoa a ler o manual redigido é o cliente. Rascunho custa um passo,
uma vez, e é exatamente o passo em que alguém confere, olhando, que as senhas
sumiram do texto. Decisão de 10/09/2026.

A REDAÇÃO ACONTECE AQUI, E NÃO SÓ NA INDEXAÇÃO
----------------------------------------------
A redação da indexação protege a base vetorial e não protege a página. Por isso
o artigo NASCE redigido: o redator preciso roda sobre o texto final, e o
detector largo confere depois, com a mesma fatalidade que tinha na ingestão por
arquivo — detector disparou e o redator não redigiu, a importação PARA,
nomeando arquivo e linha. Falso positivo é barato e visível; falha muda não é.

O QUE NÃO ENTRA
---------------
As cinco fichas comerciais (Deimos, EBS-010, iBlow 10 Pro, Mark X, Mercury): têm
preço, e publicá-las poria tabela de preço na tela do cliente. E o
`Perfil da IA Helo.txt`, que é o prompt da Helô do WhatsApp, não manual de
aparelho. A ausência deles na lista abaixo é a decisão.
"""

import argparse
import asyncio
import os
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings  # noqa: E402
from app.models.models import (  # noqa: E402
    KBArticle,
    KBArticleStatus,
    Product,
    TicketCategory,
    User,
    UserRole,
    kb_article_products,
)
from app.services.helo_texto import (  # noqa: E402
    _REGUA,
    MARCA_DE_SENHA_REDIGIDA,
    CredencialNaoRedigidaError,
    Trecho,
    _corta_numerada,
    confere_redacao,
    redige,
)
from app.utils.slug import slug_unico, slugifica  # noqa: E402


@dataclass(frozen=True)
class Manual:
    """Um manual e o produto dele — DECLARADO, e não adivinhado pelo nome."""

    arquivo: str
    produto: str
    titulo: str


# O produto é declarado, ao contrário da ingestão por arquivo, que o casava
# pelo nome do arquivo. Aquilo existia porque eram oito arquivos e ninguém
# queria tabelar; são três, e digitar três nomes é mais barato que uma
# heurística. O nome ainda é conferido contra o cadastro — ver
# `resolve_produtos`.
MANUAIS = (
    Manual("manual_phoebus_completo.txt", "Phoebus", "Manual Técnico do Phoebus"),
    Manual("Manual Tecnico Titan.txt", "Titan", "Manual Técnico do Titan"),
    Manual("Manual_Tecnico_iBlow10Pro.txt", "iBlow 10 Pro", "Manual Técnico do iBlow 10 Pro"),
)

_REGUA_IGUAL = re.compile(r"^={3,}\s*$")
_TITULO_NUMERADO = re.compile(r"^\d+\.\s")


class ImportacaoRecusadaError(RuntimeError):
    """Algo não fecha. Não há palpite bom aqui, então nada é gravado."""


def chave(texto: str) -> str:
    """
    A forma comparável de um nome: minúsculas, sem acento, sem espaço, sem
    underscore e sem hífen. "iBlow 10 Pro" e "IBLOW-10-PRO" são o mesmo produto.
    """
    s = unicodedata.normalize("NFKD", texto.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s_\-]+", "", s)


def resolve_produtos(
    manuais: tuple[Manual, ...], cadastro: list[tuple[uuid.UUID, str]]
) -> dict[str, uuid.UUID]:
    """
    O produto de cada manual, conferido contra o cadastro. Zero ou dois é FATAL.

    NA IMPORTAÇÃO, VÍNCULO AUSENTE É FATAL — e na Base de Conhecimento em geral
    não é. Duas regras, dois lugares, e a diferença é de propósito:

    - Na tela, quem publica artigo sem produto ESCOLHEU que ele vale para todos
      os aparelhos. É a regra do modelo, e é como a barra lateral funciona.
    - Aqui quem cria o artigo é MÁQUINA. Se ela não conseguir vincular o
      produto, ninguém escolheu nada: o passo a passo do Phoebus viraria
      universal e chegaria a quem tem um Titan na mão, pela porta de um
      casamento frustrado. É exatamente o defeito que a inversão da regra de
      produto torna possível, e é aqui que ele entraria.

    Quem unificar as duas achando que achou inconsistência reabre esse caminho.
    O outro lado desta nota está em `_set_article_products`, em
    `app/routers/kb.py`.

    `products.name` não tem restrição de unicidade no banco, e dois produtos
    que se reduzem à mesma chave também são fatais, com os dois ids na
    mensagem — um dicionário por nome guardaria só o último, e os chamados do
    outro registro nunca veriam o manual.
    """
    por_chave: dict[str, list[tuple[uuid.UUID, str]]] = {}
    for pid, nome in cadastro:
        por_chave.setdefault(chave(nome), []).append((pid, nome))

    resolvidos: dict[str, uuid.UUID] = {}
    for manual in manuais:
        achados = por_chave.get(chave(manual.produto), [])
        if len(achados) != 1:
            detalhe = "; ".join(f"{nome} ({pid})" for pid, nome in achados) or "nenhum"
            raise ImportacaoRecusadaError(
                f"{manual.arquivo}: o produto declarado '{manual.produto}' casou com "
                f"{len(achados)} produto(s) do cadastro ({detalhe}). É preciso exatamente "
                "um: sem vínculo, o manual valeria para TODOS os aparelhos; com dois, "
                "iria para um aparelho que não é o dele. Nada foi gravado."
            )
        resolvidos[manual.arquivo] = achados[0][0]
    return resolvidos


def converte(manual: Manual, bruto: str) -> str:
    """
    Do manual em texto para o artigo em markdown, JÁ redigido.

    Tudo do manual entra no artigo, inclusive seção que a indexação vai
    descartar por não ter corpo: o artigo é o manual inteiro, para quem lê na
    tela; escolher o que vira trecho é trabalho da indexação. Um `##` sem corpo
    ainda precisa existir para que os `###` debaixo dele saibam de quem são.

    Levanta `CredencialNaoRedigidaError` quando o detector largo vê algo com
    cara de senha que sobreviveu à redação.
    """
    partes: list[str] = []
    for titulo, bloco in _corta_numerada(bruto.splitlines()):
        corpo = [x for x in bloco if not (_REGUA.match(x) or _REGUA_IGUAL.match(x))]
        primeira = corpo[0].strip() if corpo else ""

        if " → " in titulo:
            partes.append(f"### {titulo.split(' → ', 1)[1]}")
            corpo = corpo[1:]
        elif _TITULO_NUMERADO.match(primeira):
            partes.append(f"## {titulo}")
            corpo = corpo[1:]
        # Senão é o preâmbulo do documento, antes da seção 1: entra como texto.

        texto = "\n".join(corpo).strip()
        if texto:
            partes.append(texto)

    markdown = "\n\n".join(partes).strip() + "\n"
    limpo, _ = redige(markdown)

    # O artigo inteiro como UM trecho: o que a conferência pergunta é se os
    # dígitos de alguma linha suspeita do ORIGINAL sobreviveram no texto FINAL.
    final = [Trecho(secao=manual.titulo, conteudo=limpo, exige_credencial=False, ordem=0)]
    confere_redacao(manual.arquivo, bruto, final)
    return limpo


async def grava_rascunhos(
    db: AsyncSession,
    artigos: list[tuple[Manual, str]],
    produtos: dict[str, uuid.UUID],
    autor_id: uuid.UUID,
) -> None:
    """
    Os artigos, em RASCUNHO e com a Helô autorizada a ler, numa transação só.

    Separada do resto do script para ser testável sem banco e sem a pasta dos
    manuais: é aqui que moram as duas decisões de 10/09 que um erro de digitação
    desfaria em silêncio — nascer rascunho (senão a primeira pessoa a ler o
    manual redigido é o cliente) e o vínculo com o produto (senão o manual vale
    para todos os aparelhos).
    """
    agora = datetime.now(UTC)
    for manual, limpo in artigos:
        artigo = KBArticle(
            id=uuid.uuid4(),
            title=manual.titulo,
            content=limpo,
            slug=await slug_unico(slugifica(manual.titulo), db),
            category=TicketCategory.hardware,
            tags=[],
            status=KBArticleStatus.draft,
            helo_pode_ler=True,
            author_id=autor_id,
            view_count=0,
            helpful=0,
            not_helpful=0,
            created_at=agora,
            updated_at=agora,
        )
        db.add(artigo)
        await db.flush()
        await db.execute(
            kb_article_products.insert().values(
                article_id=artigo.id, product_id=produtos[manual.arquivo]
            )
        )
    # Os três numa transação só: ou entram os três, ou nenhum.
    await db.commit()


def _alvo(url: str) -> str:
    return url.rsplit("@", 1)[-1]


async def _importa(pasta: Path, autor_email: str | None, aplicar: bool) -> int:
    settings = get_settings()
    print(f"Alvo do banco: {_alvo(settings.database_url)}")
    print(f"Modo: {'GRAVA' if aplicar else 'relatório (nada é gravado)'}\n")

    artigos: list[tuple[Manual, str]] = []
    for manual in MANUAIS:
        caminho = pasta / manual.arquivo
        if not caminho.is_file():
            raise ImportacaoRecusadaError(
                f"{manual.arquivo}: não está em {pasta}. Os três manuais são obrigatórios "
                "— importar dois e deixar o terceiro para depois é o jeito de ele nunca "
                "entrar. Nada foi gravado."
            )
        limpo = converte(manual, caminho.read_text(encoding="utf-8"))
        artigos.append((manual, limpo))
        secoes = sum(1 for linha in limpo.splitlines() if linha.startswith(("## ", "### ")))
        senhas = limpo.count(MARCA_DE_SENHA_REDIGIDA)
        print(
            f"  {manual.titulo}\n"
            f"    {secoes} seções, {len(limpo)} caracteres, "
            f"{senhas} senha(s) redigida(s), produto declarado: {manual.produto}"
        )

    motor = create_async_engine(settings.database_url)
    try:
        fabrica = async_sessionmaker(motor, expire_on_commit=False)
        async with fabrica() as db:
            cadastro = [
                (pid, nome)
                for pid, nome in (await db.execute(select(Product.id, Product.name))).all()
            ]
            produtos = resolve_produtos(MANUAIS, cadastro)

            existentes = (
                (
                    await db.execute(
                        select(KBArticle.title).where(
                            KBArticle.title.in_([m.titulo for m, _ in artigos])
                        )
                    )
                )
                .scalars()
                .all()
            )
            if existentes:
                raise ImportacaoRecusadaError(
                    f"Já existe artigo com o título de: {', '.join(sorted(existentes))}. A "
                    "importação não sobrescreve nem duplica — arquive o artigo existente ou "
                    "revise-o na tela. Nada foi gravado."
                )

            print("\nTodos os três produtos resolvidos; nenhum artigo com o mesmo título.")
            if not aplicar:
                print("Relatório apenas. Rode com --autor e --aplicar para gravar.")
                return 0

            if not autor_email:
                raise ImportacaoRecusadaError("--aplicar exige --autor <e-mail de quem assina>.")
            autor = (
                await db.execute(select(User).where(User.email == autor_email))
            ).scalar_one_or_none()
            if autor is None or autor.role not in (UserRole.admin, UserRole.technician):
                raise ImportacaoRecusadaError(
                    f"{autor_email}: não existe, ou não é da equipe. Artigo da Base de "
                    "Conhecimento só é escrito por técnico ou admin — a mesma regra da tela."
                )

            await grava_rascunhos(db, artigos, produtos, autor.id)
            print(f"\nGravados {len(artigos)} artigos em RASCUNHO. Leia e publique pela tela.")
            return 0
    finally:
        await motor.dispose()


def main() -> int:
    # O console do Windows abre em cp1252, e "→" e "—" derrubavam o script da
    # ingestão antes da primeira linha. Script roda na máquina de quem administra.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Importa os manuais técnicos para a KB.")
    parser.add_argument("--pasta", default=os.environ.get("HELO_MANUAIS_DIR"))
    parser.add_argument("--autor", help="e-mail de quem assina os artigos (técnico ou admin)")
    parser.add_argument("--aplicar", action="store_true", help="grava de verdade")
    args = parser.parse_args()

    if not args.pasta:
        print("Informe --pasta ou HELO_MANUAIS_DIR.", file=sys.stderr)
        return 2
    try:
        return asyncio.run(_importa(Path(args.pasta), args.autor, args.aplicar))
    except (ImportacaoRecusadaError, CredencialNaoRedigidaError) as exc:
        print(f"\nRECUSADO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
