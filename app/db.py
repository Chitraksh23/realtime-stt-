import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

url = settings.database_url
is_sqlite = url.startswith("sqlite")

if is_sqlite and ":memory:" not in url:
    path = url.replace("sqlite:///", "", 1)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if is_sqlite else {},
    pool_pre_ping=True,  # serverless Postgres (Neon) drops idle connections
    pool_recycle=300,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(bind=engine)
