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

import uuid

import pytest

from app.models.models import HeloDocType
from scripts.ingere_manuais import (
    FONTES,
    CorpusInconsistenteError,
    Fonte,
    _corta_emoji,
    _corta_numerada,
    _corta_regua,
    casa_produtos,
    chave,
    descarta,
    exige_produtos_distinguiveis,
    recorta,
    redige,
)

# Os sete produtos que o `app/seeds.py` grava, com a grafia exata dele. Repetir
# aqui é de propósito: se alguém renomear um produto no seed, este teste cai e
# a pessoa descobre que a base da Helô depende daquele nome — em vez de a
# ingestão passar a não casar nada, em silêncio.
_PRODUTOS_DO_SEED = (
    "Deimos",
    "EBS-010",
    "iBlow 10 Pro",
    "Mark X",
    "Mercury",
    "Phoebus",
    "Titan",
)


def _catalogo(*nomes: str) -> dict[str, uuid.UUID]:
    return {nome: uuid.uuid4() for nome in (nomes or _PRODUTOS_DO_SEED)}


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


def test_o_corpus_nao_declara_produto():
    """
    O produto vem da tabela `products`, não desta lista.

    Declarar aqui duplicaria o seed em texto solto: no dia em que alguém
    renomeasse um produto, a lista continuaria dizendo o nome antigo e a busca
    passaria a devolver nada, em silêncio. E, escrito à mão, "casou com dois
    produtos" seria impossível por construção — a ambiguidade só apareceria
    como resposta errada na tela do cliente.
    """
    assert not hasattr(FONTES[0], "produto")


