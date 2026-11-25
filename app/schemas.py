from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TranscriptionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    text: str = Field(default="", max_length=100_000)
    language: Optional[str] = Field(default=None, max_length=50)


class TranscriptionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    text: Optional[str] = Field(default=None, max_length=100_000)
    language: Optional[str] = Field(default=None, max_length=50)


class TranscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    text: str
    language: Optional[str]
    source: str
    duration_seconds: float
    segments: List[Any]
    created_at: datetime
    updated_at: datetime


class TranscriptionList(BaseModel):
    items: List[TranscriptionOut]
    total: int
