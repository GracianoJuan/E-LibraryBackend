from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from typing import List
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db import get_session
from models.user import UserCreate, User, UserRead
from services.AuthServices import AuthService
from middlewares.auth import get_current_user


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserRead


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    """Register a new user"""
    try:
        user_create = UserCreate(
            name=request.name, email=request.email, password=request.password
        )
        user = await AuthService.register_user(session, user_create)

        # Return access token
        token_response = await AuthService.login_user(session, request.email, request.password)
        return AuthResponse(
            access_token=token_response["access_token"],
            token_type=token_response["token_type"],
            user=UserRead(id=user.id, email=user.email, name=user.name),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


""" Login endpoint
params : email (str), password (str)
"""
@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    """Login user and return JWT token"""
    try:
        token_response = await AuthService.login_user(
            session, request.email, request.password
        )
        user_data = token_response["user"]
        return AuthResponse(
            access_token=token_response["access_token"],
            token_type=token_response["token_type"],
            user=UserRead(
                id=user_data["id"], email=user_data["email"], name=user_data["name"]
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get("/me", response_model=UserRead)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Get current user info"""
    return UserRead(id=current_user.id, email=current_user.email, name=current_user.name)


@router.get("/all", response_model=List[UserRead])
async def get_all_users(session: AsyncSession = Depends(get_session)) -> List[UserRead]:
    """Return all users (for manual testing only)."""
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [UserRead(id=u.id, email=u.email, name=u.name) for u in users]


@router.get("/user/{user_id}", response_model=UserRead)
async def get_user_by_id(user_id: int, session: AsyncSession = Depends(get_session)) -> UserRead:
    """Return a single user by ID (manual test endpoint)."""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead(id=user.id, email=user.email, name=user.name)


@router.post("/user", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> UserRead:
    """Create a user (manual test endpoint)."""
    try:
        user_create = UserCreate(
            name=request.name, email=request.email, password=request.password
        )
        user = await AuthService.register_user(session, user_create)
        return UserRead(id=user.id, email=user.email, name=user.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Insert data issue
# Read data works fine