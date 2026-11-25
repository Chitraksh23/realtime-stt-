from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Transcription
from .schemas import (TranscriptionCreate, TranscriptionList, TranscriptionOut,
                      TranscriptionUpdate)

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])


def _get_or_404(db: Session, tid: int) -> Transcription:
    obj = db.get(Transcription, tid)
    if obj is None:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return obj


@router.get("", response_model=TranscriptionList)
def list_transcriptions(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Transcription)
    count_stmt = select(func.count()).select_from(Transcription)
    if q.strip():
        like = f"%{q.strip()}%"
        cond = or_(Transcription.text.ilike(like), Transcription.title.ilike(like))
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(Transcription.created_at.desc(), Transcription.id.desc())
        .limit(limit).offset(offset)
    ).all()
    return {"items": items, "total": total}


@router.post("", response_model=TranscriptionOut, status_code=201)
def create_transcription(payload: TranscriptionCreate, db: Session = Depends(get_db)):
    obj = Transcription(
        title=(payload.title or "").strip() or f"Note {datetime.now(timezone.utc):%Y-%m-%d %H:%M}",
        text=payload.text,
        language=payload.language,
        source="manual",
        segments=[],
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{tid}", response_model=TranscriptionOut)
def get_transcription(tid: int, db: Session = Depends(get_db)):
    return _get_or_404(db, tid)


@router.put("/{tid}", response_model=TranscriptionOut)
def update_transcription(tid: int, payload: TranscriptionUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, tid)
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        obj.title = (data["title"] or "").strip() or obj.title
    if "text" in data and data["text"] is not None:
        obj.text = data["text"]
    if "language" in data:
        obj.language = data["language"]
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{tid}", status_code=204)
def delete_transcription(tid: int, db: Session = Depends(get_db)):
    obj = _get_or_404(db, tid)
    db.delete(obj)
    db.commit()
