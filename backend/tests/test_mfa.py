"""Segundo fator: cifra do segredo e verificação do código.

Estes testes cobrem a camada de serviço — a que lida com o segredo em si. O
contrato HTTP do login com MFA é assunto de outro arquivo.

O ponto que mais importa aqui é a assimetria entre os dois materiais secretos
do MFA, e vários testes existem só para fixá-la: o segredo TOTP é **cifrado**
(o servidor precisa recuperá-lo para recalcular o código), enquanto o código de
recuperação é **hasheado** (o servidor só precisa comparar). Trocar um pelo
outro quebra o sistema de um jeito que só aparece em produção.
"""

import pytest

from app.core.config import get_settings
from app.services import mfa

# Chave Fernet fixa, gerada só para os testes. Não vale em lugar nenhum.
_CHAVE_DE_TESTE = "kZ7QpX3vN9sT2wR6yB1mL4hG8dF0jC5aE7nU3iO9kQs="


def _troca_chave(valor: str) -> str:
    """Escreve na instância cacheada e devolve o valor anterior.

    Deliberadamente NÃO usa `get_settings.cache_clear()`. Outros testes desta
    suíte — `test_seeds.py` é o caso — guardam uma referência à instância que
    `get_settings()` devolveu e mutam atributos nela. Limpar o cache faz a
    chamada seguinte construir um objeto novo, e aquelas referências passam a
    configurar um órfão: o teste ajusta um `Settings` e o código lê outro.
    """
    settings = get_settings()
    anterior = settings.mfa_secret_encryption_key
    settings.mfa_secret_encryption_key = valor
    return anterior


@pytest.fixture
def mfa_configurado():
    """Liga o MFA com uma chave de cifra válida."""
    anterior = _troca_chave(_CHAVE_DE_TESTE)
    yield
    _troca_chave(anterior)


@pytest.fixture
def mfa_sem_chave():
    anterior = _troca_chave("")
    yield
    _troca_chave(anterior)


# ── Disponibilidade ───────────────────────────────────────────


def test_sem_chave_o_mfa_se_declara_indisponivel(mfa_sem_chave):
    assert mfa.mfa_disponivel() is False


def test_com_chave_o_mfa_se_declara_disponivel(mfa_configurado):
    assert mfa.mfa_disponivel() is True


def test_sem_chave_cifrar_levanta_em_vez_de_inventar_uma(mfa_sem_chave):
    """Sem chave, o serviço para. Não existe chave de fallback.

    Uma chave embutida no código serviria para cifrar e decifrar sem erro
    nenhum, e o sistema pareceria funcionar — protegendo o segredo contra
    exatamente ninguém, já que o repositório é onde a chave estaria.
    """
    with pytest.raises(mfa.MfaIndisponivelError):
        mfa.cifrar_segredo("QUALQUERCOISA")


# ── Cifra do segredo ──────────────────────────────────────────


def test_o_segredo_volta_igual_depois_de_cifrado(mfa_configurado):
    segredo = mfa.gerar_segredo()

    assert mfa.decifrar_segredo(mfa.cifrar_segredo(segredo)) == segredo


def test_o_texto_cifrado_nao_contem_o_segredo(mfa_configurado):
    """Prova que houve cifra, e não codificação."""
    segredo = mfa.gerar_segredo()

    cifrado = mfa.cifrar_segredo(segredo)

    assert segredo not in cifrado


def test_cifrar_duas_vezes_produz_textos_diferentes(mfa_configurado):
    """Fernet leva IV e timestamp próprios em cada operação.

    Se as duas saídas fossem iguais, a cifra seria determinística — e um dump
    do banco entregaria quais contas compartilham segredo, além de abrir espaço
    para ataque por dicionário sobre os segredos possíveis.
    """
    segredo = mfa.gerar_segredo()

    assert mfa.cifrar_segredo(segredo) != mfa.cifrar_segredo(segredo)


def test_texto_cifrado_com_outra_chave_nao_decifra(mfa_configurado):
    """A chave é o que protege, não a obscuridade do formato."""
    cifrado = mfa.cifrar_segredo(mfa.gerar_segredo())

    anterior = _troca_chave("9xV2bN8mK4jH6gF3dS1aQ7wE5rT0yU2iO4pL8zX6cA0=")
    try:
        with pytest.raises(mfa.SegredoIlegivelError):
            mfa.decifrar_segredo(cifrado)
    finally:
        _troca_chave(anterior)


def test_chave_malformada_falha_no_uso_e_nao_em_silencio():
    anterior = _troca_chave("isto-nao-e-uma-chave-fernet")
    try:
        with pytest.raises(mfa.MfaIndisponivelError):
            mfa.cifrar_segredo("QUALQUERCOISA")
    finally:
        _troca_chave(anterior)


# ── Geração do segredo ────────────────────────────────────────


def test_cada_segredo_gerado_e_diferente(mfa_configurado):
    assert len({mfa.gerar_segredo() for _ in range(20)}) == 20


def test_o_segredo_e_base32_valido_para_o_app_autenticador(mfa_configurado):
    import base64

    segredo = mfa.gerar_segredo()

    # Levanta se não for base32 — é o formato que Google Authenticator e
    # congêneres esperam no QR.
    base64.b32decode(segredo)


