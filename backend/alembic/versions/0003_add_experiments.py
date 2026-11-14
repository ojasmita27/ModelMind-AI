"""add experiments

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("task_type", sa.String(length=20), nullable=False),
        sa.Column("target_column", sa.String(length=120), nullable=False),
        sa.Column("train_fraction", sa.Float(), nullable=False),
        sa.Column("validation_fraction", sa.Float(), nullable=False),
        sa.Column("test_fraction", sa.Float(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("model_names", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("artifact_uri", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_experiments_project_id_projects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], name="fk_experiments_dataset_id_datasets", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], name="fk_experiments_dataset_version_id_dataset_versions", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_experiments"),
    )
    op.create_index("ix_experiments_project_id", "experiments", ["project_id"])
    op.create_index("ix_experiments_dataset_id", "experiments", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_experiments_dataset_id", table_name="experiments")
    op.drop_index("ix_experiments_project_id", table_name="experiments")
    op.drop_table("experiments")
