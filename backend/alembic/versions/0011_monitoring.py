"""monitoring runs + label records

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitoring_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("deployment_id", sa.Uuid(), sa.ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reference_sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_table(
        "label_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("deployment_id", sa.Uuid(), sa.ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("label", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("deployment_id", "request_id", name="uq_label_request"),
    )


def downgrade() -> None:
    op.drop_table("label_records")
    op.drop_table("monitoring_runs")