# ── Verificação do código ─────────────────────────────────────


def test_o_codigo_do_momento_e_aceito(mfa_configurado):
    import pyotp

    segredo = mfa.gerar_segredo()
    codigo = pyotp.TOTP(segredo).now()

    assert mfa.verificar_codigo(segredo, codigo) is True


def test_codigo_errado_e_recusado(mfa_configurado):
    segredo = mfa.gerar_segredo()

    assert mfa.verificar_codigo(segredo, "000000") is False


def test_codigo_de_outro_segredo_e_recusado(mfa_configurado):
    import pyotp

    codigo_alheio = pyotp.TOTP(mfa.gerar_segredo()).now()

    assert mfa.verificar_codigo(mfa.gerar_segredo(), codigo_alheio) is False


def test_a_janela_anterior_e_aceita_por_causa_do_relogio(mfa_configurado):
    """Trinta segundos de tolerância, não mais.

    O relógio do celular e o do servidor divergem, e sem tolerância nenhuma o
    usuário erra na virada do período. Uma janela para cada lado resolve isso;
    mais do que isso alarga a superfície de tentativa sem ganho de usabilidade.
    """
    import time

    import pyotp

    segredo = mfa.gerar_segredo()
    anterior = pyotp.TOTP(segredo).at(int(time.time()) - 30)

    assert mfa.verificar_codigo(segredo, anterior) is True


def test_codigo_de_muito_tempo_atras_e_recusado(mfa_configurado):
    import time

    import pyotp

    segredo = mfa.gerar_segredo()
    antigo = pyotp.TOTP(segredo).at(int(time.time()) - 600)

    assert mfa.verificar_codigo(segredo, antigo) is False


def test_codigo_com_espaco_e_aceito(mfa_configurado):
    """Os aplicativos mostram '123 456' e a pessoa copia com o espaço."""
    import pyotp

    segredo = mfa.gerar_segredo()
    codigo = pyotp.TOTP(segredo).now()

    assert mfa.verificar_codigo(segredo, f"{codigo[:3]} {codigo[3:]}") is True


def test_codigo_vazio_e_recusado_sem_levantar(mfa_configurado):
    assert mfa.verificar_codigo(mfa.gerar_segredo(), "") is False


def test_codigo_nao_numerico_e_recusado_sem_levantar(mfa_configurado):
    assert mfa.verificar_codigo(mfa.gerar_segredo(), "abcdef") is False


# ── Passo de tempo, para o antirreplay ────────────────────────


def test_casar_devolve_o_passo_do_codigo_atual(mfa_configurado):
    import time

    import pyotp

    segredo = mfa.gerar_segredo()

    passo = mfa.casar_codigo(segredo, pyotp.TOTP(segredo).now())

    assert passo == int(time.time()) // 30


def test_casar_distingue_a_janela_anterior_da_atual(mfa_configurado):
    """É essa distinção que o antirreplay consome.

    Se as duas janelas devolvessem o mesmo passo, marcar uma como usada
    invalidaria a outra e a tolerância de relógio deixaria de existir na
    prática.
    """
    import time

    import pyotp

    segredo = mfa.gerar_segredo()
    totp = pyotp.TOTP(segredo)
    agora = int(time.time())

    passo_atual = mfa.casar_codigo(segredo, totp.now())
    passo_anterior = mfa.casar_codigo(segredo, totp.at(agora - 30))

    assert passo_atual is not None and passo_anterior is not None
    assert passo_atual - passo_anterior == 1


def test_casar_devolve_none_para_codigo_errado(mfa_configurado):
    assert mfa.casar_codigo(mfa.gerar_segredo(), "000000") is None


def test_casar_devolve_none_sem_levantar_para_lixo(mfa_configurado):
    segredo = mfa.gerar_segredo()

    assert mfa.casar_codigo(segredo, "") is None
    assert mfa.casar_codigo(segredo, "abcdef") is None
    assert mfa.casar_codigo(segredo, "12") is None


def test_o_passo_e_estavel_dentro_da_mesma_janela(mfa_configurado):
    """Duas conferências do mesmo código dão o mesmo passo.

    Sem isso, marcar "usado" não pegaria o replay: a segunda tentativa geraria
    outra chave e passaria.
    """
    import pyotp

    segredo = mfa.gerar_segredo()
    codigo = pyotp.TOTP(segredo).now()

    assert mfa.casar_codigo(segredo, codigo) == mfa.casar_codigo(segredo, codigo)


# ── URI de provisionamento (o QR) ─────────────────────────────


def test_a_uri_traz_o_segredo_e_identifica_a_conta(mfa_configurado):
    segredo = mfa.gerar_segredo()

    uri = mfa.uri_de_provisionamento(segredo, "suelen@healthsafetytech.com")

    assert uri.startswith("otpauth://totp/")
    assert segredo in uri
    assert "suelen%40healthsafetytech.com" in uri or "suelen@healthsafetytech.com" in uri


def test_a_uri_nomeia_o_sistema_para_a_pessoa_achar_no_app(mfa_configurado):
    uri = mfa.uri_de_provisionamento(mfa.gerar_segredo(), "gabriel@healthsafetytech.com")

    assert "HelpHS" in uri
