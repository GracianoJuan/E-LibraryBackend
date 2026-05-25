from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, func
from models.user import User, UserCreate
from utils.jwt_utils import hash_password, verify_password, create_access_token


class AuthService:
    """Service for handling authentication logic"""

    @staticmethod
    async def register_user(session: AsyncSession, user_create: UserCreate) -> User:
        """Register a new user"""
        normalized_email = user_create.email.strip().lower()

        # Check if user already exists
        statement = select(User).where(func.lower(User.email) == normalized_email)
        result = await session.execute(statement)
        existing_user = result.scalars().first()

        if existing_user:
            raise ValueError("Email already used")

        # Create new user with hashed password
        user = User(
            email=normalized_email,
            name=user_create.name,
            hashed_password=hash_password(user_create.password),
        )
        session.add(user)
        try:
            await session.commit()
            await session.refresh(user)
        except IntegrityError:
            await session.rollback()
            raise ValueError("Email already used")
        return user

    @staticmethod
    async def login_user(session: AsyncSession, email: str, password: str) -> dict:
        """Login user and return access token"""
        normalized_email = email.strip().lower()

        # Find user by email
        statement = select(User).where(func.lower(User.email) == normalized_email)
        result = await session.execute(statement)
        user = result.scalars().first()

        if not user:
            raise ValueError("Invalid email or password")

        # Verify password
        if not verify_password(password, user.hashed_password):
            raise ValueError("Invalid email or password")

        # Generate access token
        access_token = create_access_token(user.id)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
            },
        }
