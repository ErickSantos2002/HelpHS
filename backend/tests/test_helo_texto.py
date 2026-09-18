"""
O texto da base da Helô: o corte em trechos, a redação e o detector.

Todo texto daqui é SINTÉTICO. Nenhum trecho de manual real entra neste
arquivo, e a senha usada nos testes é inventada — o repositório é público, e
copiar o manual do Phoebus para cá seria publicar exatamente o que a redação
existe para esconder.

A primeira metade veio de `test_ingestao_manuais.py`, que morreu junto com a
ingestão por arquivo em 10/09/2026: são as mesmas funções, agora compartilhadas
pela importação dos manuais e pela indexação dos artigos. A segunda metade é o
corte de ARTIGO em markdown, que é o que a Helô lê desde então.
"""

import pytest

from app.services.helo_texto import (
    MARCA_DE_SENHA_REDIGIDA,
    CredencialNaoRedigidaError,
    Trecho,
    _corta_numerada,
    confere_redacao,
    corta_artigo,
    descarta,
    redige,
    suspeitas,
)

# ── O contador crescente ─────────────────────────────────────


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


# ── Subdivisão ───────────────────────────────────────────────


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


# ── Redação ──────────────────────────────────────────────────


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


# ── Forma, não tamanho ───────────────────────────────────────


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


# ── Detector largo, redator preciso ──────────────────────────


def test_o_detector_pega_a_forma_que_o_redator_perde():
    """
    A razão de detector e redator serem funções diferentes.

    O redator é preciso: conhece a forma exata do manual do Phoebus. Padrão
    preciso erra por omissão, e a omissão aqui é MUDA — senha que escapa não é
    redigida e também não marca o trecho, então o resultado fica
    indistinguível de "não havia senha".
    """
    sem_dois_pontos = "3. Digite a senha 987654 e confirme."

    assert redige(sem_dois_pontos)[1] is False, "o redator perde esta forma, e é esperado"
    assert suspeitas(sem_dois_pontos), "o detector NÃO pode perder"


def test_o_detector_nao_dispara_em_numero_formatado():
    """
    Largo não é indiscriminado — falso positivo aqui PARA a ingestão.

    "8.000 testes" e "R$ 4.900,00" aparecem no corpus inteiro. Senha vem crua;
    número de catálogo vem com separador.
    """
    assert not suspeitas("Memória: até 8.000 testes por carga")
    assert not suspeitas("Preço do Aparelho: R$ 4.900,00")
    assert not suspeitas("Calibração a cada 12 meses ou 5.000 testes")


def test_detector_disparou_e_redator_nao_redigiu_e_erro_fatal():
    """
    O contrato entre os dois: discordância PARA a ingestão.

    É o controle de segurança do pior conteúdo do corpus. Ele não pode falhar
    em silêncio — falso positivo custa alguém olhar uma linha; falso negativo
    custa uma senha de administrador publicada na base que responde cliente.
    """
    bruto = "1. Menu\nDigite a senha 987654 para entrar."
    # O trecho vai para o banco com os dígitos intactos: é o cenário do defeito.
    trechos = [Trecho(secao="1. Menu", conteudo=bruto, exige_credencial=False, ordem=0)]

    with pytest.raises(CredencialNaoRedigidaError) as erro:
        confere_redacao("Fake.txt", bruto, trechos)

    assert "Fake.txt:2" in str(erro.value), "a mensagem precisa dizer arquivo e LINHA"
    assert "987654" not in str(erro.value), "a mensagem não transcreve a senha"


def test_quando_o_redator_fez_o_trabalho_nao_ha_erro():
    """A conferência é sobre os dígitos sobreviverem, não sobre quem rodou."""
    bruto = "1. Menu\nSenha: 987654"
    limpo, _ = redige(bruto)
    trechos = [Trecho(secao="1. Menu", conteudo=limpo, exige_credencial=True, ordem=0)]

    confere_redacao("Fake.txt", bruto, trechos)  # não levanta


# ── O artigo da Base de Conhecimento ──────────────────────────


def test_o_artigo_corta_por_secao_e_a_subsecao_leva_o_nome_do_pai():
    """
    Sozinho, "1. Resultado" é ambíguo num manual que também tem "1. Introdução".

    O nome da seção é o que a Helô cita como fonte, e fonte ambígua não se
    confere. É a hierarquia que o `_subdivide` reconstruía nos manuais
    numerados, agora declarada pelo próprio markdown.
    """
    artigo = (
        "## 1. Introdução\n"
        "O aparelho mede o teor alcoólico no ar expirado pelo sopro.\n\n"
        "## 7. Configurações\n"
        "Os ajustes abaixo ficam no menu de configuração do aparelho.\n\n"
        "### 1. Resultado na tela\n"
        "Escolha entre exibir o valor numérico ou apenas aprovado e reprovado.\n"
    )

    trechos, _ = corta_artigo("Manual do Teste", artigo)

    assert [t.secao for t in trechos] == [
        "1. Introdução",
        "7. Configurações",
        "7. Configurações → 1. Resultado na tela",
    ]
    assert [t.ordem for t in trechos] == [0, 1, 2]


