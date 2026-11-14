"""benchmark lab: tuning config + per-model params/duration

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12

Additive only: experiments.tuning_config (JSON), experiment_model_results
.best_params (JSON), experiment_model_results.training_duration_ms (float).
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("tuning_config", sa.JSON(), nullable=True))
    op.add_column("experiment_model_results", sa.Column("best_params", sa.JSON(), nullable=True))
    op.add_column("experiment_model_results", sa.Column("training_duration_ms", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiment_model_results", "training_duration_ms")
    op.drop_column("experiment_model_results", "best_params")
    op.drop_column("experiments", "tuning_config")
