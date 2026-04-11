from sqlmodel import SQLModel, Field, Relationship, Column
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timezone
from enum import Enum
from sqlalchemy import JSON, Index


# -------------------------
# User role
# -------------------------
class UserRole(str, Enum):
    PATIENT = "patient"
    ADMIN = "admin"

def get_current_utc_datetime() -> datetime:
    """Get current datetime with UTC timezone"""
    return datetime.now(timezone.utc)

def get_current_utc_date() -> date:
    """Get current date in UTC timezone"""
    return datetime.now(timezone.utc).date()

# -------------------------
# User
# -------------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    email: str = Field(index=True, unique=True)
    password_hash: str

    role: UserRole = Field(default=UserRole.PATIENT)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=get_current_utc_datetime)
    updated_at: datetime = Field(default_factory=get_current_utc_datetime)

    avatar_id: Optional[str] = Field(default=None, max_length=50)

    profile_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON)
    )

    # Relationships
    medications: List["Medication"] = Relationship(back_populates="user")
    symptom_entries: List["SymptomEntry"] = Relationship(back_populates="user")
    medication_intakes: List["MedicationIntake"] = Relationship(back_populates="user")
    daily_contexts: List["DailyContext"] = Relationship(back_populates="user")
    risk_scores: List["RiskScore"] = Relationship(back_populates="user")


# -------------------------
# Medication
# -------------------------
class Medication(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")

    name: str = Field(index=True)
    dosage: str = Field()
    frequency_per_day: int = Field(ge=1, le=6)
    start_date: date = Field(default_factory=get_current_utc_date)  # Исправлено
    end_date: Optional[date] = None
    is_active: bool = Field(default=True)

    notes: Optional[str] = Field(default=None, max_length=500)  # Заметки
    notifications_enabled: bool = Field(default=True)  # Вкл/выкл уведомлений

    # Relationships
    user: User = Relationship(back_populates="medications")
    intakes: List["MedicationIntake"] = Relationship(back_populates="medication")

    __table_args__ = (
        Index('medication_user_active_idx', 'user_id', 'is_active'),
    )


# -------------------------
# Medication Intake
# -------------------------
class MedicationIntake(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    medication_id: int = Field(foreign_key="medication.id")

    intake_date: Optional[date] = None
    taken: bool = Field(default=False)
    taken_at: Optional[datetime] = None

    # Relationships
    user: User = Relationship(back_populates="medication_intakes")
    medication: Medication = Relationship(back_populates="intakes")

    __table_args__ = (
        Index('intake_user_date_idx', 'user_id', 'intake_date'),
        Index('intake_medication_date_idx', 'medication_id', 'intake_date'),
    )


# -------------------------
# Daily symptom
# -------------------------
class SymptomEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id")
    symptom_date: date = Field(default_factory=get_current_utc_date)

    cough: int = Field(default=0, ge=0, le=3)
    breathlessness: int = Field(default=0, ge=0, le=3)
    night_symptoms: bool = Field(default=False)

    # Relationships
    user: User = Relationship(back_populates="symptom_entries")

    __table_args__ = (
        Index('symptom_user_date_idx', 'user_id', 'symptom_date', unique=True),
    )


# -------------------------
# Daily context
# -------------------------
class DailyContext(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id")
    context_date: date = Field(default_factory=get_current_utc_date)

    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pollen_index: Optional[float] = None
    air_quality_index: Optional[float] = None

    extra_data: Optional[Dict] = Field(default=None, sa_column=Column(JSON))

    # Relationships
    user: User = Relationship(back_populates="daily_contexts")

    __table_args__ = (
        Index('context_user_date_idx', 'user_id', 'context_date', unique=True),
    )


# -------------------------
# Risk result
# -------------------------
class RiskScore(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id")
    risk_date: date = Field(default_factory=get_current_utc_date)

    risk_value: float = Field(ge=0, le=1)
    risk_level: str = Field()  # "low", "medium", "high"

    model_version: str = Field(default="formula_v1")
    confidence: float = Field(default=1.0, ge=0, le=1)

    factors: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON)
    )
    recommendations: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )

    # Relationships
    user: User = Relationship(back_populates="risk_scores")

    __table_args__ = (
        Index('risk_user_date_idx', 'user_id', 'risk_date', unique=True),
        Index('risk_level_date_idx', 'risk_level', 'risk_date'),
    )

class ExacerbationEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id")
    event_date: date = Field(default_factory=get_current_utc_date)

    severity: int = Field(default=1, ge=1, le=3)  # 1 mild, 2 moderate, 3 severe
    triggered_by: Optional[str] = None  # optional comment

    created_at: datetime = Field(default_factory=get_current_utc_datetime)

    __table_args__ = (
        Index('exacerbation_user_date_idx', 'user_id', 'event_date'),
    )