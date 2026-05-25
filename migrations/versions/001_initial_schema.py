"""Initial schema - Create all tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-05-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create User table
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=False)

    # Create Author table
    op.create_table(
        'author',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create Publisher table
    op.create_table(
        'publisher',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create Book table with all fields
    op.create_table(
        'book',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('publisher_id', sa.Integer(), nullable=True),
        sa.Column('isbn', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('publish_year', sa.Integer(), nullable=True),
        sa.Column('content_file', sa.String(), nullable=True),
        sa.Column('total_likes', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_readers', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['author_id'], ['author.id']),
        sa.ForeignKeyConstraint(['publisher_id'], ['publisher.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_book_isbn'), 'book', ['isbn'], unique=True)

    # Create History table
    op.create_table(
        'history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_history_user_id'), 'history', ['user_id'], unique=False)
    op.create_index(op.f('ix_history_book_id'), 'history', ['book_id'], unique=False)

    # Create Recommendation table
    op.create_table(
        'recommendation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recommendation_user_id'), 'recommendation', ['user_id'], unique=False)
    op.create_index(op.f('ix_recommendation_book_id'), 'recommendation', ['book_id'], unique=False)

    # Create book_like table
    op.create_table(
        'book_like',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'book_id', name='uq_book_like_user_book')
    )
    op.create_index(op.f('ix_book_like_user_id'), 'book_like', ['user_id'], unique=False)
    op.create_index(op.f('ix_book_like_book_id'), 'book_like', ['book_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_book_like_book_id'), table_name='book_like')
    op.drop_index(op.f('ix_book_like_user_id'), table_name='book_like')
    op.drop_table('book_like')
    op.drop_index(op.f('ix_recommendation_book_id'), table_name='recommendation')
    op.drop_index(op.f('ix_recommendation_user_id'), table_name='recommendation')
    op.drop_table('recommendation')
    op.drop_index(op.f('ix_history_book_id'), table_name='history')
    op.drop_index(op.f('ix_history_user_id'), table_name='history')
    op.drop_table('history')
    op.drop_index(op.f('ix_book_isbn'), table_name='book')
    op.drop_table('book')
    op.drop_table('publisher')
    op.drop_table('author')
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
