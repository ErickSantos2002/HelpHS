"""
Hierarquia de contas e o último administrador ativo — contra PostgreSQL real.

O que se prova aqui
-------------------
1. **Hierarquia.** Só administrador mexe em conta de equipe (técnico ou admin).
   Técnico gere cliente e a própria conta; nada além. Vale nas quatro rotas que
   alteram outra pessoa: editar, mudar situação, excluir e anonimizar.
2. **Recusa não escreve.** Toda operação negada deixa a linha do alvo idêntica
   e não grava `audit_logs` — e deixa um aviso no log da aplicação, sem dado
   pessoal.
3. **Sempre sobra um admin ativo.** Desativar, excluir, anonimizar e rebaixar
   (inclusive a si mesmo) recusam com 409 a operação que zeraria os admins.
4. **Concorrência.** Dois admins agindo um sobre o outro AO MESMO TEMPO não
   zeram o sistema, em nenhuma combinação das cinco operações.

Por que banco próprio
---------------------
A guarda do último admin conta TODOS os admins ativos da tabela. Num banco
compartilhado (o `TEST_POSTGRES_URL` do CI serve a suíte inteira), qualquer
admin esquecido por outro módulo faria a guarda passar e o teste mentir. Por
isso este módulo cria o próprio banco — o mesmo arranjo de
`test_lgpd_consents_postgres.py` — e esvazia `users` antes de cada teste.

Como a corrida é forçada
------------------------
`_corrida` roda duas operações em sessões (e conexões) separadas e segura a
PRIMEIRA dentro do `commit()` até a segunda chegar ao commit dela — ou até
1 s passar. Sem trava no banco, a segunda passa pela checagem enquanto a
primeira ainda não comitou, as duas comitam e o sistema fica sem admin: é
exatamente o defeito, e o teste fica vermelho. Com a trava, a segunda espera
a primeira soltar e relê o estado comitado.
"""

import asyncio
import shutil
import tempfile
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi import HTTPException
from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.models import AuditLog, Base, User, UserRole, UserStatus
from app.schemas.ticket import InterruptorDaIA
from app.schemas.user import UserStatusUpdate, UserUpdate

_BANCO = "hierarquia_usuarios_testes"
_AGORA = datetime.now(UTC)


# ── Infraestrutura ────────────────────────────────────────────