def test_todo_arquivo_tem_tipo_e_corte_declarados():
    """O que continua declarado: tipo e estratégia de corte, por arquivo."""
    for f in FONTES:
        assert f.tipo is not None, f.arquivo
        assert f.corte in {"numerada", "regua", "markdown", "emoji"}, f.arquivo
        assert f.titulo, f.arquivo


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
    Bloco que é só título não vira trecho — e o descarte é ANUNCIADO.

    O piso por tamanho descartava procedimento de verdade em silêncio. O que
    desqualifica um bloco é não ter corpo, não ser curto.
    """
    arquivo = tmp_path / "Fake.txt"
    arquivo.write_text(
        "1. Curta\nnada\n2. Longa\n" + ("conteúdo de verdade " * 20),
        encoding="utf-8",
    )
    fonte = Fonte("Fake.txt", FONTES[0].tipo, "numerada", "Falso")

    doc = recorta(fonte, arquivo)

    assert [t.secao for t in doc.trechos] == ["2. Longa"]
    assert [titulo for titulo, _, _ in doc.descartes] == ["1. Curta"]
    assert doc.descartes[0][2], "todo descarte precisa dizer o motivo"


def test_a_ordem_do_arquivo_vira_a_ordem_do_trecho(tmp_path):
    """ "8.10" vem depois de "8.9"; ordenar pelo título como string inverteria."""
    arquivo = tmp_path / "Fake.txt"
    corpo = "conteúdo de verdade " * 10
    arquivo.write_text(f"1. Um\n{corpo}\n2. Dois\n{corpo}\n3. Três\n{corpo}", encoding="utf-8")
    fonte = Fonte("Fake.txt", FONTES[0].tipo, "numerada", "Falso")

    doc = recorta(fonte, arquivo)

    assert [t.ordem for t in doc.trechos] == [0, 1, 2]
    assert [t.secao for t in doc.trechos] == ["1. Um", "2. Dois", "3. Três"]


def test_o_hash_muda_quando_o_arquivo_muda(tmp_path):
    """É o que torna a ingestão idempotente sem comparar trecho a trecho."""
    arquivo = tmp_path / "Fake.txt"
    corpo = "conteúdo de verdade " * 10
    fonte = Fonte("Fake.txt", FONTES[0].tipo, "numerada", "Falso")

    arquivo.write_text(f"1. Um\n{corpo}", encoding="utf-8")
    primeiro = recorta(fonte, arquivo).hash

    arquivo.write_text(f"1. Um\n{corpo}\n2. Dois\n{corpo}", encoding="utf-8")
    segundo = recorta(fonte, arquivo).hash

    assert primeiro != segundo
    assert len(primeiro) == 64


# ── Casar arquivo com produto ─────────────────────────────────


def test_a_chave_normaliza_os_dois_lados():
    """
    Os dois casos que a comparação literal erra, e que motivaram a regra.

    O seed grava "iBlow 10 Pro" e "Mark X"; os arquivos são
    `Manual_Tecnico_iBlow10Pro.txt` e `MarkX.txt`.
    """
    assert chave("iBlow 10 Pro") == "iblow10pro"
    assert chave("Mark X") == "markx"
    assert chave("EBS-010") == "ebs010"
    assert chave("Manual_Tecnico_iBlow10Pro") == "manualtecnicoiblow10pro"
    assert chave("Manual Tecnico Titan") == "manualtecnicotitan"


def test_a_chave_tira_acento():
    """Nome de produto com acento é questão de tempo, e sai barato agora."""
    assert chave("Phoebus Ácido") == "phoebusacido"


@pytest.mark.parametrize("fonte", FONTES, ids=lambda f: f.arquivo)
def test_todo_arquivo_do_corpus_casa_com_exatamente_um_produto(fonte):
    """
    O corpus de hoje, contra os produtos que o seed grava.

    É o teste que prende a promessa: nenhum dos oito fica sem produto e
    nenhum casa com dois. Se alguém acrescentar um manual cujo nome não
    contenha o produto, este teste cai antes de a ingestão rodar.
    """
    assert len(casa_produtos(fonte, _catalogo())) == 1


def test_nenhum_produto_do_seed_e_pedaco_de_outro():
    """
    A propriedade que faz a contenção ser segura.

    Se "Mercury" fosse pedaço de "Mercury Plus", todo arquivo do Plus casaria
    com os dois — e um documento técnico pararia a ingestão. Melhor descobrir
    aqui do que no dia do cadastro do produto novo.
    """
    chaves = [chave(n) for n in _PRODUTOS_DO_SEED]

    for uma in chaves:
        outras = [c for c in chaves if c != uma]
        assert not any(uma in outra for outra in outras), uma


def test_tecnico_sem_produto_nenhum_e_erro_fatal():
    """
    Zero produto num procedimento técnico é o passo do Phoebus valendo para todos.

    Trecho sem vínculo vale para TODOS os aparelhos — o oposto do que a busca
    precisa. Parar é a única resposta certa.
    """
    fonte = Fonte("Manual_Tecnico_Aparelho_Novo.txt", HeloDocType.tecnico, "numerada", "Novo")

    with pytest.raises(CorpusInconsistenteError, match="casou com 0 produtos"):
        casa_produtos(fonte, _catalogo())


def test_tecnico_com_dois_produtos_e_erro_fatal():
    """
    Dois produtos mandam o procedimento errado, e não há palpite bom entre eles.

    Escolher o "mais parecido" resolveria o sintoma e mandaria o passo do
    aparelho errado para quem opera um instrumento de medição legal.
    """
    fonte = Fonte("Manual_Titan_e_Phoebus.txt", HeloDocType.tecnico, "numerada", "Dois")

    with pytest.raises(CorpusInconsistenteError, match="casou com 2 produtos"):
        casa_produtos(fonte, _catalogo())


def test_o_erro_nomeia_os_produtos_que_casaram():
    """Mensagem que não diz QUAIS casaram deixa o conserto para a adivinhação."""
    fonte = Fonte("Manual_Titan_e_Phoebus.txt", HeloDocType.tecnico, "numerada", "Dois")

    with pytest.raises(CorpusInconsistenteError) as erro:
        casa_produtos(fonte, _catalogo())

    assert "Phoebus" in str(erro.value)
    assert "Titan" in str(erro.value)


def test_ficha_comercial_sem_produto_tambem_e_erro_fatal():
    """
    Zero é fatal para todo tipo, e a tentação de abrir exceção tem nome.

    "Catálogo vale para todos" soa razoável e é o default que foi REMOVIDO do
    desenho: readmiti-lo pela porta do casamento frustrado recoloca o mesmo
    defeito com outro nome. Conteúdo genérico passa a existir no dia em que
    alguém o marcar de propósito, nunca porque o nome do arquivo não bateu.
    """
    fonte = Fonte("Catalogo Geral.txt", HeloDocType.comercial, "regua", "Catálogo")

    with pytest.raises(CorpusInconsistenteError, match="casou com 0 produtos"):
        casa_produtos(fonte, _catalogo())


def test_nao_casa_por_aproximacao():
    """
    Contenção é binária. `Marc X` não é `Mark X`, e não vira por semelhança.

    Distância de edição acertaria este caso e erraria o próximo, e o erro sai
    como procedimento do aparelho errado — não como exceção.
    """
    fonte = Fonte("Manual_Tecnico_Marc_X.txt", HeloDocType.tecnico, "numerada", "Quase")

    with pytest.raises(CorpusInconsistenteError):
        casa_produtos(fonte, _catalogo())


# ── Os cinco consertos ────────────────────────────────────────


def test_bloco_curto_com_corpo_fica():
    """
    O conserto do piso: 8.2 e 8.3 do Titan tinham 104 e 112 caracteres.

    O piso por tamanho descartava os dois com os vizinhos 8.1 (130) e 8.4
    (137) indexados. A base respondia "como ajusto a data" e ficava muda em
    "como coloco em português" — buraco parcial, e por isso invisível. O que
    desqualifica um bloco é não ter corpo, não ser curto.
    """
    # Corpo do tamanho do 8.2 de verdade — o trecho inteiro tinha 104
    # caracteres, dos quais uns 18 eram o título.
    curto_mas_com_corpo = (
        "8.2 Alterar Idioma\n"
        "Acesse Menu > Sistema > Idioma e escolha Português do Brasil.\n"
        "Confirme com OK."
    )

    assert descarta("8.2 Alterar Idioma", curto_mas_com_corpo) is None


def test_bloco_que_e_so_titulo_e_descartado_com_motivo():
    """O descarte mudo era o defeito de verdade: todo descarte diz o porquê."""
    assert descarta("8. Configurações", "8. Configurações") == "só o título, sem corpo"
    assert "abaixo de" in descarta("💸 Preço", "💸 Preço\nR$ 1,00")


def test_a_regua_como_sublinhado_nao_desloca_o_titulo():
    """
    O iblow10pro usa hifens SOB o cabeçalho; Deimos e MarkX usam ENTRE blocos.

    Tratados iguais, todo título do iblow10pro ficava deslocado em uma seção:
    o trecho se chamava "- Capacidade de realizar até 12 testes por minuto" e
    o cabeçalho real viajava no fim do trecho anterior. `secao` é o rótulo que
    a Helô cita como fonte.
    """
    setext = [
        "📍 Informações Comerciais",
        "-------------------------",
        "- doze testes por minuto",
        "🎯 Argumentos de Venda",
        "----------------------",
        "- bocal descartável",
    ]

    cortes = _corta_regua(setext)

    assert [t for t, _ in cortes] == ["📍 Informações Comerciais", "🎯 Argumentos de Venda"]
    assert "doze testes por minuto" in "\n".join(cortes[0][1])


def test_a_regua_como_separador_continua_separando():
    """Deimos e MarkX não podem quebrar com o conserto do iblow10pro."""
    separado = ["Bloco Um", "corpo um", "", "---", "Bloco Dois", "corpo dois"]

    assert [t for t, _ in _corta_regua(separado)] == ["Bloco Um", "Bloco Dois"]


def test_a_seta_nao_abre_trecho():
    """
    `→` é categoria Sm, e as respostas do FAQ do Mercury começam com ela.

    Aceitando Sm, as cinco respostas viravam títulos e o único trecho que
    sobrava se chamava "→ Não. O aparelho mostra os dados no visor" — uma
    RESPOSTA como rótulo de fonte, colada na pergunta seguinte. Citar fonte
    errada é pior do que não citar.
    """
    texto = [
        "✅ FAQ do Mercury",
        "1. Usa bocal descartável?",
        "→ Sim, o Mercury utiliza bocal descartável.",
        "2. Precisa de computador?",
        "→ Não. O aparelho mostra os dados no visor.",
    ]

    assert [t for t, _ in _corta_emoji(texto)] == ["✅ FAQ do Mercury"]


def test_o_preambulo_antes_do_primeiro_titulo_nao_some(tmp_path):
    """
    No EBS-010 o primeiro `##` está na linha 8, e o preço vinha antes.

    O preâmbulo era jogado fora sem passar por filtro nenhum: a ficha
    comercial ficava sem o preço, que é o que uma ficha comercial existe para
    responder.
    """
    arquivo = tmp_path / "Ficha.txt"
    arquivo.write_text(
        "EBS-010 — Ficha\nPreço do Aparelho: R$ 7.250,00\nPreço da Calibração: R$ 690,00\n"
        "## Destaques\n" + ("conteúdo de verdade " * 8),
        encoding="utf-8",
    )
    fonte = Fonte("Ficha.txt", HeloDocType.comercial, "markdown", "Ficha")

    doc = recorta(fonte, arquivo)

    assert "7.250,00" in doc.trechos[0].conteudo
    assert [t.secao for t in doc.trechos] == ["EBS-010 — Ficha", "Destaques"]


def test_o_hash_muda_quando_a_receita_muda_mesmo_com_o_arquivo_igual(tmp_path, monkeypatch):
    """
    O conserto que destrava todos os outros.

    Com o hash do arquivo bruto, melhorar o corte e rodar `--aplicar` de novo
    imprimia "inalterado, nada a fazer" nos oito documentos e o banco ficava
    com o corte velho — e, se uma senha tivesse escapado, com a senha velha.
    Este script existe para rodar várias vezes até o corte ficar bom.
    """
    arquivo = tmp_path / "Fake.txt"
    corpo = "conteúdo de verdade " * 10
    arquivo.write_text(f"1. Um\n{corpo}\n2. Dois\n{corpo}", encoding="utf-8")

    antes = recorta(Fonte("Fake.txt", HeloDocType.tecnico, "numerada", "Título A"), arquivo).hash
    depois = recorta(Fonte("Fake.txt", HeloDocType.tecnico, "numerada", "Título B"), arquivo).hash

    assert antes != depois, "mudar o título declarado precisa chegar ao banco"


# ── Produtos indistinguíveis ──────────────────────────────────


def test_produtos_com_a_mesma_chave_sao_erro_fatal():
    """
    `products.name` não tem unique no banco, e a checagem do endpoint é literal.

    "Titan" e "TITAN" entram os dois; pela chave normalizada são o mesmo
    produto. Um dicionário por nome guardaria só o último id, e os chamados do
    outro registro não recuperariam trecho nenhum — sem erro na tela.
    """
    um, outro = uuid.uuid4(), uuid.uuid4()

    with pytest.raises(CorpusInconsistenteError, match="mesma chave 'titan'"):
        exige_produtos_distinguiveis([(um, "Titan"), (outro, "TITAN")])


def test_o_erro_de_produto_duplicado_nomeia_os_dois_ids():
    """Sem os ids, a limpeza do cadastro vira caça ao tesouro."""
    um, outro = uuid.uuid4(), uuid.uuid4()

    with pytest.raises(CorpusInconsistenteError) as erro:
        exige_produtos_distinguiveis([(um, "Mark X"), (outro, "Mark-X")])

    assert str(um) in str(erro.value)
    assert str(outro) in str(erro.value)


def test_produtos_distinguiveis_passam():
    """Os sete do seed convivem sem colisão de chave."""
    catalogo = exige_produtos_distinguiveis([(uuid.uuid4(), n) for n in _PRODUTOS_DO_SEED])

    assert len(catalogo) == 7
