"""
Telefone de cliente: regra de domínio, normalização e a prova de que ela é
PROSPECTIVA.

Por que a regra existe: a telefonia (API4COM) disca para o telefone do cliente
do chamado, e `users.phone` é a fonte canônica — decisão registrada em
`docs/decisoes-e-regras.md`. Um cliente ativo sem telefone é um chamado que
nunca vira ligação.

Por que ela é prospectiva, e não uma trava geral: medido em produção em
18/09/2026, existem 14 contas `role=client` + `status=active` sem telefone.
São contas de teste, informadas como fictícias pelo responsável — mas existem
fisicamente, e uma regra que exigisse telefone em TODO `PATCH` deixaria essas
contas incapazes de editar o próprio nome. A regra proíbe duas coisas, e só
elas:

  P1  REMOÇÃO   — quem TEM telefone não pode ficar sem, sendo cliente ativo.
  P2  TRANSIÇÃO — virar cliente, ou voltar a ficar ativo, exige telefone.

O que ela NÃO proíbe: um cliente ativo legado, que já estava sem telefone,
seguir editando campos não relacionados. É o que os testes de legado abaixo
guardam — e é a diferença entre uma regra prospectiva e uma migração
disfarçada de validação.

A normalização viaja no TIPO (`TelefoneObrigatorio` / `TelefoneOpcional`),
como o CNPJ em `app/utils/documents.py` e o e-mail em
`app/utils/email_normalizado.py`. O guard de fonte no fim deste arquivo pega
o próximo campo de telefone declarado como `str` cru.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter, ValidationError

from app.main import app
from app.models.models import UserRole, UserStatus
from app.schemas.auth import RegisterRequest
from app.schemas.base import AppBaseModel
from app.schemas.user import UserCreate, UserUpdate
from app.utils.telefone import (
    TelefoneObrigatorio,
    TelefoneOpcional,
    normaliza_telefone,
    telefone_ausente,
)

# ══════════════════════════════════════════════════════════════
# 1. Normalização — E.164 como representação interna
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        # As quatro grafias que o enunciado manda aceitar.
        ("81999999999", "+5581999999999"),
        ("5581999999999", "+5581999999999"),
        ("+5581999999999", "+5581999999999"),
        ("(81) 99999-9999", "+5581999999999"),
        # Fixo de 8 dígitos, com e sem máscara.
        ("8133334444", "+558133334444"),
        ("(81) 3333-4444", "+558133334444"),
        ("558133334444", "+558133334444"),
        # Ruído que o usuário digita sem perceber.
        ("+55 (81) 99999-9999", "+5581999999999"),
        ("81 99999 9999", "+5581999999999"),
        ("81.99999.9999", "+5581999999999"),
    ],
)
def test_normaliza_para_e164(entrada, esperado):
    assert normaliza_telefone(entrada) == esperado


def test_normalizacao_e_idempotente():
    """Rodar duas vezes não pode mudar o valor — o backfill futuro depende
    disso, e o tipo roda de novo em todo PATCH que reenvie o campo."""
    uma_vez = normaliza_telefone("(81) 99999-9999")
    assert normaliza_telefone(uma_vez) == uma_vez == "+5581999999999"


def test_numero_internacional_nao_brasileiro_passa_com_ddi_explicito():
    """O produto é brasileiro, mas nada no domínio proíbe um cliente de fora.
    A exigência é o `+` — sem ele não há como saber onde o país termina."""
    assert normaliza_telefone("+351912345678") == "+351912345678"
    assert normaliza_telefone("+1 415 555 2671") == "+14155552671"


@pytest.mark.parametrize(
    "entrada",
    [
        "abc",  # letra pura
        "9999",  # curto demais para ser qualquer coisa
        "999999999",  # 9 dígitos: nem fixo com DDD, nem celular
        "123456789012",  # 12 dígitos que não começam com 55
        "+0581999999999",  # E.164 não começa com zero
        "+55819999999999999",  # passa dos 15 dígitos do E.164
        "+55",  # só o DDI
        "0081999999999",  # prefixo internacional discado, não E.164
        "01999999999",  # DDD não pode ter zero
        "81899999999",  # 11 dígitos cujo celular não começa com 9
        "8199999999",  # celular ANTIGO de 8 dígitos: não completa chamada
        # Com `+55` explícito e E.164 formalmente válido, mas com número
        # nacional de tamanho impossível — é o caso de quem para de digitar no
        # meio. Só o `+` não basta: o que vem depois do DDI também é validado.
        "+55819999",  # 8 dígitos no total, 6 depois do 55
        "+558199999999999",  # 15 dígitos no total, 13 depois do 55
    ],
)
def test_recusa_o_que_nao_e_telefone(entrada):
    with pytest.raises(ValueError):
        normaliza_telefone(entrada)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("(81) 3333-1234", "+558133331234"),
        ("8133331234", "+558133331234"),
        ("+558133331234", "+558133331234"),
        ("5581 3333-1234", "+558133331234"),
        # Os quatro prefixos de fixo no Brasil: 2, 3, 4 e 5.
        ("(81) 2222-1234", "+558122221234"),
        ("(81) 4444-1234", "+558144441234"),
        ("(81) 5555-1234", "+558155551234"),
    ],
)
def test_telefone_fixo_brasileiro_continua_aceito(entrada, esperado):
    """O campo se chama `phone`, não `mobile`. A recusa do celular antigo de
    oito dígitos **não pode** ter levado o fixo junto — ele também tem dez
    dígitos, e a diferença está só no primeiro dígito do assinante."""
    assert normaliza_telefone(entrada) == esperado


@pytest.mark.parametrize("entrada", ["(81) 9999-9999", "8199999999", "(81) 8888-9999"])
def test_celular_antigo_de_oito_digitos_segue_recusado(entrada):
    """A outra metade do par acima: dez dígitos cujo assinante começa em 8 ou
    9 é celular de antes de 2016, e esse número não completa chamada. Fixo
    brasileiro começa em 2, 3, 4 ou 5 — é esse dígito que separa os dois."""
    with pytest.raises(ValueError):
        normaliza_telefone(entrada)


def test_numero_de_digito_repetido_e_aceito():
    """`(81) 99999-9999` é o exemplo do próprio enunciado. Uma guarda contra
    'número falso por dígito repetido' recusaria justamente ele."""
    assert normaliza_telefone("(81) 99999-9999") == "+5581999999999"


def test_o_tipo_opcional_trata_campo_limpo_como_ausencia():
    """Limpar o campo no front manda `""`, não `null` — mesma regra do
    `CnpjOpcional`. Já lixo com conteúdo é erro de digitação, não ausência."""
    adaptador = TypeAdapter(TelefoneOpcional)
    assert adaptador.validate_python(None) is None
    assert adaptador.validate_python("") is None
    assert adaptador.validate_python("   ") is None
    with pytest.raises(ValidationError):
        adaptador.validate_python("abc")


def test_o_tipo_obrigatorio_recusa_vazio():
    adaptador = TypeAdapter(TelefoneObrigatorio)
    assert adaptador.validate_python("(81) 99999-9999") == "+5581999999999"
    with pytest.raises(ValidationError):
        adaptador.validate_python("")


def test_telefone_ausente_reconhece_branco_e_nulo():
    assert telefone_ausente(None)
    assert telefone_ausente("")
    assert telefone_ausente("   ")
    assert telefone_ausente("\t")
    assert not telefone_ausente("+5581999999999")


# ══════════════════════════════════════════════════════════════
# 2. Schemas de entrada
# ══════════════════════════════════════════════════════════════


def test_register_exige_telefone():
    """O `/auth/register` cria SEMPRE cliente ativo (auditado: role e status
    são literais no router), então a exigência cabe no próprio schema."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="Fulano",
            email="fulano@x.com",
            password="SenhaForte1",
            lgpd_consent=True,
        )