def test_a_primeira_linha_do_trecho_e_o_titulo_sem_a_marcacao():
    """
    O texto do trecho é o que vira vetor, e o teto de distância foi MEDIDO com
    trechos que começavam pelo cabeçalho do manual em texto puro. Deixar o
    `###` no texto mudaria o vetor de todo trecho, e a medição deixaria de
    valer sem nada quebrar visivelmente.
    """
    trechos, _ = corta_artigo(
        "X", "## 8.1 Ajustar Data e Hora\nMenu, Settings, Date e Time, e confirme.\n"
    )

    assert trechos[0].conteudo.splitlines()[0] == "8.1 Ajustar Data e Hora"
    assert "#" not in trechos[0].conteudo


def test_artigo_sem_titulo_nenhum_vira_um_trecho_so():
    """
    Artigo curto escrito na tela, sem `##`, não pode ficar invisível.

    Sem este caso o corte devolveria lista vazia — nenhum título, nenhum
    trecho —, e o artigo publicado nunca chegaria às respostas, sem erro em
    lugar nenhum. Vira um trecho só, com o título do artigo.
    """
    trechos, _ = corta_artigo(
        "Como higienizar o bocal",
        "Lave o bocal com água morna e sabão neutro, e deixe secar à sombra antes de usar.",
    )

    assert len(trechos) == 1
    assert trechos[0].secao == "Como higienizar o bocal"


def test_o_preambulo_antes_do_primeiro_titulo_leva_o_nome_do_artigo():
    """Texto antes do primeiro `##` é do artigo, e não some — a lição do EBS-010."""
    trechos, _ = corta_artigo(
        "Manual do Teste",
        "Este manual cobre a operação diária do aparelho e seus cuidados.\n\n"
        "## 1. Ligar\nPressione o botão lateral por três segundos até acender.\n",
    )

    assert trechos[0].secao == "Manual do Teste"
    assert "operação diária" in trechos[0].conteudo


def test_a_regua_de_iguais_nao_entra_no_trecho():
    """
    Em markdown, `===` abaixo de texto vira título NÍVEL 1. No trecho, é
    formatação e não conteúdo — não pode entrar no vetor.
    """
    trechos, _ = corta_artigo(
        "X", "## 7. Configurações\n===========\nOs ajustes abaixo ficam no menu do aparelho.\n"
    )

    assert "===" not in trechos[0].conteudo


def test_secao_sem_corpo_e_descartada_com_o_motivo():
    """Todo descarte diz o porquê — o descarte mudo foi o defeito da ingestão por arquivo."""
    trechos, descartes = corta_artigo(
        "X",
        "## 8. Configurações\n\n## 9. Bateria\nCarregue pelo cabo USB-C até a tela mostrar cem.\n",
    )

    assert [t.secao for t in trechos] == ["9. Bateria"]
    assert descartes[0][0] == "8. Configurações"
    assert descartes[0][2] == "só o título, sem corpo"


def test_a_marca_de_redacao_acende_a_credencial_no_trecho():
    """
    A importação redige a senha ANTES de o artigo existir e deixa a marca; a
    indexação lê a marca para acender `exige_credencial_admin`. Sem isso, o
    trecho que ensina o menu protegido perderia o aviso — e a Helô entregaria o
    procedimento sem dizer que ele depende de uma senha que ela não pode dar.
    """
    artigo = (
        "## 7. Menu avançado\n"
        f"Entre no menu avançado. Senha de configuração: {MARCA_DE_SENHA_REDIGIDA}\n"
        "Escolha a opção de exibição do resultado.\n"
    )

    trechos, _ = corta_artigo("X", artigo)

    assert trechos[0].exige_credencial is True


def test_a_marca_e_exatamente_o_que_o_redator_escreve():
    """
    O acoplamento entre dois momentos, preso num teste só.

    Se alguém mudar o texto da redação e não a constante, a importação passaria
    a escrever uma marca que a indexação não reconhece — e todo trecho de menu
    protegido perderia o aviso, em silêncio.
    """
    limpo, _ = redige("Senha: 1234")

    assert MARCA_DE_SENHA_REDIGIDA in limpo


def test_senha_digitada_na_tela_e_redigida_na_indexacao():
    """
    A rede embaixo da porta. A porta é a importação; isto pega quem digitou uma
    senha depois, direto na tela. A página continua mostrando — ela é da Base
    de Conhecimento —, mas a Helô não repete.
    """
    trechos, _ = corta_artigo(
        "X", "## Menu\nPara entrar, use o código de acesso: 4321 e confirme.\n"
    )

    assert "4321" not in trechos[0].conteudo
    assert trechos[0].exige_credencial is True


def test_senha_que_o_redator_perde_levanta_na_indexacao():
    """O detector largo continua fatal aqui; quem chama decide o que fazer com isso."""
    with pytest.raises(CredencialNaoRedigidaError):
        corta_artigo("Artigo X", "## Menu\nDigite a senha 987654 e confirme a entrada no menu.\n")
