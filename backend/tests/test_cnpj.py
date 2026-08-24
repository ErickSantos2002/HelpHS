"""
Normalização de CNPJ — ponto único.

O campo existe em duas tabelas e era gravado em formatos opostos: `users.cnpj`
saía do onboarding com 14 dígitos crus (o validador do `OnboardingUpdate` já
tirava a pontuação), enquanto `companies.cnpj` era texto livre, sem validador
nenhum, e o front ensinava o admin a digitar com máscara. Comparar os dois por
string nunca dava igual — foi o que impediu escopar a unicidade de série por
empresa e virou o levantamento de 24/08.

Estes testes prendem o contrato do `app/utils/documents`: **opcional é
opcional** (None e string vazia passam e viram None) e pontuação nunca chega
ao banco. O caso do campo opcional é o que mais importa: um validador que
recusasse None quebraria todo PATCH que não mexe em CNPJ.
"""

import pytest
from pydantic import ValidationError

from app.schemas.groups import CompanyCreate, CompanyUpdate
from app.schemas.user import OnboardingUpdate, UserUpdate
from app.utils.documents import normaliza_cnpj, normaliza_cnpj_opcional

# CNPJ real da Health & Safety, o mesmo usado nos testes de onboarding.
CNPJ_MASCARADO = "08.857.492/0001-48"
CNPJ_DIGITOS = "08857492000148"


# ═══════════════════════════════════════════════════════════════
# O helper compartilhado
# ═══════════════════════════════════════════════════════════════


def test_normaliza_cnpj_tira_a_pontuacao():
    assert normaliza_cnpj(CNPJ_MASCARADO) == CNPJ_DIGITOS


def test_normaliza_cnpj_aceita_o_que_ja_esta_normalizado():
    """Idempotência: rodar o backfill duas vezes não pode estragar a linha."""
    assert normaliza_cnpj(CNPJ_DIGITOS) == CNPJ_DIGITOS


@pytest.mark.parametrize("valor", ["123", "0885749200014", "088574920001489", "abc", ""])
def test_normaliza_cnpj_recusa_contagem_errada_de_digitos(valor):
    with pytest.raises(ValueError, match="14 dígitos"):
        normaliza_cnpj(valor)


def test_normaliza_cnpj_opcional_aceita_none():
    assert normaliza_cnpj_opcional(None) is None


@pytest.mark.parametrize("vazio", ["", "   "])
def test_normaliza_cnpj_opcional_trata_string_vazia_como_ausencia(vazio):
    """
    Limpar o campo no front manda `""`, não `null` — os dois modais de empresa
    do `GroupsPage` têm `cnpj: ""` no `defaultValues`. Se `""` virasse erro,
    criar empresa sem CNPJ (que hoje funciona) passaria a dar 422.
    """
    assert normaliza_cnpj_opcional(vazio) is None


def test_normaliza_cnpj_opcional_recusa_lixo_que_nao_e_vazio():
    """`"abc"` não é "campo limpo", é erro de digitação — não pode virar None."""
    with pytest.raises(ValueError, match="14 dígitos"):
        normaliza_cnpj_opcional("abc")


def test_normaliza_cnpj_opcional_normaliza_quando_ha_valor():
    assert normaliza_cnpj_opcional(CNPJ_MASCARADO) == CNPJ_DIGITOS


# ═══════════════════════════════════════════════════════════════
# UserUpdate — o furo por onde entrava CNPJ com pontuação
# ═══════════════════════════════════════════════════════════════


def test_user_update_sem_cnpj_nao_inventa_o_campo():
    """
    O endpoint grava com `model_dump(exclude_unset=True)`. Se o validador
    materializasse `cnpj=None`, todo PATCH de nome ou telefone apagaria o CNPJ
    do usuário.
    """
    body = UserUpdate(name="Fulano")
    assert "cnpj" not in body.model_dump(exclude_unset=True)


def test_user_update_aceita_cnpj_nulo_explicito():
    assert UserUpdate(cnpj=None).cnpj is None


def test_user_update_normaliza_a_pontuacao():
    assert UserUpdate(cnpj=CNPJ_MASCARADO).cnpj == CNPJ_DIGITOS


def test_user_update_recusa_cnpj_incompleto():
    with pytest.raises(ValidationError, match="14 dígitos"):
        UserUpdate(cnpj="123")


# ═══════════════════════════════════════════════════════════════
# CompanyCreate / CompanyUpdate — o lado que não tinha validador
# ═══════════════════════════════════════════════════════════════


