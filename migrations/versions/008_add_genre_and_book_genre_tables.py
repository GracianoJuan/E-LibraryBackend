"""Add genre and book_genre tables

Revision ID: 008_genre_bookgenre
Revises: 007_history_unique
Create Date: 2026-05-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "008_genre_bookgenre"
down_revision = "007_history_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genre",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_genre_name"), "genre", ["name"], unique=True)

    op.create_table(
        "book_genre",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("genre_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.ForeignKeyConstraint(["genre_id"], ["genre.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "genre_id", name="uq_book_genre_book_genre"),
    )
    op.create_index(op.f("ix_book_genre_book_id"), "book_genre", ["book_id"], unique=False)
    op.create_index(op.f("ix_book_genre_genre_id"), "book_genre", ["genre_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_book_genre_genre_id"), table_name="book_genre")
    op.drop_index(op.f("ix_book_genre_book_id"), table_name="book_genre")
    op.drop_table("book_genre")

    op.drop_index(op.f("ix_genre_name"), table_name="genre")
    op.drop_table("genre")