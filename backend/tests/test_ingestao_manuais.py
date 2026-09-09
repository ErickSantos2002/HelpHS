"""
O recorte e a redação dos manuais da Helô.

Todo texto daqui é SINTÉTICO. Nenhum trecho de manual real entra neste
arquivo, e a senha usada nos testes é inventada — o repositório é público, e
copiar o manual do Phoebus para cá seria publicar exatamente o que a redação
existe para esconder.

Os testes batem nas funções puras. A gravação no banco tem o seu próprio
caminho e não é exercitada aqui: o que pode dar errado nela é a idempotência,
que depende de Postgres de verdade.
"""

import pytest

from scripts.ingere_manuais import (
    _MINIMO,
    FONTES,
    Fonte,
    _corta_numerada,
    recorta,
    redige,
)

# ── O contador crescente ──────────────────────────────────────


def test_o_contador_crescente_ignora_passo_de_procedimento():
    """
    A armadilha do corpus: passo de procedimento tem a mesma forma de título.

    Uma regex de `^N.` casa "3. Aperte o botão" dentro da seção 2 e cria um
    trecho que começa no meio de uma instrução. No Phoebus são quarenta e sete
    falsos positivos contra doze títulos reais. O que separa os dois é a
    sequência: seção 3 vem depois da 2; passo 3 aparece dentro dela.
    """
    texto = [
        "1. Introdução",
        "corpo da introdução",
        "2. Passo a Passo",
        "1. Ligue o aparelho",
        "2. Aguarde o aquecimento",
        "3. Sopre por cinco segundos",
        "3. Especificações",
        "corpo das especificações",
    ]

    titulos = [t for t, _ in _corta_numerada(texto)]

    assert titulos == ["1. Introdução", "2. Passo a Passo", "3. Especificações"]


def test_a_secao_leva_os_passos_dela_junto():
    """O passo não vira título, mas continua dentro do trecho da seção."""
    texto = [
        "1. Introdução",
        "corpo",
        "2. Passo a Passo",
        "1. Ligue o aparelho",
        "2. Sopre",
    ]

    corpo = dict(_corta_numerada(texto))["2. Passo a Passo"]

    assert "1. Ligue o aparelho" in corpo
    assert "2. Sopre" in corpo


def test_numeracao_fora_de_ordem_nao_abre_secao():
    """Documento que pula do 1 para o 7 não ganha uma seção 7 por engano."""
    texto = ["1. Introdução", "corpo", "7. Coisa Solta", "mais corpo"]

    assert [t for t, _ in _corta_numerada(texto)] == ["1. Introdução"]


# ── Subdivisão ────────────────────────────────────────────────


def test_secao_com_subsecoes_e_quebrada():
    """
    A seção 7 do Phoebus reúne seis procedimentos e 3,4 mil caracteres.

    Um vetor só para seis assuntos não se parece com nenhuma das seis
    perguntas que o cliente faria — e as duas senhas caem no mesmo trecho,
    fazendo a marca de credencial deixar de dizer QUAL procedimento a exige.
    """
    corpo = "x" * 200
    texto = [
        "1. Configurações",
        "preâmbulo da seção " + corpo,
        "8.1 Ajustar Data",
        corpo,
        "8.2 Alterar Idioma",
        corpo,
    ]

    titulos = [t for t, _ in _corta_numerada(texto)]

    assert titulos == [
        "1. Configurações",
        "1. Configurações → 8.1 Ajustar Data",
        "1. Configurações → 8.2 Alterar Idioma",
    ]


def test_secao_com_uma_subsecao_so_nao_e_quebrada():
    """Quebrar por um título só troca um trecho bom por dois pedaços."""
    texto = ["1. Configurações", "corpo", "8.1 Ajustar Data", "mais corpo"]

    assert [t for t, _ in _corta_numerada(texto)] == ["1. Configurações"]


# ── Redação ───────────────────────────────────────────────────


def test_a_senha_sai_e_o_procedimento_fica():
    """
    Nem excluir nem só redigir: as duas metades da mesma decisão.

    Excluir o trecho jogaria fora o procedimento e produziria escalada cega —
    a busca não acha nada, a Helô escala por NADA ENCONTRADO e ninguém sabe
    por quê. Redigir sem marcar entregaria o procedimento sem avisar que ele
    depende de uma senha que a Helô não pode dar.
    """
    texto = "Acesse o menu avançado.\nSenha de configuração: 246810\nEscolha a opção 3."

    limpo, exigia = redige(texto)

    assert exigia is True
    assert "246810" not in limpo
    assert "REDIGIDO" in limpo
    assert "Acesse o menu avançado." in limpo
    assert "Escolha a opção 3." in limpo


