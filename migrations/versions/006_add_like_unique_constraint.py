"""Add unique constraint to book_like table

Revision ID: 006_add_like_unique_constraint
Revises: 005_remove_content_json
Create Date: 2026-05-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_add_like_unique_constraint'
down_revision = '005_remove_content_json'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique constraint to prevent duplicate likes from the same user for the same book
    op.create_unique_constraint(
        'uq_user_book_like',
        'book_like',
        ['user_id', 'book_id']
    )


def downgrade() -> None:
    # Remove the unique constraint
    op.drop_constraint(
        'uq_user_book_like',
        'book_like',
        type_='unique'
    )
