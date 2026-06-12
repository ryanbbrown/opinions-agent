"""opinion workflow tables

Revision ID: 0001_opinion_tables
Revises:
Create Date: 2026-06-12
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_opinion_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opinion_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch", sa.Integer(), nullable=False),
        sa.Column("input_paths", sa.JSON(), nullable=False),
        sa.Column("agent_output", sa.JSON(), nullable=False),
        sa.Column("resume_state", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_opinion_runs_status"), "opinion_runs", ["status"], unique=False)
    op.create_table(
        "opinion_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opinion_run_id", sa.String(length=36), nullable=False),
        sa.Column("batch", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("opinion_id", sa.String(length=32), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("current_text", sa.Text(), nullable=True),
        sa.Column("proposed_text", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("supporting_highlight_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("applied_opinion_id", sa.String(length=32), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opinion_run_id"], ["opinion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opinion_run_id", "batch", "proposal_id"),
    )
    op.create_index(op.f("ix_opinion_proposals_opinion_run_id"), "opinion_proposals", ["opinion_run_id"], unique=False)
    op.create_index(op.f("ix_opinion_proposals_status"), "opinion_proposals", ["status"], unique=False)
    op.create_table(
        "telegram_interactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("opinion_run_id", sa.String(length=36), nullable=True),
        sa.Column("opinion_proposal_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("update_id", sa.BigInteger(), nullable=True),
        sa.Column("callback_query_id", sa.String(length=128), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opinion_run_id"], ["opinion_runs.id"]),
        sa.ForeignKeyConstraint(["opinion_proposal_id"], ["opinion_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("callback_query_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("update_id"),
    )
    op.create_index(op.f("ix_telegram_interactions_chat_id"), "telegram_interactions", ["chat_id"], unique=False)
    op.create_index(
        op.f("ix_telegram_interactions_opinion_run_id"),
        "telegram_interactions",
        ["opinion_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("telegram_interactions")
    op.drop_table("opinion_proposals")
    op.drop_table("opinion_runs")
