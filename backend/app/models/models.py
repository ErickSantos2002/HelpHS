# ============================================================
# HELP DESK — HEALTH & SAFETY
# SQLAlchemy 2.0 Models — Banco de Dados PostgreSQL
# Baseado no Dicionario de Dados v1.0
# ============================================================

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
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
    general = "general"
    other = "other"


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


# ── MODELS ───────────────────────────────────────────────────


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
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # LGPD
    lgpd_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    lgpd_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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

    __table_args__ = (Index("ix_users_role_status", "role", "status"),)


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


class Equipment(Base):
    """Equipamentos associados a produtos"""

    __tablename__ = "equipments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    model: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    product: Mapped["Product"] = relationship(back_populates="equipments")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="equipment")


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
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority), default=TicketPriority.medium, nullable=False, index=True
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
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipments.id")
    )

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

    # Notas internas (visível apenas para admin/técnico)
    technician_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # IA
    ai_classification: Mapped[str | None] = mapped_column(String(100))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_conversation_summary: Mapped[str | None] = mapped_column(Text)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    equipment: Mapped["Equipment | None"] = relationship(back_populates="tickets")
    sla_config: Mapped["SLAConfig | None"] = relationship(back_populates="tickets")
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
        back_populates="ticket", uselist=False
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
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    ticket: Mapped["Ticket"] = relationship(back_populates="histories")
    user: Mapped["User"] = relationship(back_populates="ticket_histories")

    __table_args__ = (Index("ix_ticket_history_ticket_created", "ticket_id", "created_at"),)


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


class ChatMessage(Base):
    """Mensagens de chat em tempo real (WebSocket)"""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
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
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=[])
    status: Mapped[KBArticleStatus] = mapped_column(
        Enum(KBArticleStatus), default=KBArticleStatus.draft, index=True
    )
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

    __table_args__ = (Index("ix_kb_articles_category_status", "category", "status"),)


class SLAConfig(Base):
    """Configuracoes de SLA por nivel de prioridade"""

    __tablename__ = "sla_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level: Mapped[SLALevel] = mapped_column(Enum(SLALevel), unique=True, nullable=False)
    response_time_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    resolve_time_hours: Mapped[int] = mapped_column(Integer, nullable=False)
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
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1 a 5
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
