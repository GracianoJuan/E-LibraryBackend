from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class BookGenre(SQLModel, table=True):
    __tablename__ = "book_genre"
    __table_args__ = (
        UniqueConstraint("book_id", "genre_id", name="uq_book_genre_book_genre"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