def test_register_normaliza_o_telefone():
    pedido = RegisterRequest(
        name="Fulano",
        email="fulano@x.com",
        password="SenhaForte1",
        phone="(81) 99999-9999",
        lgpd_consent=True,
    )
    assert pedido.phone == "+5581999999999"


def test_user_create_normaliza_e_aceita_ausencia_no_schema():
    """A obrigatoriedade do `UserCreate` NÃO mora no schema: quem sabe o
    estado resultante é o router, que fixa `status=active`. O schema só
    normaliza."""
    assert (
        UserCreate(
            name="Fulano", email="f@x.com", password="SenhaForte1", phone="81999999999"
        ).phone
        == "+5581999999999"
    )
    assert UserCreate(name="Fulano", email="f@x.com", password="SenhaForte1").phone is None


def test_user_update_so_normaliza_quando_o_campo_vem():
    """`UserUpdate` é compartilhado por `PATCH /users/me` e `PATCH /users/{id}`
    e não pode decidir domínio: ele não conhece o usuário alvo."""
    enviado = UserUpdate(phone="(81) 99999-9999")
    assert enviado.phone == "+5581999999999"
    assert "phone" in enviado.model_dump(exclude_unset=True)

    ausente = UserUpdate(name="Outro Nome")
    assert "phone" not in ausente.model_dump(exclude_unset=True)


