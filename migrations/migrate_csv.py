import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from db import engine
from models.book_genre import BookGenre
from models.author import Author
from models.book import Book
from models.genre import Genre
from models.publisher import Publisher


async def migrate_csv_to_database():
    """Migrate books from CSV to PostgreSQL database"""
    base_path = Path(__file__).resolve().parents[1]

    # Read CSV file
    csv_candidates = [
        base_path / "sub" / "books_cleaned.csv"
    ]
    csv_path = next((path for path in csv_candidates if path.exists()), None)
    if csv_path is None:
        print(f"CSV file not found: {csv_candidates[0]}")
        return
    
    # Import pandas here
    try:
        import pandas as pd
    except ImportError:
        print("pandas is required. Install with: pip install pandas")
        return
    
    # Read CSV
    df = pd.read_csv(csv_path)

    def get_first_text(row, *keys: str) -> str:
        for key in keys:
            if key in row and pd.notna(row.get(key)):
                value = str(row.get(key)).strip()
                if value:
                    return value
        return ""
    
    # Get async session
    async with AsyncSession(engine) as session:
        statement = select(Book.isbn)
        result = await session.exec(statement)
        existing_isbns = {isbn for isbn in result.all() if isbn}

        author_cache: dict[str, int] = {}
        genre_cache: dict[str, int] = {}
        publisher_cache: dict[str, int] = {}

        async def get_or_create_lookup_id(model, value: str, cache: dict[str, int]) -> int:
            normalized_value = value.strip()
            if not normalized_value:
                raise ValueError(f"{model.__name__} value cannot be empty")

            cached_id = cache.get(normalized_value)
            if cached_id is not None:
                return cached_id

            statement = select(model).where(model.name == normalized_value)
            result = await session.exec(statement)
            existing_item = result.first()
            if existing_item is None:
                existing_item = model(name=normalized_value)
                session.add(existing_item)
                await session.flush()

            cache[normalized_value] = existing_item.id
            return existing_item.id

        # Process each row
        books_to_add = []
        all_isbns: list[str] = []
        for _, row in df.iterrows():
            title = str(row.get("title", "")).strip()
            isbn = str(row.get("isbn", "")).strip()
            author_name = str(row.get("authors", "")).strip()
            publisher_name = str(row.get("publisher", "")).strip()
            image_url = get_first_text(row, "cover_image_url", "cover_url_openlibrary", "image_url")
            description = str(row.get("description", "")).strip()
            publish_year = get_first_text(row, "published_year", "publish_year")
            raw_genres = get_first_text(row, "genre", "genres")
 
            if not isbn or isbn in existing_isbns:
                all_isbns.append(isbn)
                continue

            all_isbns.append(isbn)

            author_id = await get_or_create_lookup_id(Author, author_name, author_cache)
            publisher_id = await get_or_create_lookup_id(Publisher, publisher_name, publisher_cache)

            # Convert publish_year to int if available
            publish_year_int = None
            if publish_year:
                try:
                    publish_year_int = int(publish_year)
                except (ValueError, TypeError):
                    publish_year_int = None
    
            book = Book(
                title=title,
                isbn=isbn,
                author_id=author_id,
                publisher_id=publisher_id,
                image_url=image_url,
                description=description if description else None,
                publish_year=publish_year_int,
                content_file="content/lorem_ipsum_book",
                total_likes=0,
                total_readers=0,
            )
            books_to_add.append(book)
            existing_isbns.add(isbn)
        
        # Add all books to session and commit
        for book in books_to_add:
            session.add(book)
        
        await session.commit()

        # Reload persisted Book objects from the database so we can create
        # genre links for both newly inserted and already-existing books.
        statement = select(Book).where(Book.isbn.in_(all_isbns)) if all_isbns else select(Book)
        result = await session.exec(statement)
        persisted_books = result.all()
        book_lookup = {b.isbn: b for b in persisted_books}

        for _, row in df.iterrows():
            isbn = str(row.get("isbn", "")).strip()
            book = book_lookup.get(isbn)
            if not book:
                continue

            genre_text = get_first_text(row, "genre", "genres")
            if not genre_text:
                genre_text = "General"

            for genre_name in [part.strip() for part in genre_text.split(";") if part.strip()]:
                genre_id = await get_or_create_lookup_id(Genre, genre_name, genre_cache)
                session.add(BookGenre(book_id=book.id, genre_id=genre_id))

        await session.commit()
        print(f"Successfully migrated {len(books_to_add)} books from CSV to database")


if __name__ == "__main__":
    asyncio.run(migrate_csv_to_database())
