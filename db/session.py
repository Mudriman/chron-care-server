from sqlmodel import create_engine, Session
from app.core.config import settings

# SQLite требует connect_args для корректной работы с асинхронностью
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    echo=True,
    connect_args=connect_args
)

def get_session():
    with Session(engine) as session:
        yield session