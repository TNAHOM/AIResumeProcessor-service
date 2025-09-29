"""Add database indexes for performance optimization

Revision ID: 001_add_indexes
Revises: 
Create Date: 2024-12-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_indexes'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add indexes for improved query performance."""
    
    # Add individual column indexes
    op.create_index('ix_applications_job_post_id', 'applications', ['job_post_id'])
    op.create_index('ix_applications_status', 'applications', ['status'])
    op.create_index('ix_applications_created_at', 'applications', ['created_at'])
    op.create_index('ix_applications_updated_at', 'applications', ['updated_at'])
    
    # Add composite indexes for common query patterns
    op.create_index('ix_applications_status_created', 'applications', ['status', 'created_at'])
    op.create_index('ix_applications_job_post_status', 'applications', ['job_post_id', 'status'])
    op.create_index('ix_applications_email_created', 'applications', ['email', 'created_at'])
    op.create_index('ix_applications_status_updated', 'applications', ['status', 'updated_at'])


def downgrade() -> None:
    """Remove the added indexes."""
    
    # Remove composite indexes
    op.drop_index('ix_applications_status_updated', table_name='applications')
    op.drop_index('ix_applications_email_created', table_name='applications')
    op.drop_index('ix_applications_job_post_status', table_name='applications')
    op.drop_index('ix_applications_status_created', table_name='applications')
    
    # Remove individual column indexes
    op.drop_index('ix_applications_updated_at', table_name='applications')
    op.drop_index('ix_applications_created_at', table_name='applications')
    op.drop_index('ix_applications_status', table_name='applications')
    op.drop_index('ix_applications_job_post_id', table_name='applications')