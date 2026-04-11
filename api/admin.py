# app/api/admin.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from typing import List
import logging

from app.db.session import get_session
from app.db.models import User
from app.core.dependencies import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users")
def get_users(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: User = Depends(get_current_admin),
        session: Session = Depends(get_session)
):
    """Get all users"""
    statement = select(User).offset(skip).limit(limit)
    users = session.exec(statement).all()

    # Не возвращаем хэши паролей
    user_list = []
    for user in users:
        user_list.append({
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        })

    return {"users": user_list, "total": len(user_list)}


@router.delete("/users/{user_id}")
def delete_user(
        user_id: int,
        current_user: User = Depends(get_current_admin),
        session: Session = Depends(get_session)
):
    """Delete user"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    session.delete(user)
    session.commit()

    return {"message": f"User {user_id} deleted"}


# ? Статистика
@router.get("/stats")
def get_stats(
        current_user: User = Depends(get_current_admin),
        session: Session = Depends(get_session)
):
    """Get system statistics"""
    # Количество пользователей
    statement = select(User)
    all_users = session.exec(statement).all()

    total_users = len(all_users)
    active_users = len([u for u in all_users if u.is_active])
    patients = len([u for u in all_users if u.role == "patient"])
    admins = len([u for u in all_users if u.role == "admin"])

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "patients": patients,
            "admins": admins
        },
        "activity": {
            "avg_risk": 0.45,  # Заглушка
            "last_week_active": 78  # Заглушка
        }
    }