"""
A importação dos três manuais para a Base de Conhecimento.

Todo texto daqui é SINTÉTICO, e a senha é inventada: o repositório é público,
e o manual do Phoebus traz senhas de verdade.

Os testes batem nas partes puras — a lista do que entra, o vínculo de produto
e a conversão para markdown. O caminho que grava foi provado RODANDO o script
contra um banco local com os manuais reais, que vivem fora do repositório.
"""

import uuid

import pytest

from app.services.helo_texto import (
    MARCA_DE_SENHA_REDIGIDA,
    CredencialNaoRedigidaError,
    _corta_numerada,
    corta_artigo,
    descarta,
)
from scripts.importa_manuais_para_kb import (
    MANUAIS,
    ImportacaoRecusadaError,
    Manual,
    chave,
    converte,
    resolve_produtos,
)

# Os sete produtos que o `app/seeds.py` grava, com a grafia exata dele. Se
# alguém renomear um produto no seed, este teste cai e a pessoa descobre que a
# importação depende daquele nome — em vez de a importação recusar em produção.
_PRODUTOS_DO_SEED = ("Deimos", "EBS-010", "iBlow 10 Pro", "Mark X", "Mercury", "Phoebus", "Titan")


def _cadastro(*nomes: str) -> list[tuple[uuid.UUID, str]]:
    return [(uuid.uuid4(), nome) for nome in (nomes or _PRODUTOS_DO_SEED)]


# ── O que entra ───────────────────────────────────────────────


def test_so_os_tres_manuais_tecnicos_entram():
    """
    As cinco fichas comerciais têm preço, e publicá-las poria tabela de preço
    na tela do cliente. O perfil da Helô é o prompt dela, não manual de
    aparelho. A ausência dos seis na lista é a decisão.
    """
    assert {m.produto for m in MANUAIS} == {"Phoebus", "Titan", "iBlow 10 Pro"}
    arquivos = " ".join(m.arquivo.lower() for m in MANUAIS)
    for fora in ("deimos", "ebs", "markx", "mercury", "perfil", "iblow10pro.txt"):
        assert fora not in arquivos.split(" ") or fora == "iblow10pro.txt"
    assert "iblow10pro.txt" not in [
        m.arquivo.lower() for m in MANUAIS
    ], "a ficha do iBlow fica fora"


def test_cada_manual_declara_um_produto_que_o_seed_grava():
    for manual in MANUAIS:
        assert manual.produto in _PRODUTOS_DO_SEED, manual.arquivo


def test_a_chave_iguala_as_grafias_do_mesmo_produto():
    assert chave("iBlow 10 Pro") == chave("IBLOW-10-PRO") == chave("iblow_10_pro")


# ── O vínculo: aqui, ausente é FATAL ──────────────────────────


def test_produto_declarado_que_nao_existe_no_cadastro_e_fatal():
    """
    Na tela, artigo sem produto é escolha — vale para todos. Aqui quem cria é
    máquina, e ninguém escolheu nada: o manual do Titan viraria universal por
    um casamento frustrado.
    """
    with pytest.raises(ImportacaoRecusadaError) as erro:
        resolve_produtos(MANUAIS, _cadastro("Phoebus", "iBlow 10 Pro"))

    assert "Manual Tecnico Titan.txt" in str(erro.value)
    assert "Nada foi gravado" in str(erro.value)


def test_dois_produtos_com_a_mesma_chave_e_fatal_com_os_dois_ids():
    """
    `products.name` não é único no banco. Um dicionário por nome guardaria só o
    último id, e os chamados do outro registro nunca veriam o manual.
    """
    cadastro = _cadastro("Phoebus", "iBlow 10 Pro", "Titan", "TITAN")
    ids = [str(pid) for pid, nome in cadastro if chave(nome) == "titan"]

    with pytest.raises(ImportacaoRecusadaError) as erro:
        resolve_produtos(MANUAIS, cadastro)

    for pid in ids:
        assert pid in str(erro.value)


def test_com_o_cadastro_do_seed_os_tres_resolvem():
    resolvidos = resolve_produtos(MANUAIS, _cadastro())

    assert set(resolvidos) == {m.arquivo for m in MANUAIS}


# ── A conversão para markdown ─────────────────────────────────

# Três passos no procedimento, e não dois: com dois, o "3." da seção seguinte
# continuaria a contagem dos passos e seria lido como o terceiro passo. É a
# regra de reinício do `_corta_numerada`, documentada lá — e o erro era deste
# dado, não dela.
_MANUAL = (
    "Documento Técnico — Aparelho de Teste\n"
    "=====================================\n"
    "1. Introdução\n"
    "O aparelho mede o teor alcoólico no ar expirado pelo sopro do usuário.\n"
    "2. Passo a Passo\n"
    "1. Ligue o aparelho pelo botão lateral.\n"
    "2. Aguarde o aquecimento completo do sensor.\n"
    "3. Sopre de forma contínua até ouvir o bipe.\n"
    "3. Configurações Detalhadas\n"
    "3.1 Ajustar Data e Hora\n"
    "Menu principal, Settings, Date e Time, e confirme com o botão.\n"
    "3.2 Menu Avançado\n"
    "Entre no menu avançado. Senha de configuração: 246810\n"
    "Escolha a opção de exibição e confirme.\n"
)
_FALSO = Manual("Teste.txt", "Titan", "Manual Técnico do Teste")