def _url_do_servidor() -> tuple[str | None, object]:
    import os

    do_ambiente = os.environ.get("TEST_POSTGRES_URL")
    if do_ambiente:
        return do_ambiente.replace("postgresql://", "postgresql+asyncpg://"), None
    try:
        import pgserver
    except ImportError:
        return None, None
    pasta = tempfile.mkdtemp(prefix="helphs-testes-pg-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    url = servidor.get_uri(database="postgres")
    return url.replace("postgresql://", "postgresql+asyncpg://"), (servidor, pasta)


@pytest.fixture(scope="module")
def url_do_banco():
    """Banco PRÓPRIO, criado do zero para este módulo (ver o cabeçalho)."""
    servidor_url, recurso = _url_do_servidor()
    if servidor_url is None:
        pytest.skip("sem PostgreSQL à mão")

    url = servidor_url.rsplit("/", 1)[0] + f"/{_BANCO}"

    async def _monta() -> None:
        admin = create_async_engine(servidor_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
            await conn.execute(text(f'CREATE DATABASE "{_BANCO}"'))
        await admin.dispose()
        motor = create_async_engine(url, poolclass=NullPool)
        async with motor.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    async def _desmonta() -> None:
        admin = create_async_engine(servidor_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
        await admin.dispose()

    asyncio.run(_monta())
    yield url
    asyncio.run(_desmonta())

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def fabrica(url_do_banco):
    """Fábrica de sessões presa ao ENGINE, com a tabela de usuários vazia."""
    motor = create_async_engine(url_do_banco, poolclass=NullPool)
    async with motor.begin() as conn:
        await conn.execute(text("TRUNCATE users, audit_logs, lgpd_consents CASCADE"))
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


@pytest_asyncio.fixture
async def db(fabrica):
    async with fabrica() as sessao:
        yield sessao


async def _pessoa(
    fabrica, papel: UserRole, status: UserStatus = UserStatus.active, *, telefone="+5511999990000"
) -> User:
    """Grava e devolve um usuário destacado — serve de ator e de alvo."""
    pessoa = User(
        id=uuid.uuid4(),
        name=f"Pessoa {papel.value}",
        email=f"{uuid.uuid4().hex[:12]}@test.invalid",
        password="x",
        role=papel,
        status=status,
        phone=telefone,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    async with fabrica() as s:
        s.add(pessoa)
        await s.commit()
    return pessoa


async def _retrato(fabrica, user_id) -> dict | None:
    """A linha inteira, coluna por coluna — para provar que nada mudou."""
    async with fabrica() as s:
        linha = (
            (await s.execute(select(User.__table__).where(User.__table__.c.id == user_id)))
            .mappings()
            .one_or_none()
        )
    return dict(linha) if linha is not None else None


async def _auditoria_sobre(fabrica, user_id) -> list[AuditLog]:
    async with fabrica() as s:
        return list(
            (await s.execute(select(AuditLog).where(AuditLog.entity_id == user_id))).scalars()
        )


async def _admins_ativos(fabrica) -> int:
    async with fabrica() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.admin, User.status == UserStatus.active)
            )
        ).scalar_one()


class _Avisos:
    """Captura o que o loguru escreveu em WARNING ou acima."""

    def __enter__(self):
        self.linhas: list[str] = []
        self._id = logger.add(lambda m: self.linhas.append(str(m)), level="WARNING")
        return self

    def __exit__(self, *exc):
        logger.remove(self._id)

    @property
    def texto(self) -> str:
        return "\n".join(self.linhas)


# ── As cinco operações que tiram alguém do quadro de admins ───


async def _desativa(s, ator: User, alvo_id):
    from app.routers.users import update_user_status

    return await update_user_status(alvo_id, UserStatusUpdate(status=UserStatus.inactive), s, ator)


async def _exclui(s, ator: User, alvo_id):
    from app.routers.users import delete_user

    return await delete_user(alvo_id, s, ator)


async def _anonimiza(s, ator: User, alvo_id):
    from app.routers.users import anonymize_user

    return await anonymize_user(alvo_id, s, ator, get_settings())


async def _rebaixa(s, ator: User, alvo_id):
    from app.routers.users import update_user

    return await update_user(alvo_id, UserUpdate(role=UserRole.technician), s, ator)


async def _edita_nome(s, ator: User, alvo_id):
    from app.routers.users import update_user

    return await update_user(alvo_id, UserUpdate(name="Nome Trocado"), s, ator)


_SOBRE_OUTRO = {
    "desativa": _desativa,
    "exclui": _exclui,
    "anonimiza": _anonimiza,
    "rebaixa": _rebaixa,
}


# ══════════════════════════════════════════════════════════════
# 1. Hierarquia: técnico não mexe em conta de equipe
# ══════════════════════════════════════════════════════════════


_OPERACOES_DE_TECNICO = {"edita": _edita_nome, **_SOBRE_OUTRO}


@pytest.mark.asyncio
@pytest.mark.parametrize("papel_do_alvo", [UserRole.admin, UserRole.technician])
@pytest.mark.parametrize("operacao", list(_OPERACOES_DE_TECNICO))
async def test_tecnico_nao_altera_conta_de_equipe(fabrica, db, operacao, papel_do_alvo):
    await _pessoa(fabrica, UserRole.admin)  # o sistema tem admin: a recusa é por papel
    tecnico = await _pessoa(fabrica, UserRole.technician)
    alvo = await _pessoa(fabrica, papel_do_alvo)
    antes = await _retrato(fabrica, alvo.id)

    with _Avisos() as avisos, pytest.raises(HTTPException) as erro:
        await _OPERACOES_DE_TECNICO[operacao](db, tecnico, alvo.id)

    assert erro.value.status_code == 403
    assert await _retrato(fabrica, alvo.id) == antes, "a recusa não pode tocar no alvo"
    assert await _auditoria_sobre(fabrica, alvo.id) == [], "recusa não grava auditoria"
    # Aviso no log da aplicação: ids e papéis, nunca nome ou e-mail.
    assert str(tecnico.id) in avisos.texto and str(alvo.id) in avisos.texto
    assert alvo.email not in avisos.texto and alvo.name not in avisos.texto
    assert tecnico.email not in avisos.texto


@pytest.mark.asyncio
async def test_tecnico_nao_promove_cliente_a_admin(fabrica, db):
    """Reforço do que já valia: papel é atribuição de administrador."""
    from app.routers.users import update_user

    tecnico = await _pessoa(fabrica, UserRole.technician)
    cliente = await _pessoa(fabrica, UserRole.client)
    antes = await _retrato(fabrica, cliente.id)

    with pytest.raises(HTTPException) as erro:
        await update_user(cliente.id, UserUpdate(role=UserRole.admin), db, tecnico)

    assert erro.value.status_code == 403
    assert await _retrato(fabrica, cliente.id) == antes


@pytest.mark.asyncio
@pytest.mark.parametrize("operacao", ["edita", "desativa", "anonimiza", "exclui"])
async def test_tecnico_continua_gerindo_cliente(fabrica, db, operacao):
    """Não-regressão: o uso diário da tela por técnico continua funcionando."""
    await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)
    cliente = await _pessoa(fabrica, UserRole.client)

    await _OPERACOES_DE_TECNICO[operacao](db, tecnico, cliente.id)

    depois = await _retrato(fabrica, cliente.id)
    if operacao == "edita":
        assert depois["name"] == "Nome Trocado"
    elif operacao == "desativa":
        assert depois["status"] == UserStatus.inactive
    elif operacao == "anonimiza":
        assert depois["status"] == UserStatus.anonymized
    else:
        assert depois is None


