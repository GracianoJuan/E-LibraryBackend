from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from db import get_session
from models.book import BookRead
from models.user import User
from services.RecService import RecommendationService
from middlewares.auth import get_current_user


router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=list[BookRead])
async def get_recommendations(
    limit: int = 15,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if limit > 100:
        limit = 100
    recs_with_books = await RecommendationService.get_user_recommendations(
        session, current_user.id, limit
    )
    return [book for _, book in recs_with_books]
