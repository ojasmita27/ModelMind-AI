"""add experiment_model_results

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10

Adds per-candidate-model evaluation results so every trained model's real
metrics are persisted, not just the selected winner. Existing experiment
rows are untouched; experiments without result rows simply have none.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_model_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("task_type", sa.String(length=20), nullable=False),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cross_validation_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("validation_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("test_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("confusion_matrix", sa.JSON(), nullable=True),
        sa.Column("classification_report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], name="fk_emr_experiment_id_experiments", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_experiment_model_results"),
        sa.UniqueConstraint("experiment_id", "model_name", name="uq_emr_experiment_model"),
    )
    op.create_index("ix_experiment_model_results_experiment_id", "experiment_model_results", ["experiment_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_model_results_experiment_id", table_name="experiment_model_results")
    op.drop_table("experiment_model_results")
