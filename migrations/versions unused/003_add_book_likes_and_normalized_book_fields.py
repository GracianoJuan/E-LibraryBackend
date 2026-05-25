"""This migration has been consolidated into 001_initial_schema - kept as placeholder

Revision ID: 003_book_likes_and_book_fields
Revises: 002_normalize_book_table
Create Date: 2026-05-11 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '003_book_likes_and_book_fields'
down_revision = '002_normalize_book_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass