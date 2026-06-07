from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    PENDING_AGENT = "pending_agent"
    AWAITING_USER = "awaiting_user"
    REVISING = "revising"
    APPROVED = "approved"
    COMMITTING = "committing"
    COMMITTED = "committed"
    REJECTED = "rejected"
    FAILED = "failed"


BLOCKING_SELECTION_STATUSES = {
    RunStatus.PENDING_AGENT.value,
    RunStatus.AWAITING_USER.value,
    RunStatus.REVISING.value,
    RunStatus.APPROVED.value,
    RunStatus.COMMITTING.value,
    RunStatus.COMMITTED.value,
    RunStatus.REJECTED.value,
}


class ReadwiseSyncState(Base):
    __tablename__ = "readwise_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_after: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class ReadwiseHighlight(Base):
    __tablename__ = "readwise_highlights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    readwise_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_author: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    highlighted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_external: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    runs: Mapped[list[SummaryRunHighlight]] = relationship(back_populates="highlight")


class SummaryRun(Base):
    __tablename__ = "summary_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(32), index=True, default=RunStatus.PENDING_AGENT.value)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_paths: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_output: Mapped[dict] = mapped_column(JSON, default=dict)
    resume_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    highlights: Mapped[list[SummaryRunHighlight]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SummaryRunHighlight(Base):
    __tablename__ = "summary_run_highlights"
    __table_args__ = (UniqueConstraint("summary_run_id", "readwise_highlight_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary_run_id: Mapped[str] = mapped_column(ForeignKey("summary_runs.id", ondelete="CASCADE"), index=True)
    readwise_highlight_id: Mapped[int] = mapped_column(
        ForeignKey("readwise_highlights.id", ondelete="CASCADE"),
        index=True,
    )

    run: Mapped[SummaryRun] = relationship(back_populates="highlights")
    highlight: Mapped[ReadwiseHighlight] = relationship(back_populates="runs")


class TelegramInteraction(Base):
    __tablename__ = "telegram_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    summary_run_id: Mapped[str | None] = mapped_column(ForeignKey("summary_runs.id"), nullable=True, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    callback_query_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
