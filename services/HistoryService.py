from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from datetime import datetime
from models.history import History
from models.book import Book


class HistoryService:
    """Service for managing reading history"""

    @staticmethod
    async def add_to_history(
        session: AsyncSession, user_id: int, book_id: int
    ) -> History:
        """Add a book to user's reading history"""
        # Check if book exists
        book = await session.get(Book, book_id)
        if not book:
            raise ValueError("Book not found")

        existing_statement = select(History).where(
            History.user_id == user_id,
            History.book_id == book_id,
        )
        existing_result = await session.execute(existing_statement)
        existing_history = existing_result.scalars().first()

        if existing_history:
            existing_history.read_at = datetime.utcnow()
            session.add(existing_history)
            await session.commit()
            await session.refresh(existing_history)

            from services.RecService import RecommendationService

            await RecommendationService.generate_recommendations_from_history(
                session, user_id, existing_history.id, top_n=10
            )
            return existing_history

        # Create reading history entry
        history = History(user_id=user_id, book_id=book_id)
        session.add(history)

        # Increment total_readers
        book.total_readers += 1
        session.add(book)

        await session.flush()
        await session.commit()
        await session.refresh(history)

        from services.RecService import RecommendationService

        await RecommendationService.generate_recommendations_from_history(
            session, user_id, history.id, top_n=10
        )
        return history

    @staticmethod
    async def delete_history(
        session: AsyncSession, user_id: int, book_id: int
    ) -> bool:
        history_statement = select(History).where(
            History.user_id == user_id,
            History.book_id == book_id,
        )
        history_result = await session.execute(history_statement)
        history = history_result.scalars().first()
        if history is None:
            return False

        book = await session.get(Book, book_id)
        if book and book.total_readers > 0:
            book.total_readers -= 1
            session.add(book)

        await session.delete(history)
        await session.commit()

        from services.RecService import RecommendationService

        await RecommendationService.rebuild_user_recommendations(session, user_id, top_n=10)
        return True

    @staticmethod
    async def get_user_history(
        session: AsyncSession, user_id: int, limit: int = 100
    ) -> list[History]:
        """Get a user's reading history"""
        statement = (
            select(History)
            .where(History.user_id == user_id)
            .order_by(History.read_at.desc())
            .limit(limit)
        )
        result = await session.execute(statement)   
        # if there are no history entries, return empty list
        if not result:
            return []
        return result.scalars().all()

    @staticmethod
    async def get_user_history_with_books(
        session: AsyncSession, user_id: int, limit: int = 100
    ) -> list[tuple[History, Book]]:
        """Get a user's reading history with book details"""
        histories = await HistoryService.get_user_history(session, user_id, limit)
        result = []
        for history in histories:
            book = await session.get(Book, history.book_id)
            if book:
                result.append((history, book))
        return result