from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime

from db import get_session
from models.user import User
from services.HistoryService import HistoryService
from services.BookService import BookService
from middlewares.auth import get_current_user


router = APIRouter(prefix="/history", tags=["history"])


class DeleteHistoryResponse(BaseModel):
    message: str


@router.get("")
async def get_reading_history(
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's reading history with book details."""
    if limit > 500:
        limit = 500

    histories = await HistoryService.get_user_history(session, current_user.id, limit)
    response = []
    for history in histories:
        # Use BookService to provide human-readable book details
        book_details = await BookService.get_book_by_id_with_details(history.book_id, session)
        if not book_details:
            continue
        response.append({
            "id": history.id,
            "read_at": history.read_at,
            "book": book_details,
        })

    return response


@router.delete("/{book_id}", response_model=DeleteHistoryResponse)
async def delete_reading_history(
    book_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    deleted = await HistoryService.delete_history(session, current_user.id, book_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History not found")

    return DeleteHistoryResponse(message="History deleted")