@pytest.mark.asyncio
async def test_tecnico_edita_a_propria_conta_pela_rota_de_terceiros(fabrica, db):
    from app.routers.users import update_user

    tecnico = await _pessoa(fabrica, UserRole.technician)

    await update_user(tecnico.id, UserUpdate(department="Suporte N2"), db, tecnico)

    assert (await _retrato(fabrica, tecnico.id))["department"] == "Suporte N2"


@pytest.mark.asyncio
@pytest.mark.parametrize("papel_do_alvo", [UserRole.admin, UserRole.technician])
@pytest.mark.parametrize("operacao", ["edita", "desativa", "rebaixa", "anonimiza", "exclui"])
async def test_admin_gerencia_conta_de_equipe(fabrica, db, operacao, papel_do_alvo):
    admin = await _pessoa(fabrica, UserRole.admin)
    alvo = await _pessoa(fabrica, papel_do_alvo)
    if operacao == "rebaixa" and papel_do_alvo == UserRole.technician:
        pytest.skip("rebaixar técnico a técnico não muda nada")

    await _OPERACOES_DE_TECNICO.get(operacao, _rebaixa)(db, admin, alvo.id)

    depois = await _retrato(fabrica, alvo.id)
    if operacao == "exclui":
        assert depois is None
    elif operacao == "edita":
        assert depois["name"] == "Nome Trocado"
    elif operacao == "rebaixa":
        assert depois["role"] == UserRole.technician
    elif operacao == "desativa":
        assert depois["status"] == UserStatus.inactive
    else:
        assert depois["status"] == UserStatus.anonymized
    assert await _admins_ativos(fabrica) >= 1


# ══════════════════════════════════════════════════════════════
# 2. Auditoria das operações autorizadas
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mudanca_de_situacao_audita_antes_e_depois(fabrica, db):
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)

    await _desativa(db, admin, tecnico.id)

    (registro,) = await _auditoria_sobre(fabrica, tecnico.id)
    assert registro.user_id == admin.id
    assert registro.old_data == {"status": "active"}
    assert registro.new_data == {"status": "inactive"}


@pytest.mark.asyncio
async def test_rebaixamento_audita_o_papel_antes_e_depois(fabrica, db):
    admin = await _pessoa(fabrica, UserRole.admin)
    outro = await _pessoa(fabrica, UserRole.admin)

    await _rebaixa(db, admin, outro.id)

    (registro,) = await _auditoria_sobre(fabrica, outro.id)
    assert registro.old_data["role"] == "admin"
    assert registro.new_data["role"] == "technician"


@pytest.mark.asyncio
async def test_edicao_audita_quais_campos_mudaram_sem_copiar_dado_pessoal(fabrica, db):
    from app.routers.users import update_user

    tecnico = await _pessoa(fabrica, UserRole.technician)
    cliente = await _pessoa(fabrica, UserRole.client)

    await update_user(
        cliente.id,
        UserUpdate(name="Nome Novo Secreto", phone="+5511988887777", department=None),
        db,
        tecnico,
    )

    (registro,) = await _auditoria_sobre(fabrica, cliente.id)
    assert registro.new_data == {"campos": ["name", "phone"]}
    assert registro.old_data is None
    serializado = repr(registro.old_data) + repr(registro.new_data)
    assert "Secreto" not in serializado and "988887777" not in serializado
    assert cliente.name not in serializado


@pytest.mark.asyncio
async def test_exclusao_audita_papel_e_situacao_do_excluido(fabrica, db):
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician, UserStatus.inactive)

    await _exclui(db, admin, tecnico.id)

    (registro,) = await _auditoria_sobre(fabrica, tecnico.id)
    assert registro.old_data == {"role": "technician", "status": "inactive"}