def test_o_manual_vira_markdown_com_secao_e_subsecao():
    """
    Sem `##`, "2. Passo a Passo" no começo da linha seria renderizado como item
    de lista numerada começando em 2; e a régua de `===` viraria título gigante.
    """
    artigo = converte(_FALSO, _MANUAL)

    assert "## 1. Introdução" in artigo
    assert "## 3. Configurações Detalhadas" in artigo
    assert "### 3.1 Ajustar Data e Hora" in artigo
    assert "=====" not in artigo
    assert artigo.count("1. Introdução") == 1, "o cabeçalho não pode aparecer duas vezes"


def test_os_passos_do_procedimento_continuam_lista_e_nao_viram_secao():
    """O contador crescente é o que separa seção de passo — e ele continua valendo."""
    artigo = converte(_FALSO, _MANUAL)

    assert "1. Ligue o aparelho pelo botão lateral." in artigo
    assert "## 1. Ligue" not in artigo


def test_a_senha_sai_do_artigo_antes_de_ele_existir():
    """
    Publicado quer dizer visível para o cliente. A redação da indexação
    protegeria só a base vetorial; o artigo precisa NASCER redigido.
    """
    artigo = converte(_FALSO, _MANUAL)

    assert "246810" not in artigo
    assert MARCA_DE_SENHA_REDIGIDA in artigo
    assert "Entre no menu avançado." in artigo, "o procedimento fica, só a senha sai"


def test_senha_que_o_redator_perde_recusa_a_importacao():
    """Detector largo, e fatal aqui como era na ingestão por arquivo."""
    com_senha_solta = _MANUAL + "4. Emergência\nDigite a senha 987654 para destravar o menu.\n"

    with pytest.raises(CredencialNaoRedigidaError):
        converte(_FALSO, com_senha_solta)


def test_o_artigo_importado_indexa_com_as_mesmas_secoes_do_manual():
    """
    A ponte entre os dois momentos, e o que mantém a medição do teto valendo.

    A importação transforma o manual em markdown; a indexação corta o markdown
    em trechos. As seções que saem do outro lado precisam ser as que o manual
    tinha — é o nome que a Helô cita como fonte, e é o que as 40 perguntas da
    medição do teto usaram como gabarito.
    """
    esperadas = [
        titulo
        for titulo, bloco in _corta_numerada(_MANUAL.splitlines())
        if descarta(titulo, "\n".join(bloco).strip()) is None
    ]

    trechos, _ = corta_artigo(_FALSO.titulo, converte(_FALSO, _MANUAL))
    obtidas = [t.secao for t in trechos if t.secao != _FALSO.titulo]

    assert obtidas == [t for t in esperadas if t != "Documento Técnico — Aparelho de Teste"]


# ── O caminho que grava ───────────────────────────────────────


@pytest.mark.asyncio
async def test_os_artigos_nascem_rascunho_lidos_pela_helo_e_vinculados():
    """
    As duas decisões de 10/09 que o caminho que grava carrega, provadas sem banco.

    Rascunho: publicado quer dizer visível para o cliente, e a primeira pessoa a
    ler o manual redigido não pode ser ele. Vínculo: sem ele o manual valeria
    para TODOS os aparelhos. E um commit só, depois dos três — ou entram os
    três, ou nenhum.
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.models.models import KBArticle, KBArticleStatus, kb_article_products
    from scripts.importa_manuais_para_kb import grava_rascunhos

    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = None  # slug livre
    db = MagicMock()
    db.execute = AsyncMock(return_value=resultado)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    produtos = {m.arquivo: uuid.uuid4() for m in MANUAIS}
    autor = uuid.uuid4()

    await grava_rascunhos(
        db, [(m, "## 1. Seção\nCorpo do manual.") for m in MANUAIS], produtos, autor
    )

    gravados = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], KBArticle)]
    assert len(gravados) == 3
    assert all(a.status is KBArticleStatus.draft for a in gravados)
    assert all(a.helo_pode_ler is True for a in gravados)
    assert all(a.author_id == autor for a in gravados)
    vinculos = [
        c.args[0].compile().params
        for c in db.execute.await_args_list
        if getattr(c.args[0], "table", None) is kb_article_products
    ]
    assert sorted(v["product_id"] for v in vinculos) == sorted(produtos.values())
    db.commit.assert_awaited_once()
