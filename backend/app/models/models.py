# ============================================================
# HELP DESK — HEALTH & SAFETY
# SQLAlchemy 2.0 Models — Banco de Dados PostgreSQL
# Baseado no Dicionario de Dados v1.0
# ============================================================

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# ── BASE ─────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ── ENUMS ────────────────────────────────────────────────────


class UserRole(str, enum.Enum):
    admin = "admin"
    technician = "technician"
    client = "client"


class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    anonymized = "anonymized"


class TicketStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    awaiting_client = "awaiting_client"
    awaiting_technical = "awaiting_technical"
    resolved = "resolved"
    closed = "closed"
    cancelled = "cancelled"


class TicketPriority(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TicketCategory(str, enum.Enum):
    hardware = "hardware"
    software = "software"
    network = "network"
    access = "access"
    email = "email"
    security = "security"
    # `general` é o balde de quem não sabe classificar. Havia um segundo,
    # `other`, que saiu em 18/09/2026 com zero uso em chamados, artigos e
    # histórico: dois baldes para a mesma dúvida só dividem quem os lê.
    # Este enum é UM tipo no Postgres (`ticketcategory`) servindo
    # `tickets.category` e `kb_articles.category` — acrescentar valor aqui
    # sem migration derruba a primeira leitura que o encontrar.
    general = "general"


class SLALevel(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class NotificationType(str, enum.Enum):
    ticket_created = "ticket_created"
    ticket_assigned = "ticket_assigned"
    ticket_updated = "ticket_updated"
    ticket_resolved = "ticket_resolved"
    ticket_closed = "ticket_closed"
    sla_warning = "sla_warning"
    sla_breached = "sla_breached"
    chat_message = "chat_message"
    satisfaction_survey = "satisfaction_survey"
    system = "system"


class AuditAction(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"
    login = "login"
    logout = "logout"
    export = "export"
    assign = "assign"
    status_change = "status_change"
    password_change = "password_change"
    anonymize = "anonymize"


class KBArticleStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class LibraryVisibility(str, enum.Enum):
    """Quem pode ver um arquivo da biblioteca.

    `internal` e o default da coluna, e a escolha e a regra inteira: abrir para
    o cliente e acao explicita de quem envia, entao esquecer falha do lado
    seguro. Ha manual tecnico com senha de configuracao em texto aberto -- ver
    o cabecalho da migration c9d0e1f2a3b4.
    """

    internal = "internal"
    client = "client"


class CalendarEventType(str, enum.Enum):
    event = "event"
    meeting = "meeting"
    training = "training"
    deadline = "deadline"
    holiday = "holiday"


class CallCreationStatus(str, enum.Enum):
    """O que sabemos sobre a TENTATIVA de criar a chamada no fornecedor.

    ⚠️ NÃO é o estado telefônico. `ringing`, `answered` e `hangup` chegam pelo
    webhook e são assunto da Fase 2D. Aqui a pergunta é só uma, e é a mesma do
    `services/api4com.py`: **a chamada saiu?**

    ⚠️ Este enum NÃO vira tipo nativo do PostgreSQL. A coluna é `String` com
    `CHECK`, e a diferença é deliberada: acrescentar valor a enum nativo exige
    `ALTER TYPE ... ADD VALUE`, que nesta casa não pode ser citado em DDL
    posterior — o alembic roda a cadeia inteira numa transação só. E remover
    valor custa recriar o tipo e converter toda coluna que o usa, como foi
    preciso fazer em 18/09 com `ticketcategory`. Uma máquina de estados que
    ainda vai crescer na 2D não pode nascer com esse custo.
    """

    # Linha criada antes de falar com o fornecedor. Nada saiu ainda — e é essa
    # certeza que faz `pending` NÃO bloquear uma nova tentativa: uma linha
    # `pending` órfã de um processo que morreu significa que nenhum telefone
    # tocou.
    pending = "pending"
    # A fronteira do efeito externo. Gravado imediatamente ANTES do
    # `create_call`, e é o que tira a ambiguidade que o `pending` tinha sozinho:
    # antes deste estado existir, uma linha órfã podia significar "nunca enviei"
    # OU "enviei e não soube do resultado", e as duas exigiam condutas opostas.
    # `dispatching` órfã é o caso perigoso — bloqueia nova tentativa.
    dispatching = "dispatching"
    # HTTP 200 com `id` legível: a chamada existe do lado de lá.
    confirmed = "confirmed"
    # 4xx: o fornecedor respondeu recusando a requisição.
    rejected = "rejected"
    # Falha de conexão: não houve comunicação HTTP útil.
    unavailable = "unavailable"
    # ⚠️ Pode ter tocado o telefone de alguém e não sabemos. 5xx, 3xx, timeout
    # de leitura, 2xx ilegível. É o estado que existe para ser reconciliado,
    # e é a razão de `provider_call_id` aceitar NULL.
    indeterminate = "indeterminate"


# ── MODELS ───────────────────────────────────────────────────


class Group(Base):
    """Grupos organizacionais de clientes"""

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    companies: Mapped[list["Company"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    group_notes: Mapped[list["GroupNote"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Company(Base):
    """Empresas dentro de um grupo"""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(18))
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    group: Mapped["Group"] = relationship(back_populates="companies")
    clients: Mapped[list["User"]] = relationship(
        back_populates="company", foreign_keys="User.company_id"
    )
    company_notes: Mapped[list["CompanyNote"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class User(Base):
    """Usuarios do sistema (admin, tecnico, cliente)"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.client, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), default=UserStatus.active, nullable=False
    )
    phone: Mapped[str | None] = mapped_column(String(20))
    department: Mapped[str | None] = mapped_column(String(100))
    # Ramal da API4COM deste usuário — o `extension`/`caller` que o `POST
    # /calls` exige. Guardado aqui porque o fornecedor instrui o integrador a
    # manter o vínculo do próprio lado, e porque resolver o ramal por e-mail a
    # cada clique não funcionaria: medido em 24/09/2026, ZERO dos 16 e-mails do
    # staff do HelpHS aparece entre os 18 ramais da conta.
    #
    # String, e não inteiro: o fornecedor declara o ramal como identificador
    # textual, e ramal futuro pode não ser numérico. Mesma escolha do
    # `provider_call_id`.
    #
    # Nulo é o normal, não a exceção: quem não tem ramal não liga, e não há
    # padrão nem fallback. Ver `_guarda_de_atribuicao_de_ramal` no router.
    api4com_extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # LGPD
    lgpd_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    lgpd_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Confirmação de e-mail no auto-cadastro
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Segundo fator (TOTP), só para staff. O segredo fica CIFRADO, não hasheado:
    # conferir o código exige recalculá-lo a partir do segredo, então o servidor
    # precisa recuperá-lo em claro. O que protege é a chave da cifra morar fora
    # do banco — ver services/mfa.py.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(255))
    mfa_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Empresa (onboarding do cliente)
    company_name: Mapped[str | None] = mapped_column(String(255))
    cnpj: Mapped[str | None] = mapped_column(String(18))
    company_cep: Mapped[str | None] = mapped_column(String(9))
    company_address: Mapped[str | None] = mapped_column(String(255))
    company_city: Mapped[str | None] = mapped_column(String(100))
    company_state: Mapped[str | None] = mapped_column(String(2))
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Vínculo ao grupo (clientes)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Este cliente aceita ser atendido por IA. Desligado aqui, a Helo nao fala
    # com ele em chamado nenhum -- ha empresa que nao quer robo, e a alternativa
    # (pedir para o atendente lembrar de calar a IA em cada chamado) nao e
    # alternativa. Ligado por padrao: negar atendimento a quem nunca pediu para
    # ser excluido seria decidir por ele.
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    created_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="creator", foreign_keys="Ticket.creator_id"
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="assignee", foreign_keys="Ticket.assignee_id"
    )
    ticket_histories: Mapped[list["TicketHistory"]] = relationship(back_populates="user")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="sender")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="user")
    kb_articles: Mapped[list["KBArticle"]] = relationship(back_populates="author")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")
    satisfaction_given: Mapped[list["SatisfactionSurvey"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    equipments: Mapped[list["Equipment"]] = relationship(
        back_populates="owner", foreign_keys="Equipment.owner_id"
    )
    company: Mapped["Company | None"] = relationship(
        "Company", back_populates="clients", foreign_keys=[company_id]
    )

    __table_args__ = (
        Index("ix_users_role_status", "role", "status"),
        # Um ramal, um usuário. Índice NOMEADO e não `unique=True` na coluna,
        # para o downgrade da migration remover exatamente este objeto — mesmo
        # padrão do `uq_ticket_calls_provider_call_id` e do
        # `uq_equipments_product_serial`. No PostgreSQL vários NULL convivem
        # sob UNIQUE, que é exatamente o desejado: dezesseis pessoas sem ramal
        # não colidem entre si.
        #
        # A unicidade não é capricho de modelagem: o ramal é identidade SIP.
        # Dois usuários sob o mesmo ramal produzem ligações indistinguíveis na
        # origem, e quando os webhooks entrarem (2D) não haverá como atribuir a
        # chamada a uma pessoa — a trilha de auditoria quebra em silêncio.
        Index("uq_users_api4com_extension", "api4com_extension", unique=True),
        # Segundo fator ligado sem segredo é uma conta trancada: o login exigiria
        # um código que não há como conferir. O banco recusa esse estado em vez
        # de confiar que todo caminho de escrita futuro se lembre da regra.
        CheckConstraint(
            "mfa_enabled = false OR mfa_secret IS NOT NULL",
            name="ck_users_mfa_ligado_tem_segredo",
        ),
        # Cliente ativo sem telefone é um chamado que nunca vira ligação. A
        # regra vive na aplicação desde a Fase 1A; aqui ela vira invariante,
        # para o caminho de escrita que ainda não existe não poder esquecê-la.
        #
        # PRESENÇA, não formato: `\s` trata tabulação e quebra de linha como
        # ausência, e E.164 continua sendo assunto do tipo anotado em
        # `app/utils/telefone.py`. Pôr a regex do formato aqui criaria uma
        # segunda fonte de verdade que deriva da primeira em silêncio.
        #
        # ⚠️ `ddl_if(dialect="postgresql")` não é preciosismo: `regexp_replace`
        # é função do PostgreSQL, e a maior parte da suíte monta o schema por
        # `create_all` em SQLite. Sem a guarda, o `CREATE TABLE users` morre lá
        # com `no such function: regexp_replace` — medido, 47 falhas e 37 erros.
        # A constraint continua DECLARADA no metadata; o que a guarda muda é
        # só onde o DDL sai. Declarar aqui mantém o mapeamento alinhado com a
        # invariante real do banco, faz o `create_all` de PostgreSQL nascer
        # com a mesma regra da migration, e dá aos testes um alvo explícito
        # para comparar model e migration. O `autogenerate` do Alembic NÃO
        # compara CHECK — medido na 1.15.2 —, então essa paridade é
        # responsabilidade do teste, não da ferramenta.
        # O CHECK do MFA, acima, não precisa disso porque é SQL portável.
        CheckConstraint(
            "NOT (role = 'client' AND status = 'active') "
            r"OR regexp_replace(coalesce(phone, ''), '\s', '', 'g') <> ''",
            name="ck_users_cliente_ativo_tem_telefone",
        ).ddl_if(dialect="postgresql"),
    )


class LgpdConsent(Base):
    """Cada aceite da Política de Privacidade (e dos Termos), como evento próprio.

    `users.lgpd_consent` e `users.lgpd_consent_at` continuam sendo a leitura
    rápida do estado ATUAL — é o que as telas leem. Esta tabela é a PROVA: diz
    qual revisão cada pessoa aceitou, quando e por qual caminho, que é o que a
    seção 15 da política promete guardar.

    **Append-only pela regra de negócio.** Aceite novo é linha nova; revogar
    ESCREVE `revogado_em` nos aceites abertos e não apaga nada. Antes desta
    tabela, revogar zerava `lgpd_consent_at` e a prova do período consentido
    — justamente o que precisaria ser defendido — sumia.

    **Sem backfill.** Quem se cadastrou antes dela aceitou um texto que ainda
    não existia: a revisão dessas pessoas é desconhecida, e a ausência de
    linha é a verdade que fica gravada. É ela que dispara o re-aceite.

    Desenho em `docs/superpowers/specs/2026-08-31-registro-da-revisao-aceita-design.md`.
    """

    __tablename__ = "lgpd_consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # `SET NULL`, decidido em 24/09/2026: excluir a conta não apaga o registro
    # de que houve aceite daquela revisão — a política promete guardá-lo por
    # até 5 anos —, mas também não prende a pessoa ao registro.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # As revisões vêm de `LGPD_REVISAO_POLITICA` e `LGPD_REVISAO_TERMOS`, lidas
    # no momento do aceite. Nulas quando o documento não existe (os Termos,
    # hoje) ou quando o ambiente não declarou — desenvolvimento e teste.
    revisao_politica: Mapped[str | None] = mapped_column(String(20), nullable=True)
    revisao_termos: Mapped[str | None] = mapped_column(String(20), nullable=True)
    origem: Mapped[str] = mapped_column(String(30), nullable=False)
    concedido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # De onde o TITULAR aceitou. Nulo quando quem gravou foi outra pessoa (a
    # equipe criando a conta): o IP seria o dela, e o registro afirmaria algo
    # que não aconteceu.
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        # SQL portável: vale no `create_all` do SQLite e no PostgreSQL.
        CheckConstraint(
            "origem IN ('auto_cadastro', 'criado_por_terceiro', 'alteracao_propria')",
            name="ck_lgpd_consents_origem_conhecida",
        ),
    )


class Product(Base):
    """Produtos da empresa Health & Safety"""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    equipments: Mapped[list["Equipment"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="product")
    kb_articles: Mapped[list["KBArticle"]] = relationship(
        secondary="kb_article_products", back_populates="products"
    )


class Equipment(Base):
    """Equipamentos associados a produtos"""

    __tablename__ = "equipments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), index=True)
    model: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    product: Mapped["Product"] = relationship(back_populates="equipments")
    owner: Mapped["User | None"] = relationship(
        "User", back_populates="equipments", foreign_keys=[owner_id]
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        secondary="ticket_equipments", back_populates="equipments"
    )
    # Quem usa o aparelho. Sem `back_populates`: o lado do usuário continua
    # sendo `User.equipments` (os que ele cadastrou), e misturar os dois numa
    # relação só faria a tela do cliente mudar de sentido sem ninguém pedir.
    users: Mapped[list["User"]] = relationship(secondary="equipment_users")

    # Número de série único por PRODUTO. O dono saiu da chave em 26/08: duas
    # pessoas com a mesma série do mesmo produto têm o mesmo aparelho físico, e
    # quem diz quem usa é a `equipment_users`. Enquanto o escopo era o dono, o
    # mesmo aparelho virava duas linhas que não se conheciam.
    #
    # Série nula não conflita — em SQL, NULL nunca é igual a NULL —, e é o que
    # se quer: aparelho sem número cadastrado é caso comum, não duplicata.
    # Ver `_recusa_serie_do_produto` em routers/products.
    __table_args__ = (
        Index("uq_equipments_product_serial", "product_id", "serial_number", unique=True),
    )


# O mesmo aparelho físico é usado por mais de uma pessoa — dois funcionários da
# mesma empresa cadastram a mesma série, e hoje isso vira DUAS linhas em
# `equipments`, cada uma se achando dona. `owner_id` é um campo só e não
# comporta os dois.
#
# Aqui `owner_id` continua significando "quem cadastrou" (e é quem edita); esta
# tabela diz quem USA o aparelho. Toda pessoa anexada, inclusive o cadastrante,
# tem linha aqui — sem exceção, para nenhuma consulta precisar juntar as duas
# fontes com OR.
#
# Ver docs/superpowers/specs/2026-08-26-empresa-e-aparelho-compartilhado-design.md
equipment_users = Table(
    "equipment_users",
    Base.metadata,
    Column(
        "equipment_id",
        UUID(as_uuid=True),
        ForeignKey("equipments.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


kb_article_products = Table(
    "kb_article_products",
    Base.metadata,
    Column(
        "article_id",
        UUID(as_uuid=True),
        ForeignKey("kb_articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "product_id",
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


ticket_tags = Table(
    "ticket_tags",
    Base.metadata,
    Column(
        "ticket_id",
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# Um chamado pode envolver vários aparelhos do cliente — antes era preciso
# abrir um chamado por equipamento ou citar os seriais na descrição, onde a
# busca não alcança.
ticket_equipments = Table(
    "ticket_equipments",
    Base.metadata,
    Column(
        "ticket_id",
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "equipment_id",
        UUID(as_uuid=True),
        ForeignKey("equipments.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Ticket(Base):
    """Tickets de suporte (entidade principal)"""

    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )  # HS-2026-0001
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus), default=TicketStatus.open, nullable=False, index=True
    )
    # NULO até a triagem. O chamado nasce sem prioridade e quem a define é
    # técnico ou administrador, pelo `PATCH /tickets/{id}/priority` — o cliente
    # não escolhe a própria urgência.
    #
    # Sem `default`: um default aqui traria o `medium` de volta pela porta dos
    # fundos, e "média" seria indistinguível de "ninguém olhou ainda". São duas
    # informações diferentes, e o painel conta as duas em baldes separados.
    priority: Mapped[TicketPriority | None] = mapped_column(
        Enum(TicketPriority), nullable=True, index=True
    )
    category: Mapped[TicketCategory] = mapped_column(
        Enum(TicketCategory), default=TicketCategory.general
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id")
    )

    # A IA pode atuar NESTE chamado. É o interruptor que o técnico usa quando
    # entra numa conversa e quer a Helô calada dali em diante — o cliente
    # demorou a responder, ou o assunto virou algo que ela não deve tocar.
    #
    # Vale para a IA inteira, não só para a Helô: desligado aqui, nem a
    # classificação automática nem a sugestão de resposta olham este chamado.
    # "Desliga a IA neste chamado" tem que significar isso, senão a promessa
    # da tela é maior que a do código.
    #
    # É o botão DE GENTE, e só. A Helô não escreve aqui quando decide sair
    # sozinha — para isso existe o `helo_saiu` logo abaixo. A exceção está lá
    # explicada: quando o CLIENTE pede para falar com uma pessoa, os dois vão
    # a `False`, porque aí quem quis sair da IA foi ele.
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # A Helô já saiu deste chamado — escalou, e o chamado passou a ser do
    # humano. Ela não volta a falar aqui nem que o cliente escreva de novo.
    #
    # Existe porque o `ai_enabled` estava fazendo dois trabalhos. Enquanto ela
    # falava uma vez por chamado, "escalou" e "IA desligada" davam no mesmo. Com
    # ela conversando, escalar por decisão do modelo, por teto de trocas ou por
    # a IA estar fora do ar passou a desligar também a sugestão de resposta e o
    # resumo DO TÉCNICO — tirando a ferramenta dele exatamente nos chamados em
    # que a IA já tinha falhado, e sem ninguém ter pedido.
    #
    # Separado, cada campo responde a uma pergunta só: `ai_enabled` é "alguém
    # quer a IA fora daqui?", `helo_saiu` é "a conversa dela acabou?".
    helo_saiu: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # SLA
    sla_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sla_configs.id")
    )
    sla_response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_resolve_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_first_response: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_response_breach: Mapped[bool] = mapped_column(Boolean, default=False)
    sla_resolve_breach: Mapped[bool] = mapped_column(Boolean, default=False)
    sla_paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_total_paused_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Total de minutos ÚTEIS concedidos por extensões de prazo no ciclo ATUAL.
    # Acumulador, e não um prazo já calculado: conceder +3 e depois +1 tem de
    # dar o mesmo que conceder +4, e isso só vale se o prazo for sempre
    # recomputado da base. A reabertura zera; as linhas de
    # `ticket_sla_extensions` do ciclo anterior continuam lá.
    sla_resolve_extension_total_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    # O prazo efetivo de resolução, MATERIALIZADO para o SQL agregado.
    #
    # O painel e os relatórios decidem violação em `count(...).filter(...)`, e
    # não passam pelo motor: comparavam `sla_resolve_due_at < now()`, que
    # ignora pausa e ignoraria a extensão. Esta coluna é a versão SQL do que
    # `prazo_efetivo_de_resolucao` devolve, e quem a escreve é
    # `atualiza_prazo_efetivo` — ninguém mais.
    sla_resolve_effective_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # Escrita por quem resolve, quando resolve fora do prazo. Nulo significa
    # DUAS coisas legitimas e permanentes: resolvido dentro do prazo, ou
    # resolvido antes de a exigencia existir. Nao ha default nem NOT NULL de
    # proposito -- vazio apagaria a diferenca entre "nao precisou" e "nao
    # preencheu".
    sla_breach_justification: Mapped[str | None] = mapped_column(Text)

    # Notas internas (visível apenas para admin/técnico)
    technician_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Observação do cliente (visível para todos, editável apenas pelo cliente)
    client_observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Nota de resolução (preenchida ao concluir o ticket)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # IA
    ai_classification: Mapped[str | None] = mapped_column(String(100))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_conversation_summary: Mapped[str | None] = mapped_column(Text)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Ciclo de encerramento (RN-005 / RN-006).
    # `resolved_at` é a referência dos dois prazos — fechamento automático e
    # reabertura — e por isso não pode ser confundido com `closed_at`, que é
    # reescrito quando o chamado passa para Fechado.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    auto_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    creator: Mapped["User"] = relationship(
        back_populates="created_tickets", foreign_keys=[creator_id]
    )
    assignee: Mapped["User | None"] = relationship(
        back_populates="assigned_tickets", foreign_keys=[assignee_id]
    )
    product: Mapped["Product | None"] = relationship(back_populates="tickets")
    sla_config: Mapped["SLAConfig | None"] = relationship(back_populates="tickets")
    sla_extensions: Mapped[list["TicketSlaExtension"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    histories: Mapped[list["TicketHistory"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    satisfaction_survey: Mapped["SatisfactionSurvey | None"] = relationship(
        back_populates="ticket", uselist=False, cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=ticket_tags, back_populates="tickets", lazy="selectin"
    )
    equipments: Mapped[list["Equipment"]] = relationship(
        secondary=ticket_equipments, back_populates="tickets", lazy="selectin"
    )
    ticket_notes: Mapped[list["TicketNote"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_tickets_status_priority", "status", "priority"),
        Index("ix_tickets_assignee_status", "assignee_id", "status"),
    )


class TicketHistory(Base):
    """Historico de alteracoes de tickets"""

    __tablename__ = "ticket_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    # NULL = ação do próprio sistema (ex.: fechamento automático da RN-005)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    ticket: Mapped["Ticket"] = relationship(back_populates="histories")
    user: Mapped["User | None"] = relationship(back_populates="ticket_histories")

    __table_args__ = (Index("ix_ticket_history_ticket_created", "ticket_id", "created_at"),)


class GroupNote(Base):
    """Notas de grupos (múltiplas por grupo)"""

    __tablename__ = "group_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group: Mapped["Group"] = relationship(back_populates="group_notes")
    author: Mapped["User"] = relationship()


class CompanyNote(Base):
    """Notas de empresas (múltiplas por empresa)"""

    __tablename__ = "company_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="company_notes")
    author: Mapped["User"] = relationship()


class TicketSlaExtension(Base):
    """Cada prorrogação de prazo concedida, como evento próprio.

    Por que tabela e não só `ticket_history`: a extensão é um COMPROMISSO DE
    PRAZO comunicado ao cliente, pode acontecer várias vezes, e cada concessão
    tem dados próprios — quantos dias, de que prazo para que prazo, com que
    justificativa. Guardar isso espremido em `old_value`/`new_value` deixaria
    a quantidade concedida como informação derivada, e ela é o que o cliente
    lê na Atividade.

    **Append-only pela regra de negócio.** Nenhum fluxo edita ou apaga uma
    linha daqui: uma prorrogação concedida aconteceu, e reabrir o chamado zera
    o acumulador do ciclo novo sem tocar no registro do ciclo anterior.
    """

    __tablename__ = "ticket_sla_extensions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    # Quem concedeu. Sem `ondelete`: a autoria de um compromisso de prazo não
    # some porque a conta foi desligada — é o mesmo critério do histórico.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # Dias ÚTEIS pedidos (1, 3, 5, 15 ou 30) e o que eles valem em minutos
    # úteis. Os dois, e não só um: `days` é o que a pessoa escolheu e o que a
    # tela mostra; `business_minutes` é o que entrou na conta. Guardar apenas
    # os dias faria a auditoria depender da jornada VIGENTE para reconstruir o
    # que foi concedido naquele dia.
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    business_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    previous_effective_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_effective_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["Ticket"] = relationship(back_populates="sla_extensions")


class TicketNote(Base):
    """Notas internas de tickets (múltiplas por ticket)"""

    __tablename__ = "ticket_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["Ticket"] = relationship(back_populates="ticket_notes")
    author: Mapped["User"] = relationship()


class Attachment(Base):
    """Anexos de tickets"""

    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    virus_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    virus_clean: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    ticket: Mapped["Ticket"] = relationship(back_populates="attachments")
    user: Mapped["User"] = relationship(back_populates="attachments")


class LibraryFile(Base):
    """Arquivo recorrente: manual, guia, formulario.

    Guardado UMA vez e apontado por quem o usa. A mensagem de chat que o anexa
    referencia esta linha em vez de copiar o binario -- copiar multiplicaria o
    mesmo PDF no disco e criaria a duvida de qual copia vale quando o admin
    subir uma versao nova.
    """

    __tablename__ = "library_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Nulo = nao e de um aparelho especifico (politica, formulario).
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    visibility: Mapped[LibraryVisibility] = mapped_column(
        Enum(LibraryVisibility, name="libraryvisibility"),
        default=LibraryVisibility.internal,
        server_default="internal",
        nullable=False,
    )

    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    virus_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    virus_clean: Mapped[bool] = mapped_column(Boolean, default=False)

    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["Product | None"] = relationship()


class ChatMessage(Base):
    """Mensagens de chat em tempo real (WebSocket)"""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    # Nulo quando quem falou nao foi gente: a Helo (`is_ai`) e as mensagens
    # automaticas do sistema. A alternativa era criar um usuario "Helo" no
    # banco, e ele apareceria na lista de tecnicos, poderia ser atribuido a
    # chamado e receberia e-mail de notificacao -- tres problemas novos para
    # resolver um. Mesmo padrao ja adotado em `ticket_history.user_id`, onde
    # nulo significa "foi o sistema".
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    # Aponta para a biblioteca, nao copia. SET NULL no banco: apagar um item
    # da biblioteca nao pode apagar a conversa -- a mensagem sobrevive sem o
    # arquivo, que e ruim mas recuperavel; apagar a fala do tecnico nao e.
    library_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("library_files.id", ondelete="SET NULL"), index=True
    )
    library_file: Mapped["LibraryFile | None"] = relationship()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    ticket: Mapped["Ticket"] = relationship(back_populates="chat_messages")
    sender: Mapped["User"] = relationship(back_populates="chat_messages")

    __table_args__ = (Index("ix_chat_messages_ticket_created", "ticket_id", "created_at"),)


class KBArticle(Base):
    """Artigos da Base de Conhecimento"""

    __tablename__ = "kb_articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    category: Mapped[TicketCategory] = mapped_column(
        Enum(TicketCategory), default=TicketCategory.general
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)
    status: Mapped[KBArticleStatus] = mapped_column(
        Enum(KBArticleStatus), default=KBArticleStatus.draft, index=True
    )
    # A Helô pode usar este artigo para responder cliente. Padrão `true`: desde
    # 10/09/2026 artigo publicado alimenta as respostas dela sem ninguém rodar
    # nada, e esta é a forma de manter um artigo na barra lateral e FORA da IA.
    # Coluna, e não tag, porque tag é texto livre e erro de digitação mudaria
    # o comportamento em silêncio. O porquê do padrão, com o número e a data,
    # está na migration `c9x0y1z2a3b4`.
    helo_pode_ler: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    helpful: Mapped[int] = mapped_column(Integer, default=0)
    not_helpful: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    author: Mapped["User"] = relationship(back_populates="kb_articles")
    comments: Mapped[list["KBComment"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    # Sem nenhum produto vinculado, o artigo vale para todos os produtos
    products: Mapped[list["Product"]] = relationship(
        secondary=kb_article_products, back_populates="kb_articles"
    )

    __table_args__ = (Index("ix_kb_articles_category_status", "category", "status"),)


class KBComment(Base):
    """Comentários e respostas em artigos da Base de Conhecimento"""

    __tablename__ = "kb_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_comments.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    article: Mapped["KBArticle"] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship()


class SLAConfig(Base):
    """Configuracoes de SLA por nivel de prioridade"""

    __tablename__ = "sla_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level: Mapped[SLALevel] = mapped_column(Enum(SLALevel), unique=True, nullable=False)
    # MINUTOS, nao horas. Metade da resposta do nivel critico e 30 min, e isso
    # nao cabe numa coluna de horas inteiras -- foi o que forcou a troca de
    # unidade. Ver a migration a7b8c9d0e1f2.
    response_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolve_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_threshold: Mapped[int] = mapped_column(Integer, default=80)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="sla_config")


class SatisfactionSurvey(Base):
    """Pesquisa de satisfacao (CSAT)"""

    __tablename__ = "satisfaction_surveys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1 a 10
    # O quanto recomendaria a empresa, 1 a 10. Nulo nas avaliações enviadas
    # antes desta pergunta existir — a coleta antiga não tem como ser recuperada.
    recommend_rating: Mapped[int | None] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    ticket: Mapped["Ticket"] = relationship(back_populates="satisfaction_survey")
    user: Mapped["User"] = relationship(back_populates="satisfaction_given")

    __table_args__ = (Index("ix_satisfaction_surveys_rating", "rating"),)


class Notification(Base):
    """Notificacoes in-app e email"""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )


class AuditLog(Base):
    """Logs de auditoria (LGPD compliance)"""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    old_data: Mapped[dict | None] = mapped_column(JSONB)
    new_data: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))  # suporta IPv6
    user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Relacionamentos
    user: Mapped["User | None"] = relationship(back_populates="audit_logs")

    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)


class Tag(Base):
    """Etiquetas para classificação de tickets"""

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tickets: Mapped[list["Ticket"]] = relationship(secondary=ticket_tags, back_populates="tags")


class QuickReply(Base):
    """Mensagens prontas que o técnico insere no chat digitando /atalho"""

    __tablename__ = "quick_replies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shortcut: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CalendarEvent(Base):
    """Eventos da agenda da equipe (admin + técnicos)"""

    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[CalendarEventType] = mapped_column(
        Enum(CalendarEventType), default=CalendarEventType.event, nullable=False
    )
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")
    # As duas continuam NOT NULL e com hora. "Dia inteiro" nao as torna nulas:
    # a API deriva as bordas do dia quando `all_day` esta ligado, e o indice, os
    # filtros e as leituras antigas seguem funcionando sem saber da chave.
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Data FLUTUANTE quando ligado: o evento vale das 00:00:00Z as 23:59:59.999999Z
    # da data escolhida, e a tela o desenha pela DATA, nao pelo instante. Ver o
    # cabecalho de `app/utils/agenda.py` -- e a decisao que permite os eventos
    # antigos virarem dia inteiro sem recalcular linha nenhuma.
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped["User | None"] = relationship()


# ── BASE DA HELÔ (Fase 2) ────────────────────────────────────
#
# Separada dos `KBArticle`, confirmando a decisão de 26/08. São dois corpora
# com donos e ciclos diferentes: o artigo da Base de Conhecimento é escrito por
# gente da equipe, tem autor, rascunho e contador de "foi útil"; o trecho de
# manual é derivado de um arquivo que alguém do fabricante escreveu e que a
# ingestão recorta. Misturar os dois obrigaria metade das colunas de cada um a
# nascer nula na outra metade das linhas.

# Dimensão do vetor. 1024 é o que bge-m3 e multilingual-e5-large produzem — os
# dois modelos locais em avaliação. NÃO é configurável: `vector(N)` é tipo de
# coluna, e trocar o modelo por um de dimensão diferente é migration nova, não
# variável de ambiente. Está escrito aqui para que a troca seja uma decisão
# consciente e não a descoberta de um INSERT recusado em produção.
HELO_EMBEDDING_DIM = 1024


class HeloChunk(Base):
    """Um trecho recuperável — a unidade que a busca devolve e que a Helô cita."""

    __tablename__ = "helo_chunks"
    __table_args__ = (
        # Único por artigo: a indexação não pode gravar dois trechos disputando
        # a mesma posição, senão a ordem de leitura vira sorteio.
        Index("ix_helo_chunks_artigo_ordem", "article_id", "ordem", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # O ARTIGO de onde o trecho saiu. Desde 10/09/2026 a fonte da Helô é a
    # Base de Conhecimento, e o produto do trecho é o produto do artigo — por
    # `kb_article_products`, que a tela já edita. Um vínculo por trecho seria
    # uma segunda fonte de verdade para a mesma pergunta.
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id", ondelete="CASCADE"), index=True
    )
    # Texto, e não número: aqui cabe tanto "8.2 Alterar Idioma" quanto um
    # título de artigo escrito pelo suporte — e é esta string que a resposta
    # cita como fonte.
    secao: Mapped[str] = mapped_column(String(255), nullable=False)
    # A posição do trecho dentro do artigo. A ordem do texto é a ordem do
    # procedimento, e ela não se recupera do texto depois: "8.10" vem depois de
    # "8.9", e ordenar por `secao` como string colocaria "8.10" antes de "8.2".
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    # O trecho ensina um procedimento que só roda com senha de administrador.
    # O valor da senha é REDIGIDO na importação do manual e o procedimento
    # fica — as duas metades da mesma decisão. Excluir o trecho pareceria mais
    # seguro e é pior: a busca não acharia nada, a Helô escalaria por NADA
    # ENCONTRADO, e nem ela nem o técnico saberiam o motivo. Com a marca ela
    # escala dizendo o motivo exato.
    exige_credencial_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Nulo só por um instante: a indexação embute antes de gravar, e com o
    # serviço de embedding fora ela não grava nada — o trecho velho fica no
    # lugar e a próxima varredura tenta de novo.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(HELO_EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HeloIndexacao(Base):
    """
    O que já foi indexado, e de qual versão do texto.

    Existe para a varredura periódica reindexar SÓ o artigo que mudou. O hash
    é do RESULTADO do corte — dos trechos que seriam gravados —, e não do
    `content` cru nem do `updated_at`:

    - `updated_at` anda a cada visualização do artigo (`view_count` é
      incrementado por UPDATE), e cada clique pagaria embedding de texto igual;
    - o `content` cru não enxerga mudança de receita: consertar o corte ou a
      redação com o texto igual deixaria a base com o corte velho. É a lição
      do `_hash_do_resultado` da ingestão por arquivo, que existia pelo mesmo
      motivo.
    """

    __tablename__ = "helo_indexacao"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id", ondelete="CASCADE"), primary_key=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    indexado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── TELEFONIA (Fase 2B) ──────────────────────────────────────


class TicketCall(Base):
    """Uma TENTATIVA de ligar para o cliente de um chamado.

    O nome importa: a linha nasce antes de existir chamada, e pode terminar
    sem que nunca tenhamos sabido se existiu. Modelar só "chamadas
    confirmadas" perderia exatamente o estado perigoso — aquele em que o
    `POST /calls` pode ter tocado o telefone de alguém e a resposta não voltou.
    É por isso que `provider_call_id` aceita NULL: uma tabela que o exigisse
    NOT NULL seria incapaz de registrar o caso que mais precisa ser
    reconciliado depois.

    Por que tabela própria, e não coluna em `tickets`
    --------------------------------------------------
    Uma tentativa tem estado e ciclo próprios, e a maioria dos chamados nunca
    terá nenhuma. Cinco colunas nulas em 99% das linhas é o sinal, já escrito
    nesta casa, de que são duas coisas — o mesmo critério que criou
    `helo_indexacao` em vez de inchar `kb_articles`.

    Não há `relationship()` para `Ticket`, de propósito: `helo_indexacao` é o
    precedente de tabela satélite que se liga só pela FK. Evita tocar o modelo
    `Ticket` por uma frente que ainda não tem consumidor.

    O que esta tabela NÃO guarda, e é escolha
    ------------------------------------------
    Telefone, `caller`, `extension`, cabeçalho, corpo da requisição, corpo da
    resposta, `message` do fornecedor, metadata e URL de gravação. O telefone
    canônico continua em `users.phone`, e o resto é dado de terceiro que não
    precisamos reter para saber o estado da tentativa. Guardar resposta bruta
    seria criar um segundo lugar por onde PII e credencial poderiam vazar.
    """

    __tablename__ = "ticket_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL = quem iniciou não existe mais. Mesmo critério de `kb_comments.author_id`
    # e `equipments.owner_id`: a tentativa é fato do chamado e sobrevive à
    # exclusão da conta; quem some é a autoria.
    initiated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # STRING OPACA, e `Text` porque não sabemos o comprimento. A documentação
    # oficial diz `string` e mostra DOIS formatos para o mesmo campo: 27
    # caracteres base62 (`1PkXhmBsYAvr9legLB2d7BimT0Q`) na referência da API, e
    # UUID textual de 36 (`bdf199fa-...`) no guia de integração. Por isso NÃO é
    # `UUID` do PostgreSQL: o tipo nativo rejeitaria o primeiro formato, e o
    # HelpHS quebraria por validar algo que o fornecedor nunca prometeu.
    # Nada é validado, nada é transformado — o valor volta como chegou.
    provider_call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    creation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    # O status HTTP que o fornecedor devolveu, quando houve resposta. NULL
    # quando não houve — e a diferença entre "não respondeu" e "respondeu 500"
    # é justamente o que separa `unavailable` de `indeterminate`.
    provider_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # SQL portável de propósito: `IN`, `<>` e `IS NOT NULL` existem no
        # SQLite, então esta constraint NÃO precisa do `ddl_if` que o CHECK do
        # telefone precisou — lá o problema era `regexp_replace`, que é só do
        # PostgreSQL. Aqui a mesma regra vale nos dois bancos, e a suíte que
        # monta schema por `create_all` a exercita de graça.
        CheckConstraint(
            "creation_status IN ('pending', 'dispatching', 'confirmed', "
            "'rejected', 'unavailable', 'indeterminate')",
            name="ck_ticket_calls_status_conhecido",
        ),
        # Confirmada sem identificador seria um registro que afirma saber da
        # chamada sem ter como apontá-la — nem para consultar, nem para
        # desligar. O inverso NÃO é imposto: ter `provider_call_id` sem estar
        # `confirmed` é estado legítimo que a reconciliação da 2D pode produzir.
        CheckConstraint(
            "creation_status <> 'confirmed' OR provider_call_id IS NOT NULL",
            name="ck_ticket_calls_confirmada_tem_id",
        ),
        # Índice único NOMEADO, e não `unique=True` na coluna, para que o
        # downgrade da migration remova exatamente este objeto — mesmo padrão
        # do `uq_equipments_product_serial`. No PostgreSQL vários NULL convivem
        # sob UNIQUE, que é o comportamento que queremos: toda tentativa sem
        # identificador é distinta das outras.
        Index("uq_ticket_calls_provider_call_id", "provider_call_id", unique=True),
        Index("ix_ticket_calls_ticket_created", "ticket_id", "created_at"),
    )
