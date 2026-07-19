"""initial schema: test_run, system_metrics, system_processes

Revision ID: 20260716_0001
Revises:
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260716_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("total_alerts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_test_run_id", "test_run", ["id"])

    op.create_table(
        "system_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "test_run_id",
            sa.Integer(),
            sa.ForeignKey("test_run.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("cpu_usage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ram_usage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("disk_usage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("disk_read_bps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("disk_write_bps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("network_in_bps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("network_out_bps", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_system_metrics_id", "system_metrics", ["id"])
    op.create_index("ix_system_metrics_test_run_id", "system_metrics", ["test_run_id"])
    op.create_index("ix_system_metrics_timestamp", "system_metrics", ["timestamp"])
    op.create_index(
        "ix_system_metrics_test_run_timestamp",
        "system_metrics",
        ["test_run_id", "timestamp"],
    )

    op.create_table(
        "system_processes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "test_run_id",
            sa.Integer(),
            sa.ForeignKey("test_run.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="unknown"),
        sa.Column("cpu_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("memory_percent", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_system_processes_id", "system_processes", ["id"])
    op.create_index("ix_system_processes_test_run_id", "system_processes", ["test_run_id"])
    op.create_index("ix_system_processes_timestamp", "system_processes", ["timestamp"])
    op.create_index("ix_system_processes_name", "system_processes", ["name"])
    op.create_index(
        "ix_system_processes_test_run_timestamp",
        "system_processes",
        ["test_run_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_system_processes_test_run_timestamp", table_name="system_processes")
    op.drop_index("ix_system_processes_name", table_name="system_processes")
    op.drop_index("ix_system_processes_timestamp", table_name="system_processes")
    op.drop_index("ix_system_processes_test_run_id", table_name="system_processes")
    op.drop_index("ix_system_processes_id", table_name="system_processes")
    op.drop_table("system_processes")

    op.drop_index("ix_system_metrics_test_run_timestamp", table_name="system_metrics")
    op.drop_index("ix_system_metrics_timestamp", table_name="system_metrics")
    op.drop_index("ix_system_metrics_test_run_id", table_name="system_metrics")
    op.drop_index("ix_system_metrics_id", table_name="system_metrics")
    op.drop_table("system_metrics")

    op.drop_index("ix_test_run_id", table_name="test_run")
    op.drop_table("test_run")