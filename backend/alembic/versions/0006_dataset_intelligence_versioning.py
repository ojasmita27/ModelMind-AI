"""dataset versioning lineage + experiment preprocessing config

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12

Adds to dataset_versions: source ('upload'|'cleaned'), derived_from_version_id
(self-FK, SET NULL), transformation_log (JSON). Adds to experiments:
preprocessing_config (JSON, nullable). All additive; existing rows keep
defaults ('upload', NULL).
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataset_versions", sa.Column("source", sa.String(length=20), nullable=False, server_default="upload"))
    op.add_column("dataset_versions", sa.Column("derived_from_version_id", sa.Uuid(), nullable=True))
    op.add_column("dataset_versions", sa.Column("transformation_log", sa.JSON(), nullable=True))
    with op.batch_alter_table("dataset_versions") as batch:
        batch.create_foreign_key(
            "fk_dataset_versions_derived_from",
            "dataset_versions", ["derived_from_version_id"], ["id"], ondelete="SET NULL",
        )
    op.add_column("experiments", sa.Column("preprocessing_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "preprocessing_config")
    with op.batch_alter_table("dataset_versions") as batch:
        batch.drop_constraint("fk_dataset_versions_derived_from", type_="foreignkey")
    op.drop_column("dataset_versions", "transformation_log")
    op.drop_column("dataset_versions", "derived_from_version_id")
    op.drop_column("dataset_versions", "source")
