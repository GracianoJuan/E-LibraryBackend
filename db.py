from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel import SQLModel
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:juan@localhost:5432/elibrary_db",
)

# Convert postgresql+psycopg to postgresql+asyncpg for async
DATABASE_URL_ASYNC = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://")

engine = create_async_engine(
    DATABASE_URL_ASYNC,
    echo=True,
    future=True,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session