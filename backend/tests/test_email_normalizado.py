"""
E-mail é identidade sem distinção de maiúsculas.

Medido em 15/09: o `EmailStr` normaliza só o domínio e preserva a caixa da
parte local, e todas as buscas comparam igualdade exata — `Fulano@x.com` e
`fulano@x.com` viravam DUAS contas para o sistema e UMA caixa postal no mundo
real. Consequências: conta fantasma por dedo no shift, "senha incorreta"
inexplicável no login com caixa diferente, e reset de senha mexendo só numa
das contas gêmeas. Produção foi conferida no mesmo dia: zero duplicatas —
esta regra fecha a porta enquanto ela ainda está limpa.

A regra viaja no tipo (`EmailNormalizado`), como o CNPJ em
`app/utils/documents.py`: declarar o tipo traz a normalização junto, e
esquecer dela exige contrariar o tipo. O passado é do script
`scripts/normaliza_emails.py`; a trava final é o índice único em
`lower(email)` da migration.
"""

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from app.schemas.auth import EmailRequest, LoginRequest, RegisterRequest
from app.schemas.user import UserCreate
from app.utils.email_normalizado import EmailNormalizado
from scripts.normaliza_emails import planeja_normalizacao

MISTO = "FuLaNo@ExEmPlo.COM"
MINUSCULO = "fulano@exemplo.com"


def test_o_tipo_poe_o_email_inteiro_em_minusculas():
    """O EmailStr sozinho baixa só o domínio — o tipo baixa a parte local."""
    assert TypeAdapter(EmailNormalizado).validate_python(MISTO) == MINUSCULO


@pytest.mark.parametrize(
    ("classe", "extras"),
    [
        (LoginRequest, {"password": "qualquer"}),
        (
            RegisterRequest,
            {"name": "Fulano", "password": "SenhaForte1", "lgpd_consent": True},
        ),
        (EmailRequest, {}),
        (UserCreate, {"name": "Fulano", "password": "SenhaForte1"}),
    ],
)
def test_toda_entrada_de_email_normaliza(classe, extras):
    """Cadastro, login, esqueci-a-senha e criação por admin falam a mesma língua."""
    obj = classe(email=MISTO, **extras)
    assert obj.email == MINUSCULO


def test_nenhum_schema_declara_emailstr_cru():
    """Guard de fonte, no padrão da casa: o próximo campo de e-mail de entrada
    declarado como `EmailStr` puro nasceria sem a normalização, em silêncio."""
    import app.schemas.auth as auth_schemas
    import app.schemas.user as user_schemas

    for modulo in (auth_schemas, user_schemas):
        fonte = Path(modulo.__file__).read_text(encoding="utf-8")
        assert (
            "email: EmailStr" not in fonte
        ), f"{modulo.__name__} declara EmailStr cru — usar EmailNormalizado"


# ── O planejador do script de backfill ────────────────────────


def test_planejador_normaliza_so_o_que_precisa():
    """Linha já minúscula fica de fora — é o que torna o script idempotente."""
    mudancas, colisoes = planeja_normalizacao([(1, "Fulano@x.com"), (2, "ja@minusculo.com")])
    assert mudancas == [(1, "Fulano@x.com", "fulano@x.com")]
    assert colisoes == []


def test_planejador_nunca_toca_colisao():
    """Normalizar uma das gêmeas fundiria identidades — a decisão é humana,
    e as duas linhas seguem intactas no relatório."""
    mudancas, colisoes = planeja_normalizacao(
        [(1, "Fulano@x.com"), (2, "fulano@x.com"), (3, "Outro@y.com")]
    )
    assert mudancas == [(3, "Outro@y.com", "outro@y.com")]
    assert colisoes == [("fulano@x.com", ["Fulano@x.com", "fulano@x.com"])]
