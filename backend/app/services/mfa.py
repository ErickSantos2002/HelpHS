"""Segundo fator por TOTP, para o staff.

O segredo TOTP é **cifrado**, não hasheado — e a diferença não é preferência.
Verificar um código exige recalculá-lo a partir do segredo a cada tentativa,
então o servidor precisa recuperá-lo em claro. Um hash tornaria a verificação
impossível.

O que protege o segredo, então, é a chave da cifra morar **fora do banco**, em
`MFA_SECRET_ENCRYPTION_KEY`. Um dump do banco, sozinho, não gera código nenhum.
Não existe chave embutida como alternativa: uma chave no repositório cifraria e
decifraria sem erro nenhum, o sistema pareceria funcionar, e o segredo estaria
protegido contra exatamente ninguém. Sem a variável, o MFA se declara
indisponível e o login segue como sempre foi.

O código de recuperação vai pelo caminho oposto — o servidor só precisa
comparar, nunca recuperar, então ele é hasheado como senha.

Nada deste módulo deve ser logado: nem segredo, nem código, nem a URI do QR.
"""

import base64
import hmac
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

# Nome que aparece no aplicativo autenticador, junto ao e-mail da pessoa.
_EMISSOR = "HelpHS"

# Período do TOTP, em segundos. É o default do pyotp e o que os autenticadores
# assumem; está aqui como nome porque o cálculo do passo de tempo depende dele.
_PERIODO = 30

# Uma janela de 30 s para cada lado. O relógio do celular e o do servidor
# divergem, e sem tolerância nenhuma a pessoa erra na virada do período.
# Mais do que isso alarga a superfície de tentativa sem ganho de usabilidade.
_JANELA = 1


class MfaIndisponivelError(RuntimeError):
    """A chave de cifra não está configurada, ou não é utilizável."""


class SegredoIlegivelError(RuntimeError):
    """O texto cifrado não abre com a chave atual."""


def _fernet() -> Fernet:
    """A chave é lida a cada chamada, de propósito.

    `get_settings` é cacheada, então o custo é desprezível — e ler aqui, em vez
    de no import do módulo, evita o defeito que o `llm.py` tem: lá a
    configuração é congelada na importação, e mudar a variável exige restart do
    contêiner.
    """
    bruta = get_settings().mfa_secret_encryption_key.strip()
    if not bruta:
        raise MfaIndisponivelError(
            "MFA_SECRET_ENCRYPTION_KEY não está configurada — sem ela o segredo "
            "do segundo fator não pode ser cifrado."
        )
    try:
        return Fernet(bruta.encode())
    except ValueError as exc:  # binascii.Error herda de ValueError
        raise MfaIndisponivelError(
            "MFA_SECRET_ENCRYPTION_KEY não é uma chave Fernet válida: espera-se "
            "32 bytes em base64 urlsafe."
        ) from exc


def mfa_disponivel() -> bool:
    """Se o segundo fator pode ser usado neste ambiente."""
    try:
        _fernet()
    except MfaIndisponivelError:
        return False
    return True


def gerar_segredo() -> str:
    """Segredo novo, em base32 — o formato que os autenticadores leem."""
    return pyotp.random_base32()


def cifrar_segredo(segredo: str) -> str:
    return _fernet().encrypt(segredo.encode()).decode()


def decifrar_segredo(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken as exc:
        raise SegredoIlegivelError(
            "O segredo guardado não abre com a chave atual. A chave foi trocada "
            "ou o registro veio de outro ambiente."
        ) from exc


def casar_codigo(segredo: str, codigo: str) -> int | None:
    """Devolve o **passo de tempo** que casou, ou `None` se nenhum casou.

    Saber qual janela casou é o que torna o antirreplay possível: quem consome
    marca aquele passo como usado, e o mesmo código não vale duas vezes dentro
    dos ~90 s em que continuaria matematicamente válido. `verify()` do pyotp só
    devolve um booleano, e com ele não há o que marcar.

    A comparação é em tempo constante. O ganho é pequeno num código de seis
    dígitos, mas o custo é uma linha.

    Entrada suja não levanta: os aplicativos exibem "123 456" e a pessoa cola
    com o espaço. Qualquer coisa que não seja dígito é recusa, não erro.
    """
    limpo = codigo.replace(" ", "").strip()
    if not limpo.isdigit():
        return None

    totp = pyotp.TOTP(segredo)
    agora = int(time.time())
    for deslocamento in range(-_JANELA, _JANELA + 1):
        instante = agora + deslocamento * _PERIODO
        if hmac.compare_digest(totp.at(instante), limpo):
            return instante // _PERIODO
    return None


def verificar_codigo(segredo: str, codigo: str) -> bool:
    """Só se o código vale, sem dizer qual janela casou.

    Serve o cadastro, onde não há replay a impedir: quem ativa já está dentro de
    uma sessão autenticada. O caminho do login usa `casar_codigo`.
    """
    return casar_codigo(segredo, codigo) is not None


def uri_de_provisionamento(segredo: str, email: str) -> str:
    """A URI `otpauth://` que vira QR na tela de cadastro.

    Carrega o segredo em claro — é o ponto do formato. Não pode ser logada nem
    guardada; existe só para atravessar a tela uma vez.
    """
    return pyotp.TOTP(segredo).provisioning_uri(name=email, issuer_name=_EMISSOR)


def normalizar_segredo_para_exibicao(segredo: str) -> str:
    """Agrupa o segredo de quatro em quatro, para quem digita à mão.

    Alguns autenticadores não leem QR e pedem o segredo digitado; ler
    trinta e dois caracteres corridos é onde o erro acontece.
    """
    base64.b32decode(segredo)  # recusa entrada que o app não aceitaria
    return " ".join(segredo[i : i + 4] for i in range(0, len(segredo), 4))