# ══════════════════════════════════════════════════════════════
# 3. O último administrador ativo
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unico_admin_nao_se_rebaixa(fabrica, db):
    admin = await _pessoa(fabrica, UserRole.admin)
    antes = await _retrato(fabrica, admin.id)

    with _Avisos() as avisos, pytest.raises(HTTPException) as erro:
        await _rebaixa(db, admin, admin.id)

    assert erro.value.status_code == 409
    assert await _retrato(fabrica, admin.id) == antes
    assert await _auditoria_sobre(fabrica, admin.id) == []
    assert str(admin.id) in avisos.texto and admin.email not in avisos.texto


@pytest.mark.asyncio
async def test_admin_se_rebaixa_quando_sobra_outro(fabrica, db):
    admin = await _pessoa(fabrica, UserRole.admin)
    await _pessoa(fabrica, UserRole.admin)

    await _rebaixa(db, admin, admin.id)

    assert (await _retrato(fabrica, admin.id))["role"] == UserRole.technician
    assert await _admins_ativos(fabrica) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operacao", list(_SOBRE_OUTRO))
async def test_ultimo_admin_ativo_nao_sai_nem_por_ator_desatualizado(fabrica, db, operacao):
    """O ator chegou autenticado como admin, mas foi desativado antes de agir.

    É a forma real da corrida: a autenticação leu `active` e, no instante da
    operação, ele já não é admin ativo. O alvo é o ÚNICO admin ativo que
    restou — a operação zeraria o sistema.
    """
    ator = await _pessoa(fabrica, UserRole.admin, UserStatus.inactive)
    ator.status = UserStatus.active  # o que a autenticação viu
    unico = await _pessoa(fabrica, UserRole.admin)
    antes = await _retrato(fabrica, unico.id)

    with pytest.raises(HTTPException) as erro:
        await _SOBRE_OUTRO[operacao](db, ator, unico.id)

    assert erro.value.status_code == 409
    assert await _retrato(fabrica, unico.id) == antes
    assert await _admins_ativos(fabrica) == 1


@pytest.mark.asyncio
async def test_ultimo_admin_nao_sai_pelo_patch_de_status_para_anonymized(fabrica, db):
    """O `PATCH /status` também aceita `anonymized` — é o segundo caminho que
    tira um admin do quadro, e ele encerra a autorização da foto (Fase 3B).

    A recusa do último admin tem de vir ANTES desse encerramento: a linha sai
    exatamente como estava, autorização da foto inclusive.
    """
    from app.routers.users import update_user_status

    ator = await _pessoa(fabrica, UserRole.admin, UserStatus.inactive)
    ator.status = UserStatus.active  # o que a autenticação viu
    unico = await _pessoa(fabrica, UserRole.admin)
    async with fabrica() as s:
        await s.execute(
            text("UPDATE users SET avatar_visivel_a_terceiros = true WHERE id = :id"),
            {"id": unico.id},
        )
        await s.commit()
    antes = await _retrato(fabrica, unico.id)

    with pytest.raises(HTTPException) as erro:
        await update_user_status(unico.id, UserStatusUpdate(status=UserStatus.anonymized), db, ator)

    assert erro.value.status_code == 409
    assert await _retrato(fabrica, unico.id) == antes
    async with fabrica() as s:
        autorizada = (
            await s.execute(
                text("SELECT avatar_visivel_a_terceiros FROM users WHERE id = :id"),
                {"id": unico.id},
            )
        ).scalar_one()
    assert autorizada is True
    assert await _admins_ativos(fabrica) == 1
    assert await _auditoria_sobre(fabrica, unico.id) == []


@pytest.mark.asyncio
async def test_admin_inativo_sai_sem_checar_quadro(fabrica, db):
    """Tirar quem já não conta como admin ativo não ameaça o quadro."""
    admin = await _pessoa(fabrica, UserRole.admin)
    inativo = await _pessoa(fabrica, UserRole.admin, UserStatus.inactive)

    await _exclui(db, admin, inativo.id)

    assert await _retrato(fabrica, inativo.id) is None


# ══════════════════════════════════════════════════════════════
# 4. Concorrência: nenhuma combinação zera os admins
# ══════════════════════════════════════════════════════════════


