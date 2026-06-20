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
    RUNNING_AGENT = "running_agent"
    AWAITING_USER = "awaiting_user"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    ABANDONED = "abandoned"


NON_TERMINAL_RUN_STATUSES = {
    RunStatus.PENDING_AGENT.value,
    RunStatus.RUNNING_AGENT.value,
    RunStatus.AWAITING_USER.value,
}


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class OpinionRun(Base):
    __tablename__ = "opinion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(32), index=True, default=RunStatus.PENDING_AGENT.value)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    batch: Mapped[int] = mapped_column(Integer, default=1)
    turn_seq: Mapped[int] = mapped_column(Integer, default=0)
    input_paths: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_output: Mapped[dict] = mapped_column(JSON, default=dict)
    resume_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    proposals: Mapped[list[OpinionProposal]] = relationship(back_populates="run", cascade="all, delete-orphan")


class OpinionProposal(Base):
    __tablename__ = "opinion_proposals"
    __table_args__ = (UniqueConstraint("opinion_run_id", "batch", "proposal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opinion_run_id: Mapped[str] = mapped_column(ForeignKey("opinion_runs.id", ondelete="CASCADE"), index=True)
    batch: Mapped[int] = mapped_column(Integer, default=1)
    proposal_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    opinion_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    supporting_highlight_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), index=True, default=ProposalStatus.PENDING.value)
    applied_opinion_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    run: Mapped[OpinionRun] = relationship(back_populates="proposals")


class TelegramInteraction(Base):
    __tablename__ = "telegram_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    opinion_run_id: Mapped[str | None] = mapped_column(ForeignKey("opinion_runs.id"), nullable=True, index=True)
    opinion_proposal_id: Mapped[int | None] = mapped_column(ForeignKey("opinion_proposals.id"), nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    callback_query_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
