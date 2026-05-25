from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class RecommendationBase(SQLModel):
    user_id: int = Field(foreign_key="user.id")
    book_id: int = Field(foreign_key="book.id")
    score: float


class Recommendation(RecommendationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RecommendationRead(RecommendationBase):
    id: int
    created_at: datetime