def test_texto_sem_senha_nao_e_marcado():
    """Marcar por engano faz a Helô escalar pergunta que ela sabia responder."""
    limpo, exigia = redige("Aperte o botão azul por três segundos.")

    assert exigia is False
    assert limpo == "Aperte o botão azul por três segundos."


def test_o_link_do_drive_sai_sem_marcar_credencial():
    """
    Link privado mandado a cliente externo é vazamento com a nossa assinatura.

    Sai da base até alguém confirmar que é público — mas não é senha, então
    não escala.
    """
    limpo, exigia = redige("Baixe em https://drive.google.com/file/d/abc123/view aqui.")

    assert "drive.google.com" not in limpo
    assert exigia is False


@pytest.mark.parametrize(
    "linha",
    [
        "Senha: 1234",
        "senha do menu: 12345678",
        "Código de acesso: 4321",
        "CÓDIGO: 987654",
    ],
)
def test_formas_de_escrever_senha_que_precisam_casar(linha):
    """A lista é generosa de propósito: deixar passar é publicar a senha."""
    limpo, exigia = redige(linha)

    assert exigia is True
    assert not any(c.isdigit() for c in limpo.split("REDIGIDO")[0])


# ── O corpus declarado ────────────────────────────────────────


def test_o_prompt_da_helo_nao_entra_na_base():
    """
    `Perfil da IA Helo.txt` é o system prompt v4.0 do WhatsApp, não um manual.

    Indexado, ela recuperaria as próprias regras de escalação como se fossem
    procedimento de aparelho — e ele sozinho é 22% do texto da pasta.
    """
    assert "Perfil da IA Helo.txt" not in {f.arquivo for f in FONTES}
    assert len(FONTES) == 8


def test_todo_arquivo_tem_produto_e_tipo_declarados():
    """Errar o produto manda o procedimento do aparelho errado para o cliente."""
    for f in FONTES:
        assert f.produto, f.arquivo
        assert f.tipo is not None, f.arquivo
        assert f.corte in {"numerada", "regua", "markdown", "emoji"}, f.arquivo


def test_as_cinco_fichas_comerciais_estao_marcadas_como_comerciais():
    """A busca técnica filtra por tipo; ficha marcada errado vira cotação no chamado."""
    comerciais = {f.arquivo for f in FONTES if f.tipo.value == "comercial"}

    assert comerciais == {
        "Deimos.txt",
        "EBS-010.txt",
        "iblow10pro.txt",
        "MarkX.txt",
        "Mercury.txt",
    }


# ── Trecho curto ──────────────────────────────────────────────


def test_trecho_curto_demais_nao_vira_trecho(tmp_path):
    """
    Cabeçalho e rodapé de contato casam com qualquer pergunta curta.

    São dezenas de caracteres sem procedimento nenhum: no ranking vetorial
    competem com o trecho certo e às vezes ganham.
    """
    arquivo = tmp_path / "Fake.txt"
    arquivo.write_text(
        "1. Curta\nnada\n2. Longa\n" + ("conteúdo de verdade " * 20),
        encoding="utf-8",
    )
    fonte = Fonte("Fake.txt", "Titan", FONTES[0].tipo, "numerada", "Falso")

    doc = recorta(fonte, arquivo)

    assert [t.secao for t in doc.trechos] == ["2. Longa"]
    assert all(len(t.conteudo) >= _MINIMO for t in doc.trechos)


def test_a_ordem_do_arquivo_vira_a_ordem_do_trecho(tmp_path):
    """ "8.10" vem depois de "8.9"; ordenar pelo título como string inverteria."""
    arquivo = tmp_path / "Fake.txt"
    corpo = "conteúdo de verdade " * 10
    arquivo.write_text(f"1. Um\n{corpo}\n2. Dois\n{corpo}\n3. Três\n{corpo}", encoding="utf-8")
    fonte = Fonte("Fake.txt", "Titan", FONTES[0].tipo, "numerada", "Falso")

    doc = recorta(fonte, arquivo)

    assert [t.ordem for t in doc.trechos] == [0, 1, 2]
    assert [t.secao for t in doc.trechos] == ["1. Um", "2. Dois", "3. Três"]


def test_o_hash_muda_quando_o_arquivo_muda(tmp_path):
    """É o que torna a ingestão idempotente sem comparar trecho a trecho."""
    arquivo = tmp_path / "Fake.txt"
    corpo = "conteúdo de verdade " * 10
    fonte = Fonte("Fake.txt", "Titan", FONTES[0].tipo, "numerada", "Falso")

    arquivo.write_text(f"1. Um\n{corpo}", encoding="utf-8")
    primeiro = recorta(fonte, arquivo).hash

    arquivo.write_text(f"1. Um\n{corpo}\n2. Dois\n{corpo}", encoding="utf-8")
    segundo = recorta(fonte, arquivo).hash

    assert primeiro != segundo
    assert len(primeiro) == 64
