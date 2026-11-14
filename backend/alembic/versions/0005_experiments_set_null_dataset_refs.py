"""preserve experiments on dataset deletion

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12

Changes experiments.dataset_id / dataset_version_id from CASCADE+NOT NULL to
SET NULL+NULLABLE so deleting a dataset (or a dataset version) preserves the
experiment's metrics, configuration and evaluation history. Existing rows
keep their values; only the constraint behavior changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("experiments") as batch:
        batch.alter_column("dataset_id", existing_type=sa.Uuid(), nullable=True)
        batch.alter_column("dataset_version_id", existing_type=sa.Uuid(), nullable=True)
        batch.drop_constraint("fk_experiments_dataset_id_datasets", type_="foreignkey")
        batch.drop_constraint("fk_experiments_dataset_version_id_dataset_versions", type_="foreignkey")
        batch.create_foreign_key(
            "fk_experiments_dataset_id_datasets", "datasets", ["dataset_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_foreign_key(
            "fk_experiments_dataset_version_id_dataset_versions",
            "dataset_versions", ["dataset_version_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    # Reverting is only safe while no experiment has NULL dataset refs.
    with op.batch_alter_table("experiments") as batch:
        batch.drop_constraint("fk_experiments_dataset_id_datasets", type_="foreignkey")
        batch.drop_constraint("fk_experiments_dataset_version_id_dataset_versions", type_="foreignkey")
        batch.create_foreign_key(
            "fk_experiments_dataset_id_datasets", "datasets", ["dataset_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_foreign_key(
            "fk_experiments_dataset_version_id_dataset_versions",
            "dataset_versions", ["dataset_version_id"], ["id"], ondelete="CASCADE",
        )
        batch.alter_column("dataset_id", existing_type=sa.Uuid(), nullable=False)
        batch.alter_column("dataset_version_id", existing_type=sa.Uuid(), nullable=False)
