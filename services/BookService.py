from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from models.book import Book
from models.book_genre import BookGenre
from models.genre import Genre
from models.like import Like
from models.user import User
from models.book import BookCreate
from models.author import Author
from models.category import Category
from models.publisher import Publisher


class BookService:
    """Service for handling book operations"""

    @staticmethod
    async def get_book_by_id(session: AsyncSession, book_id: int) -> Book | None:
        """Get a book by ID"""
        return await session.get(Book, book_id)

    @staticmethod
    async def get_most_liked_books(session: AsyncSession, limit: int = 10) -> list[Book]:
        """Get the most liked books"""
        statement = select(Book).order_by(Book.total_likes.desc()).limit(limit)
        result = await session.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def like_book(session: AsyncSession, book_id: int, user_id: int) -> Book:
        """Create a like for the user and increment total_likes when needed."""
        book = await session.get(Book, book_id)
        if not book:
            raise ValueError("Book not found")

        statement = select(Like).where(Like.book_id == book_id, Like.user_id == user_id)
        result = await session.execute(statement)
        existing_like = result.scalars().first()

        if existing_like is None:
            session.add(Like(book_id=book_id, user_id=user_id))
            book.total_likes += 1
        session.add(book)
        await session.commit()
        await session.refresh(book)
        return book

    @staticmethod
    async def is_book_liked(session: AsyncSession, book_id: int, user_id: int) -> bool:
        statement = select(Like).where(Like.book_id == book_id, Like.user_id == user_id)
        result = await session.execute(statement)
        return result.scalars().first() is not None

    @staticmethod
    async def get_user_likes(
        session: AsyncSession, user_id: int, limit: int = 100
    ) -> list[Like]:
        """Get a user's liked books ordered by latest like action."""
        statement = (
            select(Like)
            .where(Like.user_id == user_id)
            .order_by(Like.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def unlike_book(session: AsyncSession, book_id: int, user_id: int) -> Book:
        """Remove a like for the user and decrement total_likes when needed."""
        book = await session.get(Book, book_id)
        if not book:
            raise ValueError("Book not found")

        statement = select(Like).where(Like.book_id == book_id, Like.user_id == user_id)
        result = await session.execute(statement)
        existing_like = result.scalars().first()

        if existing_like is not None:
            await session.delete(existing_like)
            if book.total_likes > 0:
                book.total_likes -= 1
        session.add(book)
        await session.commit()
        await session.refresh(book)
        return book

    @staticmethod
    async def create_book(session: AsyncSession, book_create: BookCreate) -> Book:
        """Create a new book record"""
        book_data = book_create.dict(exclude={"genre_ids"})
        genre_ids = list(dict.fromkeys(book_create.genre_ids))
        book = Book(**book_data)
        session.add(book)
        await session.commit()
        await session.refresh(book)

        for genre_id in genre_ids:
            genre = await session.get(Genre, genre_id)
            if genre:
                session.add(BookGenre(book_id=book.id, genre_id=genre_id))

        await session.commit()
        return book

    @staticmethod
    async def _get_book_genres(session: AsyncSession, book_id: int) -> list[str]:
        statement = (
            select(Genre.name)
            .join(BookGenre, BookGenre.genre_id == Genre.id)
            .where(BookGenre.book_id == book_id)
            .order_by(Genre.name)
        )
        result = await session.execute(statement)
        return [name for name in result.scalars().all() if name]

    @staticmethod
    async def get_available_books(session: AsyncSession, limit: int = 50) -> list[Book]:
        """Return available books (no particular ordering)."""
        statement = select(Book).limit(limit)
        result = await session.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def get_most_liked_books_with_details(
        session: AsyncSession, limit: int = 15
    ) -> list[dict]:
        """Get most liked books with author, genres, and publisher names."""
        # Fetch books ordered by likes
        statement = select(Book).order_by(Book.total_likes.desc()).limit(limit)
        result = await session.execute(statement)
        books = result.scalars().all()

        # Build response with related data
        response = []
        for book in books:
            author = await session.get(Author, book.author_id)
            publisher = await session.get(Publisher, book.publisher_id)
            genres = await BookService._get_book_genres(session, book.id)

            response.append({
                "id": book.id,
                "title": book.title,
                "isbn": book.isbn,
                "image_url": book.image_url,
                "description": book.description,
                "content_file": book.content_file,
                "total_likes": book.total_likes,
                "total_readers": book.total_readers,
                "author": author.name if author else "Unknown",
                "genres": genres,
                "category": genres[0] if genres else "Unknown",
                "publisher": publisher.name if publisher else "Unknown",
            })
        return response 

    @staticmethod
    async def get_most_read_books_with_details(
        session: AsyncSession, limit: int = 15
    ) -> list[dict]:
        """Get most read books with author, genres, and publisher names."""
        # Fetch books ordered by readers
        statement = select(Book).order_by(Book.total_readers.desc()).limit(limit)
        result = await session.execute(statement)
        books = result.scalars().all()

        # Build response with related data
        response = []
        for book in books:
            author = await session.get(Author, book.author_id)
            publisher = await session.get(Publisher, book.publisher_id)
            genres = await BookService._get_book_genres(session, book.id)

            response.append({
                "id": book.id,
                "title": book.title,
                "isbn": book.isbn,
                "image_url": book.image_url,
                "description": book.description,
                "content_file": book.content_file,
                "total_likes": book.total_likes,
                "total_readers": book.total_readers,
                "author": author.name if author else "Unknown",
                "genres": genres,
                "category": genres[0] if genres else "Unknown",
                "publisher": publisher.name if publisher else "Unknown",
            })
        return response

    @staticmethod
    async def get_book_by_id_with_details(book_id: int, session: AsyncSession) -> dict | None:
        """Get a book by ID with author, genres, and publisher details."""
        book = await session.get(Book, book_id)
        if not book:
            return None

        author = await session.get(Author, book.author_id)
        publisher = await session.get(Publisher, book.publisher_id)
        genres = await BookService._get_book_genres(session, book.id)

        return {
            "id": book.id,
            "title": book.title,
            "isbn": book.isbn,
            "image_url": book.image_url,
            "description": book.description,
            "content_file": book.content_file,
            "total_likes": book.total_likes,
            "total_readers": book.total_readers,
            "author": author.name if author else "Unknown",
            "genres": genres,
            "category": genres[0] if genres else "Unknown",
            "publisher": publisher.name if publisher else "Unknown",
        }

    @staticmethod
    async def get_book_genres(session: AsyncSession) -> list[str]:
        """Return distinct genre names used by the catalog."""
        statement = select(Genre.name).order_by(Genre.name)
        result = await session.execute(statement)
        return [name for name in result.scalars().all() if name]

    @staticmethod
    async def get_book_categories(session: AsyncSession) -> list[str]:
        """Backward-compatible alias for genre names."""
        return await BookService.get_book_genres(session)

    @staticmethod
    async def get_explore_books_with_details(
        session: AsyncSession,
        limit: int = 12,
        genre: str | None = None,
        category: str | None = None,
        search_field: str | None = None,
        query: str | None = None,
    ) -> list[dict]:
        """Return a small, filtered book list for the Explore page."""
        statement = (
            select(Book, Author, Publisher)
            .join(Author, Book.author_id == Author.id)
            .join(Publisher, Book.publisher_id == Publisher.id)
        )

        normalized_genre = (genre or category or "").strip()
        if normalized_genre and normalized_genre.lower() != "all":
            statement = statement.join(BookGenre, BookGenre.book_id == Book.id).join(Genre, BookGenre.genre_id == Genre.id)
            statement = statement.where(Genre.name == normalized_genre)

        normalized_query = (query or "").strip()
        normalized_field = (search_field or "author").strip().lower()
        if normalized_query:
            pattern = f"%{normalized_query}%"
            if normalized_field == "publisher":
                statement = statement.where(Publisher.name.ilike(pattern))
            elif normalized_field == "title":
                statement = statement.where(Book.title.ilike(pattern))
            else:
                statement = statement.where(Author.name.ilike(pattern))

        statement = statement.order_by(Book.total_likes.desc(), Book.id.desc()).limit(limit)
        result = await session.execute(statement)

        books = []
        for book, author, publisher in result.all():
            genres = await BookService._get_book_genres(session, book.id)
            books.append({
                "id": book.id,
                "title": book.title,
                "isbn": book.isbn,
                "image_url": book.image_url,
                "description": book.description,
                "content_file": book.content_file,
                "total_likes": book.total_likes,
                "total_readers": book.total_readers,
                "author": author.name if author else "Unknown",
                "genres": genres,
                "category": genres[0] if genres else "Unknown",
                "publisher": publisher.name if publisher else "Unknown",
            })

        return books
    
    

