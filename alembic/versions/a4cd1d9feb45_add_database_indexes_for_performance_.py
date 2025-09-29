"""Add database indexes for performance optimization

Revision ID: a4cd1d9feb45
Revises: 
Create Date: 2025-09-29 20:52:24.918835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a4cd1d9feb45'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes to applications table."""
    
    # Create the applications table if it doesn't exist (initial migration)
    op.create_table('applications',
        sa.Column('id', sa.String(36), nullable=False, comment='UUID stored as string'),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('job_post_id', sa.String(36), nullable=True),
        sa.Column('original_filename', sa.String(), nullable=False),
        sa.Column('s3_path', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', name='applicationstatus'), nullable=False),
        sa.Column('seniority_level', sa.Enum('INTERN', 'JUNIOR', 'MID', 'SENIOR', name='senioritylevel'), nullable=True),
        sa.Column('analysis', sa.JSON(), nullable=True),
        sa.Column('failed_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extracted_data', sa.JSON(), nullable=True),
        sa.Column('embedded_value', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add performance indexes
    op.create_index('ix_applications_email', 'applications', ['email'])
    op.create_index('ix_applications_job_post_id', 'applications', ['job_post_id'])
    op.create_index('ix_applications_status', 'applications', ['status'])
    op.create_index('ix_applications_created_at', 'applications', ['created_at'])
    op.create_index('ix_applications_s3_path', 'applications', ['s3_path'], unique=True)
    op.create_index('ix_applications_id', 'applications', ['id'])


def downgrade() -> None:
    """Remove performance indexes from applications table."""
    
    # Drop indexes
    op.drop_index('ix_applications_created_at', table_name='applications')
    op.drop_index('ix_applications_status', table_name='applications')
    op.drop_index('ix_applications_job_post_id', table_name='applications')
    op.drop_index('ix_applications_email', table_name='applications')
    op.drop_index('ix_applications_s3_path', table_name='applications')
    op.drop_index('ix_applications_id', table_name='applications')
    
    # Drop table
    op.drop_table('applications')
