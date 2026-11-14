"""add datasets and dataset versions

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25

Portable: sa.func.now() renders now() on PostgreSQL and CURRENT_TIMESTAMP on SQLite.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_datasets_project_id_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_datasets"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("job_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("job_error", sa.Text(), nullable=True),
        sa.Column("job_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], name="fk_dataset_versions_dataset_id_datasets", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_versions"),
        sa.UniqueConstraint("sha256_checksum", name="uq_dataset_versions_sha256_checksum"),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_dataset_versions_dataset_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_index("ix_datasets_project_id", table_name="datasets")
    op.drop_table("datasets")
