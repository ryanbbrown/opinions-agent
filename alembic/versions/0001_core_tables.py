"""core tables

Revision ID: 0001_core_tables
Revises:
Create Date: 2026-06-07
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_core_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "readwise_sync_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("updated_after", sa.String(length=64), nullable=True),
        sa.Column("page_cursor", sa.String(length=512), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "readwise_highlights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("readwise_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=True),
        sa.Column("document_title", sa.Text(), nullable=True),
        sa.Column("document_author", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("highlighted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_external", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_readwise_highlights_readwise_id"), "readwise_highlights", ["readwise_id"], unique=True)
    op.create_table(
        "summary_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("input_paths", sa.JSON(), nullable=False),
        sa.Column("agent_output", sa.JSON(), nullable=False),
        sa.Column("resume_state", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lock_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_summary_runs_status"), "summary_runs", ["status"], unique=False)
    op.create_table(
        "summary_run_highlights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("summary_run_id", sa.String(length=36), nullable=False),
        sa.Column("readwise_highlight_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["readwise_highlight_id"], ["readwise_highlights.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["summary_run_id"], ["summary_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("summary_run_id", "readwise_highlight_id"),
    )
    op.create_index(
        op.f("ix_summary_run_highlights_readwise_highlight_id"),
        "summary_run_highlights",
        ["readwise_highlight_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_summary_run_highlights_summary_run_id"),
        "summary_run_highlights",
        ["summary_run_id"],
        unique=False,
    )
    op.create_table(
        "telegram_interactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("summary_run_id", sa.String(length=36), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("update_id", sa.BigInteger(), nullable=True),
        sa.Column("callback_query_id", sa.String(length=128), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["summary_run_id"], ["summary_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_telegram_interactions_chat_id"), "telegram_interactions", ["chat_id"], unique=False)
    op.create_index(
        op.f("ix_telegram_interactions_callback_query_id"),
        "telegram_interactions",
        ["callback_query_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_telegram_interactions_idempotency_key"),
        "telegram_interactions",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_telegram_interactions_summary_run_id"),
        "telegram_interactions",
        ["summary_run_id"],
        unique=False,
    )
    op.create_index(op.f("ix_telegram_interactions_update_id"), "telegram_interactions", ["update_id"], unique=True)


def downgrade() -> None:
    op.drop_table("telegram_interactions")
    op.drop_table("summary_run_highlights")
    op.drop_table("summary_runs")
    op.drop_table("readwise_highlights")
    op.drop_table("readwise_sync_state")
