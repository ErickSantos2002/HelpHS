"""
Telefone em E.164 — ponto único de normalização e validação.

**E.164 é a representação canônica INTERNA do HelpHS**, escolhida por ser o
padrão internacional de numeração e por não depender de fornecedor nenhum.
A conversão para o formato que a API4COM espera em `POST /calls.called` é
responsabilidade futura e isolada do adapter da integração — não mora aqui, e
a decisão de qual grafia enviar segue em aberto com o fornecedor.

Por que a regra viaja no TIPO, e não num validador copiado em cada modelo: é
o padrão já estabelecido pelo CNPJ (`app/utils/documents.py`) e pelo e-mail
(`app/utils/email_normalizado.py`). Declarar `TelefoneOpcional` traz a
normalização junto, e esquecer dela exige contrariar o tipo. O guard de fonte
em `tests/test_telefone.py` pega o próximo campo declarado como `str` cru.

`AfterValidator` e não `Before`: rodando depois da coerção, o valor que chega
já é `str | None` de verdade — com `Before`, um telefone digitado como número
entraria como `int` e estouraria `AttributeError` em vez de virar 422.

O que estas funções NÃO fazem:

- **Não adivinham DDI.** Um número sem `+` só é aceito se for reconhecível
  como brasileiro (10 ou 11 dígitos com DDD, ou 12/13 já começando em 55).
  Qualquer outra coisa exige o `+` explícito, porque não há como saber onde o
  código do país termina — e chutar produz número indiscável gravado como se
  fosse bom.
- **Não corrigem o passado.** A regra é prospectiva: linha antiga fora do
  formato continua no banco até um script avulso tratá-la, que é a regra da
  casa para dado histórico.
- **Não usam o histórico do fornecedor como referência.** O que a API4COM
  devolve em `GET /calls` descreve o que ela emitiu, não o que vale para
  `users.phone`.
"""

import re
from typing import Annotated

from pydantic import AfterValidator

_ERRO = (
    "Informe um telefone válido com DDD, por exemplo (81) 99999-9999. "
    "Para número de fora do Brasil, inclua o código do país com '+'."
)

# E.164 permite de 8 a 15 dígitos, e nenhum país tem código começando em zero.
_E164_MIN = 8
_E164_MAX = 15

_SO_DIGITOS = re.compile(r"\D")


def _valida_e164(digitos: str) -> None:
    if not (_E164_MIN <= len(digitos) <= _E164_MAX):
        raise ValueError(_ERRO)
    if digitos.startswith("0"):
        raise ValueError(_ERRO)


def _valida_nacional_brasileiro(nacional: str) -> None:
    """Valida o número brasileiro SEM o 55: DDD + assinante.

    Dez dígitos são fixo (assinante começa em 2–5) e onze são celular
    (assinante começa em 9, obrigatório desde 2016). A consequência prática de
    exigir o 9: `8199999999` — celular antigo de oito dígitos — é recusado, e
    é recusa correta, porque esse número não completa chamada há anos.
    """
    if len(nacional) not in (10, 11):
        raise ValueError(_ERRO)

    ddd = nacional[:2]
    # Não existe DDD começando em zero, nem com zero na segunda casa.
    if ddd[0] == "0" or ddd[1] == "0":
        raise ValueError(_ERRO)

    primeiro_do_assinante = nacional[2]
    if len(nacional) == 11:
        if primeiro_do_assinante != "9":
            raise ValueError(_ERRO)
    elif primeiro_do_assinante not in "2345":
        raise ValueError(_ERRO)


def normaliza_telefone(valor: str) -> str:
    """Devolve o telefone em E.164 (`+5581999999999`).

    Aceita as grafias que as pessoas realmente digitam — com máscara, com
    espaço, com ou sem DDI — desde que o resultado seja um número
    internacional válido.

    Raises:
        ValueError: se o valor não puder ser reduzido a um E.164 válido.
    """
    texto = valor.strip()
    if not texto:
        raise ValueError(_ERRO)

    digitos = _SO_DIGITOS.sub("", texto)

    if texto.startswith("+"):
        # Veio como internacional: validar de verdade a forma canônica, em vez
        # de preservar o que chegou só porque tinha um '+' na frente.
        _valida_e164(digitos)
        if digitos.startswith("55"):
            _valida_nacional_brasileiro(digitos[2:])
        return f"+{digitos}"

    if len(digitos) in (10, 11):
        _valida_nacional_brasileiro(digitos)
        return f"+55{digitos}"

    if len(digitos) in (12, 13) and digitos.startswith("55"):
        _valida_nacional_brasileiro(digitos[2:])
        return f"+{digitos}"

    raise ValueError(_ERRO)


def normaliza_telefone_opcional(valor: str | None) -> str | None:
    """Versão para campo opcional: ausência e campo limpo viram `None`.

    Limpar o campo no front manda `""`, não `null` — os formulários nascem com
    `phone: ""` no estado inicial. Recusar isso quebraria salvar o perfil sem
    telefone, que é exatamente o caminho das contas legadas.

    O que **não** é tratado como ausência é lixo com conteúdo: `"abc"` tem zero
    dígitos, mas é erro de digitação, não campo limpo. Vira `ValueError` em vez
    de virar `None` em silêncio — mesma escolha do `normaliza_cnpj_opcional`.
    """
    if valor is None or not valor.strip():
        return None
    return normaliza_telefone(valor)


def telefone_ausente(valor: str | None) -> bool:
    """Diz se não há telefone — nulo, vazio ou só espaço em branco.

    Existe para os guards do router não reimplementarem essa pergunta em
    quatro lugares, e para que "só espaços" nunca conte como telefone.
    """
    return valor is None or not valor.strip()


# ── Tipos para os schemas ─────────────────────────────────────

TelefoneObrigatorio = Annotated[str, AfterValidator(normaliza_telefone)]
TelefoneOpcional = Annotated[str | None, AfterValidator(normaliza_telefone_opcional)]
