# routers/user.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
import logging
from typing import Optional

from app.db.session import get_session
from app.db.models import User
from app.core.dependencies import get_current_user, get_current_patient
from app.schemas.user import UserResponse, UserUpdate, OnboardingUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    responses={
        200: {"description": "Profile retrieved successfully"},
        401: {"description": "Not authenticated"}
    }
)
def get_profile(
    current_user: User = Depends(get_current_user)
):
    """Get profile of currently authenticated user"""
    logger.info(f"Profile requested for user: {current_user.id}")

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        avatar_id=current_user.avatar_id,
        profile_data = current_user.profile_data
    )

@router.patch("/onboarding", response_model=UserResponse)
def update_onboarding(
    data: OnboardingUpdate,
    current_user: User = Depends(get_current_patient),
    session: Session = Depends(get_session)
):
    current_user.profile_data = {
        **(current_user.profile_data or {}),
        **data.dict(exclude_unset=True)
    }

    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user

@router.patch(
    "/profile",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user profile",
    responses={
        200: {"description": "Profile updated successfully"},
        401: {"description": "Not authenticated"},
        422: {"description": "Validation error"}
    }
)
def update_profile(
    updates: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update user profile (avatar only for now)"""
    logger.info(f"Profile update requested for user: {current_user.id}")

    # Обновляем только avatar_id
    if updates.avatar_id is not None:
        current_user.avatar_id = updates.avatar_id
        logger.info(f"Avatar updated to: {updates.avatar_id} for user: {current_user.id}")

    try:
        session.add(current_user)
        session.commit()
        session.refresh(current_user)

        logger.info(f"Profile updated successfully for user: {current_user.id}")
        return UserResponse(
            id=current_user.id,
            email=current_user.email,
            role=current_user.role,
            is_active=current_user.is_active,
            avatar_id=current_user.avatar_id
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Profile update error for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during profile update"
        )