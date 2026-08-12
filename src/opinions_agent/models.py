from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class CycleStatus(StrEnum):
    STARTING = "starting"
    ACTIVE = "active"
    STOPPED = "stopped"
    COMPLETED = "completed"


class BatchStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_USER = "awaiting_user"
    STOPPED = "stopped"
    COMPLETED = "completed"


class GitPhase(StrEnum):
    AGENT_EDITING = "agent_editing"
    COMMIT_INTENT = "commit_intent"
    COMMITTED = "committed"
    PUSHED = "pushed"
    COMPLETED = "completed"


class OpinionCycle(Base):
    __tablename__ = "opinion_cycles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    week_key: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default=CycleStatus.STARTING.value)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    initial_evidence_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    batch_count: Mapped[int] = mapped_column(Integer, default=0)
    current_batch: Mapped[int] = mapped_column(Integer, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    batches: Mapped[list[OpinionBatch]] = relationship(back_populates="cycle", cascade="all, delete-orphan")


class OpinionBatch(Base):
    __tablename__ = "opinion_batches"
    __table_args__ = (UniqueConstraint("cycle_id", "batch_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("opinion_cycles.id", ondelete="CASCADE"), index=True)
    batch_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True, default=BatchStatus.QUEUED.value)
    evidence_versions: Mapped[list] = mapped_column(JSON, default=list)
    document_ids: Mapped[list] = mapped_column(JSON, default=list)
    bundle_path: Mapped[str] = mapped_column(Text)
    evidence_count: Mapped[int] = mapped_column(Integer)
    document_count: Mapped[int] = mapped_column(Integer)
    latest_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    successful_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    cycle: Mapped[OpinionCycle] = relationship(back_populates="batches")


class OpinionEvidenceAssignment(Base):
    __tablename__ = "opinion_evidence_assignments"
    __table_args__ = (UniqueConstraint("evidence_id", "fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(160), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(32))
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("opinion_cycles.id"), nullable=True, index=True)
    batch_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowLease(Base):
    __tablename__ = "workflow_leases"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OpinionRun(Base):
    __tablename__ = "opinion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(32), index=True, default=RunStatus.PENDING_AGENT.value)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    batch: Mapped[int] = mapped_column(Integer, default=1)
    batch_count: Mapped[int] = mapped_column(Integer, default=1)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("opinion_cycles.id"), nullable=True, index=True)
    turn_seq: Mapped[int] = mapped_column(Integer, default=0)
    input_paths: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_output: Mapped[dict] = mapped_column(JSON, default=dict)
    resume_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    baseline_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    git_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    git_base_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    git_result_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_log_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reconcile_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconcile_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    proposals: Mapped[list[OpinionProposal]] = relationship(back_populates="run", cascade="all, delete-orphan")


class OpinionProposal(Base):
    __tablename__ = "opinion_proposals"
    __table_args__ = (UniqueConstraint("opinion_run_id", "proposal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opinion_run_id: Mapped[str] = mapped_column(ForeignKey("opinion_runs.id", ondelete="CASCADE"), index=True)
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