def test_company_create_sem_cnpj_continua_valido():
    """Criar empresa sem CNPJ funciona hoje e precisa continuar funcionando."""
    assert CompanyCreate(name="Acme").cnpj is None


def test_company_create_normaliza_a_pontuacao():
    assert CompanyCreate(name="Acme", cnpj=CNPJ_MASCARADO).cnpj == CNPJ_DIGITOS


def test_company_create_recusa_cnpj_incompleto():
    with pytest.raises(ValidationError, match="14 dígitos"):
        CompanyCreate(name="Acme", cnpj="123")


def test_company_update_sem_cnpj_nao_inventa_o_campo():
    """
    `update_company` percorre os campos com `getattr(body, field)`, mas o laço
    é guardado por `exclude_unset`. Vale a mesma regra do `UserUpdate`.
    """
    body = CompanyUpdate(name="Acme")
    assert "cnpj" not in body.model_dump(exclude_unset=True)


def test_company_update_normaliza_a_pontuacao():
    assert CompanyUpdate(cnpj=CNPJ_MASCARADO).cnpj == CNPJ_DIGITOS


def test_company_update_limpa_o_campo_com_string_vazia():
    assert CompanyUpdate(cnpj="").cnpj is None


def test_company_update_recusa_cnpj_incompleto():
    with pytest.raises(ValidationError, match="14 dígitos"):
        CompanyUpdate(cnpj="1234")


# ═══════════════════════════════════════════════════════════════
# OnboardingUpdate — regressão: continua obrigatório
# ═══════════════════════════════════════════════════════════════


def _onboarding(**over):
    body = {
        "company_name": "Health & Safety LTDA",
        "cnpj": CNPJ_MASCARADO,
        "company_cep": "50070-000",
    }
    body.update(over)
    return body


def test_onboarding_continua_normalizando():
    assert OnboardingUpdate(**_onboarding()).cnpj == CNPJ_DIGITOS


def test_onboarding_continua_recusando_cnpj_vazio():
    """
    Aqui o campo é **obrigatório**. A regra de "vazio vira None" dos opcionais
    não pode vazar para cá e deixar passar onboarding sem CNPJ.
    """
    with pytest.raises(ValidationError):
        OnboardingUpdate(**_onboarding(cnpj=""))


def test_onboarding_continua_recusando_cnpj_incompleto():
    with pytest.raises(ValidationError, match="14 dígitos"):
        OnboardingUpdate(**_onboarding(cnpj="123"))


# ═══════════════════════════════════════════════════════════════
# Script de backfill
# ═══════════════════════════════════════════════════════════════
#
# O script corrige o passado; o validador cuida do futuro. Backfill nunca vai
# em migration — regra do projeto — então ele é avulso, roda à mão e não pode
# supor que roda no boot.
#
# O que estes testes prendem é a parte que decide, separada da que grava: ela é
# pura, e é onde mora o risco de apagar dado bom.

from scripts.normaliza_cnpj import planeja_normalizacao  # noqa: E402


def test_backfill_ignora_linha_ja_normalizada():
    """Idempotência: rodar duas vezes não pode gerar UPDATE na segunda."""
    mudancas, problemas = planeja_normalizacao([("id-1", CNPJ_DIGITOS)])
    assert mudancas == []
    assert problemas == []


def test_backfill_normaliza_linha_mascarada():
    mudancas, problemas = planeja_normalizacao([("id-1", CNPJ_MASCARADO)])
    assert mudancas == [("id-1", CNPJ_MASCARADO, CNPJ_DIGITOS)]
    assert problemas == []


def test_backfill_ignora_nulo():
    assert planeja_normalizacao([("id-1", None)]) == ([], [])


def test_backfill_transforma_string_vazia_em_nulo():
    """`""` e NULL significam a mesma coisa; as consultas usam `IS NOT NULL`."""
    mudancas, problemas = planeja_normalizacao([("id-1", "   ")])
    assert mudancas == [("id-1", "   ", None)]
    assert problemas == []


def test_backfill_nao_toca_no_que_nao_da_para_normalizar():
    """
    Linha torta vira RELATO, não UPDATE. Um script de limpeza que apaga o que
    não entende é pior que o problema que veio consertar — quem decide o que
    fazer com ela é o Rickelme, olhando o relatório.
    """
    mudancas, problemas = planeja_normalizacao([("id-1", "123"), ("id-2", CNPJ_MASCARADO)])
    assert mudancas == [("id-2", CNPJ_MASCARADO, CNPJ_DIGITOS)]
    assert problemas == [("id-1", "123")]