async def _corrida(fabrica, primeira, segunda):
    """Roda as duas em paralelo, segurando a primeira no `commit()`.

    Devolve, para cada uma, "ok" ou o status HTTP da recusa. Qualquer outra
    exceção sobe — 500 não é resultado aceitável.
    """
    a_segunda_chegou = asyncio.Event()

    async def roda(operacao, e_a_primeira: bool):
        async with fabrica() as s:
            commit_original = s.commit

            async def commit_vigiado():
                if e_a_primeira:
                    try:
                        await asyncio.wait_for(a_segunda_chegou.wait(), timeout=1.0)
                    except TimeoutError:
                        pass  # a segunda está presa na trava: é o esperado
                else:
                    a_segunda_chegou.set()
                await commit_original()

            s.commit = commit_vigiado  # type: ignore[method-assign]
            try:
                await operacao(s)
                return "ok"
            except HTTPException as e:
                return e.status_code

    primeira_tarefa = asyncio.create_task(roda(primeira, True))
    await asyncio.sleep(0.3)  # a primeira chega ao commit antes de a segunda começar
    segunda_tarefa = asyncio.create_task(roda(segunda, False))
    return await asyncio.gather(primeira_tarefa, segunda_tarefa)


_TODAS = [*_SOBRE_OUTRO, "rebaixa_a_si"]


def _operacao(nome: str, ator: User, outro: User):
    if nome == "rebaixa_a_si":
        return lambda s: _rebaixa(s, ator, ator.id)
    return lambda s: _SOBRE_OUTRO[nome](s, ator, outro.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("op_de_a", _TODAS)
@pytest.mark.parametrize("op_de_b", _TODAS)
async def test_dois_admins_ao_mesmo_tempo_nunca_zeram_o_sistema(fabrica, op_de_a, op_de_b):
    a = await _pessoa(fabrica, UserRole.admin)
    b = await _pessoa(fabrica, UserRole.admin)

    resultados = await _corrida(fabrica, _operacao(op_de_a, a, b), _operacao(op_de_b, b, a))

    assert all(r == "ok" or 400 <= r < 500 for r in resultados), resultados
    assert "ok" in resultados, f"uma das duas deveria passar: {resultados}"
    assert await _admins_ativos(fabrica) == 1, (
        f"{op_de_a} × {op_de_b} deixou {await _admins_ativos(fabrica)} admin(s) ativo(s): "
        f"{resultados}"
    )


@pytest.mark.asyncio
async def test_tres_admins_desativando_em_roda_sobra_um(fabrica):
    """A desativa B, B desativa C, C desativa A — tudo ao mesmo tempo."""
    from app.routers.users import update_user_status

    a, b, c = [await _pessoa(fabrica, UserRole.admin) for _ in range(3)]

    async def desativa(ator, alvo):
        async with fabrica() as s:
            try:
                await update_user_status(
                    alvo.id, UserStatusUpdate(status=UserStatus.inactive), s, ator
                )
                return "ok"
            except HTTPException as e:
                return e.status_code

    resultados = await asyncio.gather(desativa(a, b), desativa(b, c), desativa(c, a))

    assert all(r == "ok" or 400 <= r < 500 for r in resultados), resultados
    assert await _admins_ativos(fabrica) >= 1, resultados


# ══════════════════════════════════════════════════════════════
# 5. IA só se configura em conta de cliente
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("papel_do_ator", [UserRole.admin, UserRole.technician])
@pytest.mark.parametrize("papel_do_alvo", [UserRole.admin, UserRole.technician])
async def test_ia_recusa_conta_que_nao_e_cliente(fabrica, db, papel_do_ator, papel_do_alvo):
    from app.routers.users import toggle_user_ai

    ator = await _pessoa(fabrica, papel_do_ator)
    alvo = await _pessoa(fabrica, papel_do_alvo)
    antes = await _retrato(fabrica, alvo.id)

    with _Avisos() as avisos, pytest.raises(HTTPException) as erro:
        await toggle_user_ai(alvo.id, InterruptorDaIA(enabled=False), db, ator)

    assert erro.value.status_code == 422
    assert await _retrato(fabrica, alvo.id) == antes
    assert await _auditoria_sobre(fabrica, alvo.id) == []
    assert str(alvo.id) in avisos.texto and alvo.email not in avisos.texto


@pytest.mark.asyncio
async def test_ia_desligada_em_cliente_audita_antes_e_depois(fabrica, db):
    from app.routers.users import toggle_user_ai

    tecnico = await _pessoa(fabrica, UserRole.technician)
    cliente = await _pessoa(fabrica, UserRole.client)

    await toggle_user_ai(cliente.id, InterruptorDaIA(enabled=False), db, tecnico)

    assert (await _retrato(fabrica, cliente.id))["ai_enabled"] is False
    (registro,) = await _auditoria_sobre(fabrica, cliente.id)
    assert registro.old_data == {"ai_enabled": True}
    assert registro.new_data == {"ai_enabled": False}
