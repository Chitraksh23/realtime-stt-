from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled")
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="live")  # live | manual
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    segments: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
