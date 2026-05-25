# Service layer for handling book recommendations
from pathlib import Path

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, delete, func

from models.history import History
from models.recommendation import Recommendation
from models.book import Book

import sys

# Add cbf to path
cbf_path = Path(__file__).parent.parent / "cbf"
sys.path.insert(0, str(cbf_path))

from cbf import load_all_cbf


class RecommendationService:
    """Service for managing book recommendations"""

    _cbf_model = None

    @classmethod
    async def initialize_cbf(cls):
        """Initialize the CBF model (call once on startup)"""
        if cls._cbf_model is None:
            try:
                cbf_dir = Path(__file__).parent.parent / "cbf"
                cls._cbf_model = load_all_cbf(str(cbf_dir / "books_processed.csv"))["tfidf"]
            except Exception as e:
                print(f"Warning: Could not initialize CBF model: {e}")
                cls._cbf_model = None

    @staticmethod
    async def _resolve_book_id_by_title(session: AsyncSession, title: str) -> int | None:
        normalized_title = title.strip().lower()
        if not normalized_title:
            return None

        statement = select(Book.id).where(func.lower(Book.title) == normalized_title)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def _resolve_book_by_id(session: AsyncSession, book_id: int) -> Book | None:
        return await session.get(Book, book_id)

    @staticmethod
    async def _get_user_read_book_ids(session: AsyncSession, user_id: int) -> set[int]:
        statement = select(History.book_id).where(History.user_id == user_id)
        result = await session.execute(statement)
        return set(result.scalars().all())

    @staticmethod
    async def _upsert_recommendation(
        session: AsyncSession,
        user_id: int,
        book_id: int,
        score: float,
    ) -> Recommendation:
        statement = select(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.book_id == book_id,
        )
        result = await session.execute(statement)
        existing = result.scalars().first()

        if existing is not None:
            if score > existing.score:
                existing.score = score
            session.add(existing)
            return existing

        recommendation = Recommendation(user_id=user_id, book_id=book_id, score=score)
        session.add(recommendation)
        return recommendation

    @staticmethod
    async def _prune_read_recommendations(session: AsyncSession, user_id: int) -> None:
        read_book_ids = await RecommendationService._get_user_read_book_ids(session, user_id)
        if not read_book_ids:
            return

        statement = delete(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.book_id.in_(read_book_ids),
        )
        await session.execute(statement)

    @classmethod
    async def _generate_recommendations_from_title(
        cls,
        session: AsyncSession,
        user_id: int,
        source_title: str,
        top_n: int = 10,
    ) -> list[Recommendation]:
        recommendations: list[Recommendation] = []

        if cls._cbf_model is None:
            await cls.initialize_cbf()

        if cls._cbf_model is None:
            return recommendations

        try:
            cbf_recs = cls._cbf_model.get_recommendations(source_title, top_n=top_n)
            read_book_ids = await cls._get_user_read_book_ids(session, user_id)

            for _, row in cbf_recs.iterrows():
                rec_title = str(row.get("title", "")).strip()
                rec_book_id = await cls._resolve_book_id_by_title(session, rec_title)
                if rec_book_id is None:
                    continue

                if rec_book_id in read_book_ids:
                    continue

                score = float(row["similarity_score"])
                rec = await cls._upsert_recommendation(session, user_id, rec_book_id, score)
                recommendations.append(rec)

            await session.commit()
        except Exception as e:
            print(f"Warning: Error generating CBF recommendations: {e}")

        return recommendations

    @classmethod
    async def get_recommendations_for_book(
        cls,
        session: AsyncSession,
        book_id: int,
        limit: int = 10,
        threshold: float = 0.25,
        min_results: int = 5,
    ) -> list[int]:
        if cls._cbf_model is None:
            await cls.initialize_cbf()

        if cls._cbf_model is None:
            return []

        source_book = await cls._resolve_book_by_id(session, book_id)
        if not source_book:
            return []

        max_candidates = max(limit * 2, 10)
        try:
            cbf_recs = cls._cbf_model.get_recommendations(source_book.title, top_n=max_candidates)
        except Exception as exc:
            print(f"Warning: Error generating book recommendations: {exc}")
            return []

        recommended_ids: list[int] = []
        fallback_ids: list[int] = []
        seen_ids: set[int] = {source_book.id}

        for _, row in cbf_recs.iterrows():
            rec_title = str(row.get("title", "")).strip()
            rec_book_id = await cls._resolve_book_id_by_title(session, rec_title)
            if rec_book_id is None or rec_book_id in seen_ids:
                continue

            seen_ids.add(rec_book_id)
            fallback_ids.append(rec_book_id)

            score = float(row.get("similarity_score", 0.0))
            if score >= threshold:
                recommended_ids.append(rec_book_id)

            if len(recommended_ids) >= limit:
                break

        if len(recommended_ids) < min_results:
            for rec_book_id in fallback_ids:
                if rec_book_id in recommended_ids:
                    continue
                recommended_ids.append(rec_book_id)
                if len(recommended_ids) >= min_results:
                    break

        return recommended_ids[:limit]

    @staticmethod
    async def generate_recommendations(
        session: AsyncSession, user_id: int, book_id: int, top_n: int = 10
    ) -> list[Recommendation]:
        """
        Generate recommendations for a user based on a book they just read.
        Uses CBF algorithm to find similar books.
        """
        # Get the book
        book = await session.get(Book, book_id)
        if not book:
            raise ValueError("Book not found")
        return await RecommendationService._generate_recommendations_from_title(
            session,
            user_id,
            book.title,
            top_n=top_n,
        )

    @classmethod
    async def generate_recommendations_from_history(
        cls,
        session: AsyncSession,
        user_id: int,
        history_id: int,
        top_n: int = 10,
    ) -> list[Recommendation]:
        history = await session.get(History, history_id)
        if not history:
            raise ValueError("History not found")

        book = await session.get(Book, history.book_id)
        if not book:
            raise ValueError("Book not found")

        return await cls._generate_recommendations_from_title(
            session,
            user_id,
            book.title,
            top_n=top_n,
        )

    @classmethod
    async def rebuild_user_recommendations(
        cls,
        session: AsyncSession,
        user_id: int,
        top_n: int = 5,
    ) -> list[Recommendation]:
        statement = delete(Recommendation).where(Recommendation.user_id == user_id)
        await session.execute(statement)

        histories_statement = (
            select(History)
            .where(History.user_id == user_id)
            .order_by(History.read_at.desc())
        )
        histories_result = await session.execute(histories_statement)
        histories = histories_result.scalars().all()

        rebuilt: list[Recommendation] = []
        for history in histories:
            rebuilt.extend(
                await cls.generate_recommendations_from_history(
                    session,
                    user_id,
                    history.id,
                    top_n=top_n,
                )
            )

        await cls._prune_read_recommendations(session, user_id)
        await session.commit()
        return rebuilt

    @staticmethod
    async def get_user_recommendations(
        session: AsyncSession, user_id: int, limit: int = 15
    ) -> list[tuple[Recommendation, Book]]:
        """Get recommendations for a user with their book details, sorted by similarity score"""
        await RecommendationService._prune_read_recommendations(session, user_id)
        await session.commit()

        # Get recommendations ordered by score (highest first), then by creation date
        statement = (
            select(Recommendation)
            .where(Recommendation.user_id == user_id)
            .order_by(Recommendation.score.desc(), Recommendation.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(statement)
        recommendations = result.scalars().all()
        
        # if there are no recommendations, return empty list
        if not recommendations:
            return []

        # Fetch book details
        result_with_books = []
        for rec in recommendations:
            book = await session.get(Book, rec.book_id)
            if book:
                result_with_books.append((rec, book))

        return result_with_books

    @staticmethod
    async def clear_user_recommendations(
        session: AsyncSession, user_id: int
    ) -> int:
        """Clear all recommendations for a user"""
        statement = delete(Recommendation).where(Recommendation.user_id == user_id)
        result = await session.execute(statement)
        await session.commit()
        return result.rowcount