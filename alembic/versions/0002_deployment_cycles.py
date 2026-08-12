"""deployment cycles and recovery state

Revision ID: 0002_deployment_cycles
Revises: 0001_opinion_tables
Create Date: 2026-08-11
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_deployment_cycles"
down_revision = "0001_opinion_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opinion_cycles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("week_key", sa.String(10), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initial_evidence_after", sa.DateTime(timezone=True)),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("batch_count", sa.Integer(), nullable=False),
        sa.Column("current_batch", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("failure_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_opinion_cycles_week_key", "opinion_cycles", ["week_key"], unique=True)
    op.create_index("ix_opinion_cycles_status", "opinion_cycles", ["status"])
    op.create_table(
        "opinion_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cycle_id", sa.String(36), sa.ForeignKey("opinion_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence_versions", sa.JSON(), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("bundle_path", sa.Text(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("latest_run_id", sa.String(36)),
        sa.Column("successful_run_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cycle_id", "batch_number"),
    )
    op.create_index("ix_opinion_batches_cycle_id", "opinion_batches", ["cycle_id"])
    op.create_index("ix_opinion_batches_status", "opinion_batches", ["status"])
    op.create_table(
        "opinion_evidence_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evidence_id", sa.String(160), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("cycle_id", sa.String(36), sa.ForeignKey("opinion_cycles.id")),
        sa.Column("batch_number", sa.Integer()),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evidence_id", "fingerprint"),
    )
    op.create_index("ix_opinion_evidence_assignments_evidence_id", "opinion_evidence_assignments", ["evidence_id"])
    op.create_index("ix_opinion_evidence_assignments_cycle_id", "opinion_evidence_assignments", ["cycle_id"])
    op.create_table(
        "workflow_leases",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column("owner_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("opinion_runs", sa.Column("batch_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("opinion_runs", sa.Column("cycle_id", sa.String(36)))
    op.add_column("opinion_runs", sa.Column("lease_owner", sa.String(64)))
    op.add_column("opinion_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("opinion_runs", sa.Column("git_phase", sa.String(32)))
    op.add_column("opinion_runs", sa.Column("git_base_sha", sa.String(64)))
    op.add_column("opinion_runs", sa.Column("git_result_sha", sa.String(64)))
    op.add_column("opinion_runs", sa.Column("decision_log_hash", sa.String(64)))
    op.create_foreign_key("fk_opinion_runs_cycle", "opinion_runs", "opinion_cycles", ["cycle_id"], ["id"])
    op.create_index("ix_opinion_runs_cycle_id", "opinion_runs", ["cycle_id"])
    proposal_unique = next(
        (
            constraint["name"]
            for constraint in sa.inspect(op.get_bind()).get_unique_constraints("opinion_proposals")
            if constraint["column_names"] == ["opinion_run_id", "batch", "proposal_id"]
        ),
        None,
    )
    if not proposal_unique:
        raise RuntimeError("0002 requires the 0001 opinion proposal batch uniqueness constraint")
    op.drop_constraint(proposal_unique, "opinion_proposals", type_="unique")
    op.drop_column("opinion_proposals", "batch")
    op.create_unique_constraint(
        "uq_opinion_proposals_run_proposal",
        "opinion_proposals",
        ["opinion_run_id", "proposal_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_opinion_proposals_run_proposal", "opinion_proposals", type_="unique")
    op.add_column("opinion_proposals", sa.Column("batch", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint(
        "uq_opinion_proposals_run_batch_proposal",
        "opinion_proposals",
        ["opinion_run_id", "batch", "proposal_id"],
    )
    op.drop_index("ix_opinion_runs_cycle_id", table_name="opinion_runs")
    op.drop_constraint("fk_opinion_runs_cycle", "opinion_runs", type_="foreignkey")
    for column in (
        "decision_log_hash",
        "git_result_sha",
        "git_base_sha",
        "git_phase",
        "lease_expires_at",
        "lease_owner",
        "cycle_id",
        "batch_count",
    ):
        op.drop_column("opinion_runs", column)
    op.drop_table("workflow_leases")
    op.drop_table("opinion_evidence_assignments")
    op.drop_table("opinion_batches")
    op.drop_table("opinion_cycles")
