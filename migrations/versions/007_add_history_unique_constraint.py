"""Add unique constraint to history table

Revision ID: 007_history_unique
Revises: 006_add_like_unique_constraint
Create Date: 2026-05-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "007_history_unique"
down_revision = "006_add_like_unique_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove duplicate history rows and prevent future duplicates."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, user_id, book_id, read_at
            FROM history
            ORDER BY user_id, book_id, read_at DESC, id DESC
            """
        )
    ).fetchall()

    seen_pairs: set[tuple[int, int]] = set()
    duplicate_ids: list[int] = []
    for row in rows:
        pair = (row.user_id, row.book_id)
        if pair in seen_pairs:
            duplicate_ids.append(row.id)
        else:
            seen_pairs.add(pair)

    for history_id in duplicate_ids:
        conn.execute(
            sa.text("DELETE FROM history WHERE id = :history_id"),
            {"history_id": history_id},
        )

    op.create_unique_constraint(
        "uq_history_user_book",
        "history",
        ["user_id", "book_id"],
    )


def downgrade() -> None:
    """Remove the history unique constraint."""
    op.drop_constraint(
        "uq_history_user_book",
        "history",
        type_="unique",
    )
