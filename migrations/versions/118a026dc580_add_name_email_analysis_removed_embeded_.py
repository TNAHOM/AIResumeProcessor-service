"""Add name, email, analysis (applications only)

Revision ID: 118a026dc580
Revises: 45e62b2520a9
Create Date: 2025-09-28 22:39:52.858182

This migration has been sanitized to avoid touching external tables
like 'users' and 'job_posts'. It now only changes the 'applications'
table owned by this service.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "118a026dc580"
down_revision: Union[str, Sequence[str], None] = "45e62b2520a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (applications only)."""
    # Add new columns on applications
    op.add_column("applications", sa.Column("name", sa.String(), nullable=False))
    op.add_column("applications", sa.Column("email", sa.String(), nullable=False))
    op.add_column(
        "applications", sa.Column("job_post_id", sa.String(length=36), nullable=True)
    )
    op.add_column("applications", sa.Column("analysis", sa.JSON(), nullable=True))

    # Remove legacy embedded_* columns (embedded_value stays)
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("embedded_requirements")
        batch_op.drop_column("embedded_responsibility")
        batch_op.drop_column("embedded_description")


def downgrade() -> None:
    """Downgrade schema (applications only)."""
    # Re-add legacy embedded_* columns
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(
            sa.Column("embedded_description", Vector(dim=3072), nullable=True)
        )
        batch_op.add_column(
            sa.Column("embedded_responsibility", Vector(dim=3072), nullable=True)
        )
        batch_op.add_column(
            sa.Column("embedded_requirements", Vector(dim=3072), nullable=True)
        )

    # Remove newly added columns
    op.drop_column("applications", "analysis")
    op.drop_column("applications", "job_post_id")
    op.drop_column("applications", "email")
    op.drop_column("applications", "name")
