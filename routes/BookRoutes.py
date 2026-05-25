from pathlib import Path
import mimetypes

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from db import get_session
from models.book import BookRead, BookCreate, Book
from models.user import User
from services.BookService import BookService
from services.HistoryService import HistoryService
from services.RecService import RecommendationService
from middlewares.auth import get_current_user


router = APIRouter(prefix="/books", tags=["books"])


class BookLikeResponse(BaseModel):
    id: int
    total_likes: int


class BookLikeStatusResponse(BaseModel):
    id: int
    is_liked: bool


class BookRecommendationQuery(BaseModel):
    limit: int = 10
    threshold: float = 0.25


class BookDetailResponse(BaseModel):
    id: int
    title: str
    author: str
    category: str | None = None
    genres: list[str] = Field(default_factory=list)
    publisher: str
    isbn: str
    image_url: str | None = None
    description: str | None = None
    content_file: str | None = None
    total_likes: int
    total_readers: int


class BookContentResponse(BaseModel):
    id: int
    page_numbers: list[int] = Field(default_factory=list)


@router.get("/genres", response_model=list[str])
async def get_book_genres(session: AsyncSession = Depends(get_session)):
    """Get all catalog genres for the explore filters."""
    return await BookService.get_book_genres(session)


@router.get("/categories", response_model=list[str])
async def get_book_categories(session: AsyncSession = Depends(get_session)):
    """Backward-compatible alias for genre filters."""
    return await BookService.get_book_genres(session)


@router.get("/explore", response_model=list[BookDetailResponse])
async def explore_books(
    limit: int = 12,
    genre: str | None = None,
    category: str | None = None,
    search_field: str | None = None,
    query: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Return a small filtered set of books for the Explore page."""
    if limit > 50:
        limit = 50
    return await BookService.get_explore_books_with_details(
        session,
        limit=limit,
        genre=genre,
        category=category,
        search_field=search_field,
        query=query,
    )


BACKEND_ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _resolve_book_content_directory(book: Book) -> Path:
    if not book.content_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book has no content file",
        )

    candidate = (BACKEND_ROOT / book.content_file).resolve()
    try:
        candidate.relative_to(BACKEND_ROOT)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid content file path",
        ) from exc

    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book content directory not found",
        )

    return candidate


def _list_page_numbers(content_directory: Path) -> list[int]:
    pages: list[int] = []
    for item in content_directory.iterdir():
        if not item.is_file() or item.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        try:
            page_number = int(item.stem)
        except ValueError:
            continue

        pages.append(page_number)

    return sorted(set(pages))


def _resolve_page_file(content_directory: Path, page_number: int) -> Path | None:
    for extension in IMAGE_EXTENSIONS:
        candidate = content_directory / f"{page_number}{extension}"
        if candidate.exists() and candidate.is_file():
            return candidate

    for item in content_directory.iterdir():
        if item.is_file() and item.stem == str(page_number):
            return item

    return None


@router.get("/most-liked", response_model=list[BookDetailResponse])
async def get_most_liked_books(
    limit: int = 15, session: AsyncSession = Depends(get_session)
):
    """Get most liked books (10-15 books)"""
    if limit > 100:
        limit = 100
    books = await BookService.get_most_liked_books_with_details(session, limit)
    return books


@router.get("/most-read", response_model=list[BookDetailResponse])
async def get_most_read_books(
    limit: int = 15, session: AsyncSession = Depends(get_session)
):
    """Get most read books (10-15 books)"""
    if limit > 100:
        limit = 100
    books = await BookService.get_most_read_books_with_details(session, limit)
    return books


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(book_id: int, session: AsyncSession = Depends(get_session)):
    """Get a book by ID with details"""
    book = await BookService.get_book_by_id_with_details(book_id, session)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


@router.get("/{book_id}/recommendations", response_model=list[BookDetailResponse])
async def get_book_recommendations(
    book_id: int,
    limit: int = 10,
    threshold: float = 0.25,
    session: AsyncSession = Depends(get_session),
):
    if limit < 1:
        limit = 1
    if limit > 10:
        limit = 10

    if threshold < 0:
        threshold = 0
    if threshold > 1:
        threshold = 1

    related_book_ids = await RecommendationService.get_recommendations_for_book(
        session,
        book_id,
        limit=limit,
        threshold=threshold,
        min_results=5,
    )

    result: list[BookDetailResponse] = []
    for related_book_id in related_book_ids:
        book = await BookService.get_book_by_id_with_details(related_book_id, session)
        if book:
            result.append(book)

    return result


@router.get("/{book_id}/content", response_model=BookContentResponse)
async def get_book_content(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    book = await BookService.get_book_by_id(session, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    content_directory = _resolve_book_content_directory(book)
    page_numbers = _list_page_numbers(content_directory)
    if not page_numbers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No page images found for this book",
        )

    return BookContentResponse(id=book.id, page_numbers=page_numbers)


@router.get("/{book_id}/content/{page_number}")
async def get_book_content_page(
    book_id: int,
    page_number: int,
    session: AsyncSession = Depends(get_session),
):
    book = await BookService.get_book_by_id(session, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    content_directory = _resolve_book_content_directory(book)
    page_file = _resolve_page_file(content_directory, page_number)
    if not page_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page image not found")

    media_type, _ = mimetypes.guess_type(page_file.name)
    return FileResponse(
        page_file,
        media_type=media_type or "image/jpeg",
        filename=page_file.name,
    )


@router.get("/{book_id}/pdf")
async def get_book_pdf(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Serve the PDF file configured in content_file for a given book."""
    book = await BookService.get_book_by_id(session, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    if not book.content_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book has no content file",
        )

    candidate = (BACKEND_ROOT / book.content_file).resolve()
    try:
        candidate.relative_to(BACKEND_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content file path") from exc

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF file not found")

    return FileResponse(candidate, media_type="application/pdf", filename=candidate.name)


@router.post("/{book_id}/read", status_code=status.HTTP_201_CREATED)
async def read_book(
    book_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Mark a book as read and generate recommendations"""
    # Add to reading history
    history = await HistoryService.add_to_history(session, current_user.id, book_id)

    return {"message": "Book marked as read", "history_id": history.id}


@router.post("/", response_model=BookDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_book(
    book_create: BookCreate, session: AsyncSession = Depends(get_session)
):
    """Create a new book"""
    book = await BookService.create_book(session, book_create)
    book_detail = await BookService.get_book_by_id_with_details(book.id, session)
    if not book_detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book_detail


@router.post("/{book_id}/like", response_model=BookLikeResponse)
async def like_book(
    book_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Like a book (increment total_likes)"""
    book = await BookService.like_book(session, book_id, current_user.id)
    return BookLikeResponse(id=book.id, total_likes=book.total_likes)


@router.delete("/{book_id}/like", response_model=BookLikeResponse)
async def unlike_book(
    book_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Unlike a book (decrement total_likes)"""
    book = await BookService.unlike_book(session, book_id, current_user.id)
    return BookLikeResponse(id=book.id, total_likes=book.total_likes)


@router.get("/{book_id}/like", response_model=BookLikeStatusResponse)
async def get_like_status(
    book_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Check whether the current user already liked a book."""
    is_liked = await BookService.is_book_liked(session, book_id, current_user.id)
    return BookLikeStatusResponse(id=book_id, is_liked=is_liked)


