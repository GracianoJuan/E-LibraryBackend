from sqlmodel import SQLModel, Field, UniqueConstraint
from typing import Optional
from datetime import datetime


class HistoryBase(SQLModel):
    user_id: int = Field(foreign_key="user.id")
    book_id: int = Field(foreign_key="book.id")


class History(HistoryBase, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_history_user_book"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    read_at: datetime = Field(default_factory=datetime.utcnow)


class HistoryRead(HistoryBase):
    id: int
    read_at: datetime