def test_user_update_recusa_telefone_invalido():
    with pytest.raises(ValidationError):
        UserUpdate(phone="abc")


# ══════════════════════════════════════════════════════════════
# 3. Guards no router — a regra prospectiva
# ══════════════════════════════════════════════════════════════


def _user(role=UserRole.client, status=UserStatus.active, phone=None, uid=None):
    u = MagicMock()
    u.id = uid or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.name = f"Test {role.value}"
    u.role = role
    u.status = status
    u.phone = phone
    u.department = None
    u.avatar_url = None
    u.last_login = None
    u.lgpd_consent = True
    u.lgpd_consent_at = None
    u.company_name = None
    u.cnpj = None
    u.company_cep = None
    u.company_address = None
    u.company_city = None
    u.company_state = None
    u.onboarding_completed = True
    # Campo novo do `UserResponse` (Fase 2C.1a). Sem valor explícito o
    # MagicMock devolve um objeto e o `model_validate` recusa — mesma
    # armadilha que os campos de empresa acima já registram.
    u.api4com_extension = None
    u.ai_enabled = True
    u.created_at = datetime.now(UTC)
    u.updated_at = datetime.now(UTC)
    return u


def _db(alvo):
    async def _execute(*args, **kwargs):
        resultado = MagicMock()
        resultado.scalar_one_or_none.return_value = alvo
        resultado.scalars.return_value.all.return_value = [alvo] if alvo else []
        resultado.scalar_one.return_value = 1 if alvo else 0
        return resultado

    sessao = AsyncMock()
    sessao.execute = _execute
    sessao.add = MagicMock()
    sessao.commit = AsyncMock()
    sessao.refresh = AsyncMock()

    async def _gen():
        yield sessao

    return _gen


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


def _autentica(ator, alvo):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _db(alvo)
    app.dependency_overrides[get_current_user] = lambda: ator


