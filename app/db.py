from sqlmodel import SQLModel, create_engine, Session
from app.config import settings

engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
