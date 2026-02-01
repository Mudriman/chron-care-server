from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
import logging

from app.db.session import get_session
from app.db.models import User
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token
)
from app.schemas.user import UserRegister, UserLogin, UserResponse, TokenResponse

# Инициализация логгера
logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    responses={
        201: {"description": "User created successfully"},
        400: {"description": "User already exists"},
        422: {"description": "Validation error"}
    }
)
def register(user: UserRegister, session: Session = Depends(get_session)):
    """Register a new user in the system"""
    logger.info(f"Registration attempt for email: {user.email}")

    # Проверка существующего пользователя
    existing_user = session.exec(
        select(User).where(User.email == user.email)
    ).first()

    if existing_user:
        logger.warning(f"Registration failed - user already exists: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Создание нового пользователя
    new_user = User(
        email=user.email,
        password_hash=hash_password(user.password),
        role="patient",
        is_active=True
    )

    try:
        session.add(new_user)
        session.commit()
        session.refresh(new_user)

        logger.info(f"User registered successfully: {new_user.id} ({new_user.email})")
        return UserResponse(
            id=new_user.id,
            email=new_user.email,
            role=new_user.role,
            is_active=new_user.is_active
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Registration error for {user.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during registration"
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User login",
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"},
        422: {"description": "Validation error"}
    }
)
def login(user: UserLogin, session: Session = Depends(get_session)):
    """Authenticate user and return JWT token"""
    logger.info(f"Login attempt for email: {user.email}")

    # Поиск пользователя
    db_user = session.exec(
        select(User).where(User.email == user.email)
    ).first()

    if not db_user:
        logger.warning(f"Login failed - user not found: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Проверка пароля
    if not verify_password(user.password, db_user.password_hash):
        logger.warning(f"Login failed - invalid password for user: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Генерация токена
    try:
        token = create_access_token({"sub": str(db_user.id), "role": db_user.role})
        logger.info(f"Login successful for user: {db_user.id} ({db_user.email})")

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            role=db_user.role
        )

    except Exception as e:
        logger.error(f"Token generation error for {user.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authentication"
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check"
)
def health_check():
    """Simple health check endpoint"""
    logger.debug("Health check called")
    return {"status": "healthy", "service": "auth"}


# @router.post("/create-admin", include_in_schema=False)
# def create_admin(
#         email: str = "admin@example.com",
#         password: str = "admin123",
#         session: Session = Depends(get_session)
# ):
#     existing_admin = session.exec(
#         select(User).where(User.email == email)
#     ).first()
#
#     if existing_admin:
#         return {"message": "Admin already exists"}
#
#     admin_user = User(
#         email=email,
#         password_hash=hash_password(password),
#         role="admin",
#         is_active=True
#     )
#
#     session.add(admin_user)
#     session.commit()
#
#     return {"message": "Admin created", "email": email}