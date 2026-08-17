"""Add report task prompt controls."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("report_tasks")}
    if "prompt_mode" not in columns:
        op.add_column(
            "report_tasks",
            sa.Column(
                "prompt_mode",
                sa.String(length=20),
                nullable=False,
                server_default="adaptive",
            ),
        )
    if "report_prompt" not in columns:
        op.add_column(
            "report_tasks",
            sa.Column("report_prompt", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("report_tasks")}
    if "report_prompt" in columns:
        op.drop_column("report_tasks", "report_prompt")
    if "prompt_mode" in columns:
        op.drop_column("report_tasks", "prompt_mode")