async def _patch(rota, corpo, ator, alvo):
    _autentica(ator, alvo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        return await cliente.patch(rota, json=corpo)


# ── Legado: a regra NÃO pode travar quem já está sem telefone ──


@pytest.mark.asyncio
async def test_legado_sem_telefone_edita_o_nome():
    """Caso 1 do enunciado. São 14 contas assim em produção: se isto recusar,
    a Fase 1A vira migração disfarçada de validação."""
    legado = _user(phone=None)
    resposta = await _patch(f"/api/v1/users/{legado.id}", {"name": "Nome Novo"}, legado, legado)
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_legado_sem_telefone_edita_campo_nao_relacionado():
    """Caso 2 do enunciado."""
    legado = _user(phone=None)
    resposta = await _patch(f"/api/v1/users/{legado.id}", {"department": "Suporte"}, legado, legado)
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_legado_sem_telefone_pelo_proprio_perfil():
    """A tela de perfil manda o formulário INTEIRO, então um legado envia
    `phone: null` junto do nome. Esvaziar o que já era vazio é no-op, não
    remoção — recusar aqui travaria o perfil de 14 contas."""
    legado = _user(phone=None)
    resposta = await _patch(
        "/api/v1/users/me", {"name": "Nome Novo", "phone": None}, legado, legado
    )
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_legado_inativo_edita_campo_nao_relacionado():
    """Caso 7 do enunciado."""
    legado = _user(status=UserStatus.inactive, phone=None)
    resposta = await _patch(f"/api/v1/users/{legado.id}", {"name": "Outro"}, legado, legado)
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_legado_sem_telefone_pode_preencher_um_valido():
    """O caminho de saída do legado: enviar telefone é sempre permitido, desde
    que válido."""
    legado = _user(phone=None)
    resposta = await _patch(
        f"/api/v1/users/{legado.id}", {"phone": "(81) 99999-9999"}, legado, legado
    )
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_legado_sem_telefone_nao_pode_enviar_telefone_invalido():
    """Caso do enunciado: se enviar phone, o valor precisa ser válido."""
    legado = _user(phone=None)
    resposta = await _patch(f"/api/v1/users/{legado.id}", {"phone": "abc"}, legado, legado)
    assert resposta.status_code == 422


# ── P1: remoção ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cliente_ativo_nao_remove_telefone_com_nulo():
    """Caso 3 do enunciado."""
    cliente = _user(phone="+5581999999999")
    resposta = await _patch(f"/api/v1/users/{cliente.id}", {"phone": None}, cliente, cliente)
    assert resposta.status_code == 422
    assert "remover" in resposta.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cliente_ativo_nao_remove_telefone_com_string_vazia():
    """Caso 4 do enunciado. O `""` vira `None` no tipo (campo limpo), e é o
    guard que recusa — não a validação de formato."""
    cliente = _user(phone="+5581999999999")
    resposta = await _patch(f"/api/v1/users/{cliente.id}", {"phone": ""}, cliente, cliente)
    assert resposta.status_code == 422
    assert "remover" in resposta.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cliente_ativo_nao_remove_telefone_pelo_proprio_perfil():
    """A mesma proibição pelo `PATCH /users/me` — senão o cliente contorna
    a regra editando a si mesmo."""
    cliente = _user(phone="+5581999999999")
    resposta = await _patch("/api/v1/users/me", {"phone": None}, cliente, cliente)
    assert resposta.status_code == 422


@pytest.mark.asyncio
async def test_admin_nao_remove_telefone_de_cliente_ativo():
    """Nem o admin: a regra é do domínio, não da tela."""
    admin = _user(role=UserRole.admin, phone=None)
    cliente = _user(phone="+5581999999999")
    resposta = await _patch(f"/api/v1/users/{cliente.id}", {"phone": None}, admin, cliente)
    assert resposta.status_code == 422


@pytest.mark.asyncio
async def test_tecnico_ativo_pode_remover_o_proprio_telefone():
    """A regra vale para CLIENTE. Técnico e admin seguem como estavam."""
    tecnico = _user(role=UserRole.technician, phone="+5581999999999")
    resposta = await _patch("/api/v1/users/me", {"phone": None}, tecnico, tecnico)
    assert resposta.status_code == 200, resposta.text


# ── P2: transição ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_virar_cliente_sem_telefone_e_recusado():
    """Caso 6 do enunciado."""
    admin = _user(role=UserRole.admin, phone=None)
    tecnico = _user(role=UserRole.technician, phone=None)
    resposta = await _patch(f"/api/v1/users/{tecnico.id}", {"role": "client"}, admin, tecnico)
    assert resposta.status_code == 422


@pytest.mark.asyncio
async def test_legado_reenviar_o_proprio_papel_nao_e_transicao():
    """`role: client` num usuário que JÁ é cliente não muda nada — e a
    proteção precisa reagir à transição real (`technician → client`), não à
    presença do campo no corpo. A tela de edição manda o papel sempre, então
    tratar isso como transição travaria todo legado no modal do admin."""
    admin = _user(role=UserRole.admin, phone=None)
    legado = _user(phone=None)
    resposta = await _patch(
        f"/api/v1/users/{legado.id}", {"role": "client", "name": "Nome Novo"}, admin, legado
    )
    assert resposta.status_code == 200, resposta.text
    assert legado.name == "Nome Novo"


@pytest.mark.asyncio
async def test_legado_reenviar_a_propria_situacao_nao_e_transicao():
    """`status: active` num usuário que JÁ está ativo também não é transição:
    a proteção guarda a VOLTA para ativo (`inactive → active`)."""
    admin = _user(role=UserRole.admin, phone=None)
    legado = _user(phone=None)
    _autentica(admin, legado)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.patch(
            f"/api/v1/users/{legado.id}/status", json={"status": "active"}
        )
    assert resposta.status_code == 200, resposta.text
    assert legado.status == UserStatus.active


@pytest.mark.asyncio
async def test_virar_cliente_com_telefone_no_mesmo_pedido_e_aceito():
    """A transição é possível — basta mandar o telefone junto."""
    admin = _user(role=UserRole.admin, phone=None)
    tecnico = _user(role=UserRole.technician, phone=None)
    resposta = await _patch(
        f"/api/v1/users/{tecnico.id}",
        {"role": "client", "phone": "(81) 99999-9999"},
        admin,
        tecnico,
    )
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_virar_cliente_quem_ja_tem_telefone_e_aceito():
    admin = _user(role=UserRole.admin, phone=None)
    tecnico = _user(role=UserRole.technician, phone="+5581999999999")
    resposta = await _patch(f"/api/v1/users/{tecnico.id}", {"role": "client"}, admin, tecnico)
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_reativar_cliente_sem_telefone_e_recusado():
    """Caso 5 do enunciado: a volta para `active` é o momento em que a conta
    passa a valer para a telefonia."""
    admin = _user(role=UserRole.admin, phone=None)
    inativo = _user(status=UserStatus.inactive, phone=None)
    _autentica(admin, inativo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.patch(
            f"/api/v1/users/{inativo.id}/status", json={"status": "active"}
        )
    assert resposta.status_code == 422


@pytest.mark.asyncio
async def test_reativar_cliente_com_telefone_e_aceito():
    admin = _user(role=UserRole.admin, phone=None)
    inativo = _user(status=UserStatus.inactive, phone="+5581999999999")
    _autentica(admin, inativo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.patch(
            f"/api/v1/users/{inativo.id}/status", json={"status": "active"}
        )
    assert resposta.status_code == 200, resposta.text


@pytest.mark.asyncio
async def test_desativar_cliente_sem_telefone_e_aceito():
    """Sair de ativo nunca é bloqueado — a regra guarda o estado ATIVO."""
    admin = _user(role=UserRole.admin, phone=None)
    legado = _user(phone=None)
    _autentica(admin, legado)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.patch(
            f"/api/v1/users/{legado.id}/status", json={"status": "inactive"}
        )
    assert resposta.status_code == 200, resposta.text


# ── Criação ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_nao_cria_cliente_sem_telefone():
    admin = _user(role=UserRole.admin, phone=None)
    _autentica(admin, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.post(
            "/api/v1/users",
            json={
                "name": "Cliente Novo",
                "email": "novo@x.com",
                "password": "SenhaForte1",
                "role": "client",
            },
        )
    assert resposta.status_code == 422


@pytest.mark.asyncio
async def test_admin_cria_tecnico_sem_telefone():
    """Técnico e admin seguem a regra anterior do sistema: telefone opcional."""
    admin = _user(role=UserRole.admin, phone=None)
    _autentica(admin, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.post(
            "/api/v1/users",
            json={
                "name": "Tecnico Novo",
                "email": "tec@x.com",
                "password": "SenhaForte1",
                "role": "technician",
            },
        )
    assert resposta.status_code == 201, resposta.text


# ── Anonimização ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anonimizacao_continua_zerando_o_telefone():
    """O direito ao esquecimento é mais forte que a regra de telefone: a
    anonimização escreve `phone = None` direto no objeto, sem passar pelos
    guards. Este teste existe para que ninguém 'conserte' isso depois."""
    admin = _user(role=UserRole.admin, phone=None)
    alvo = _user(phone="+5581999999999")
    _autentica(admin, alvo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.post(f"/api/v1/users/{alvo.id}/anonymize")
    assert resposta.status_code == 200, resposta.text
    assert alvo.phone is None
    assert alvo.status == UserStatus.anonymized


# ══════════════════════════════════════════════════════════════
# 4. Guard de fonte
# ══════════════════════════════════════════════════════════════


def _schemas_de_entrada_com_telefone():
    """Todo modelo de ENTRADA de auth/user que tenha campo `phone`.

    Descoberto por varredura, e não por lista fixa: uma lista fixa não pegaria
    o schema novo, que é exatamente o caso que o guard existe para pegar.
    `*Response` fica de fora porque é saída — ver o teste logo abaixo, que
    guarda o outro lado da mesma regra.
    """
    import inspect

    import app.schemas.auth as schemas_auth
    import app.schemas.user as schemas_user

    for modulo in (schemas_auth, schemas_user):
        for nome, classe in inspect.getmembers(modulo, inspect.isclass):
            if not issubclass(classe, AppBaseModel) or classe is AppBaseModel:
                continue
            if classe.__module__ != modulo.__name__ or nome.endswith("Response"):
                continue
            if "phone" in classe.model_fields:
                yield f"{modulo.__name__}.{nome}", classe.model_fields["phone"]


def test_nenhum_schema_de_entrada_declara_telefone_cru():
    """Guard de fonte, no padrão de `test_email_normalizado.py`: o próximo
    campo de telefone de entrada declarado como `str` puro nasceria sem
    normalização, em silêncio.

    `groups.py` fica de fora de propósito — `companies.phone` não é fonte da
    telefonia (decisão registrada), e o cleanup dele é outro PR.
    """
    from pydantic import AfterValidator

    from app.utils.telefone import normaliza_telefone, normaliza_telefone_opcional

    aprovados = {normaliza_telefone, normaliza_telefone_opcional}
    encontrados = list(_schemas_de_entrada_com_telefone())
    assert encontrados, "a varredura não achou schema nenhum — o guard ficou cego"

    for nome, campo in encontrados:
        validadores = {item.func for item in campo.metadata if isinstance(item, AfterValidator)}
        assert validadores & aprovados, (
            f"{nome} declara telefone cru — usar TelefoneObrigatorio " f"ou TelefoneOpcional"
        )


def test_o_schema_de_resposta_nao_valida_telefone():
    """O outro lado da regra, e ele importa: validador em schema de RESPOSTA
    faria a leitura de uma linha legada mal-formada devolver 500. A regra é
    de entrada — as 14 contas sem telefone precisam continuar legíveis."""
    from app.schemas.user import UserResponse

    assert UserResponse.model_fields["phone"].metadata == []
    assert (
        UserResponse(
            **{
                "id": uuid.uuid4(),
                "name": "Legado",
                "email": "l@x.com",
                "role": UserRole.client,
                "status": UserStatus.active,
                "phone": "(81) 9999-9999 ramal 4",  # fora do formato, de propósito
                "department": None,
                "avatar_url": None,
                "last_login": None,
                "lgpd_consent": True,
                "lgpd_consent_at": None,
                "company_name": None,
                "cnpj": None,
                "company_cep": None,
                "company_address": None,
                "company_city": None,
                "company_state": None,
                "onboarding_completed": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ).phone
        == "(81) 9999-9999 ramal 4"
    )
