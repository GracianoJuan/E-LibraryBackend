from sqlmodel import SQLModel, Field
from typing import Optional


class BookBase(SQLModel):
    title: str
    isbn: str
    image_url: str
    author_id: int = Field(foreign_key="author.id")
    publisher_id: int = Field(foreign_key="publisher.id")


class Book(BookBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    description: Optional[str] = Field(default=None)
    publish_year: Optional[int] = Field(default=None)
    content_file: Optional[str] = Field(default=None)
    total_likes: int = Field(default=0)
    total_readers: int = Field(default=0)


class BookRead(BookBase):
    id: int
    description: Optional[str]
    publish_year: Optional[int]
    content_file: Optional[str]
    total_likes: int
    total_readers: int
    genres: list[str] = Field(default_factory=list)


class BookCreate(BookBase):
    genre_ids: list[int] = Field(default_factory=list)