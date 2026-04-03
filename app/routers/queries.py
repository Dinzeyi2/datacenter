from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.query import SavedQuery

router = APIRouter()


class QueryCreate(BaseModel):
    title: str
    description: Optional[str] = None
    sql: str
    folder: Optional[str] = "general"
    variables: Optional[dict] = {}
    visibility: Optional[str] = "private"
    connection_id: int


class QueryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    sql: Optional[str] = None
    folder: Optional[str] = None
    variables: Optional[dict] = None
    visibility: Optional[str] = None


class QueryOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    sql: str
    folder: str
    variables: dict
    visibility: str
    connection_id: int
    author_id: int

    class Config:
        from_attributes = True


@router.post("/", response_model=QueryOut)
def create_query(
    body: QueryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = SavedQuery(**body.dict(), author_id=current_user.id)
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


@router.get("/", response_model=list[QueryOut])
def list_queries(
    search: Optional[str] = Query(None),
    folder: Optional[str] = Query(None),
    connection_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SavedQuery).filter(
        (SavedQuery.author_id == current_user.id) | (SavedQuery.visibility.in_(["team", "public"]))
    )
    if search:
        q = q.filter(
            SavedQuery.title.ilike(f"%{search}%") | SavedQuery.description.ilike(f"%{search}%")
        )
    if folder:
        q = q.filter(SavedQuery.folder == folder)
    if connection_id:
        q = q.filter(SavedQuery.connection_id == connection_id)
    return q.order_by(SavedQuery.updated_at.desc().nullslast()).all()


@router.get("/{query_id}", response_model=QueryOut)
def get_query(
    query_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SavedQuery).filter(SavedQuery.id == query_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Query not found")
    if q.visibility == "private" and q.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return q


@router.patch("/{query_id}", response_model=QueryOut)
def update_query(
    query_id: int,
    body: QueryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SavedQuery).filter(
        SavedQuery.id == query_id, SavedQuery.author_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Query not found")
    for field, val in body.dict(exclude_none=True).items():
        setattr(q, field, val)
    db.commit()
    db.refresh(q)
    return q


@router.delete("/{query_id}")
def delete_query(
    query_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SavedQuery).filter(
        SavedQuery.id == query_id, SavedQuery.author_id == current_user.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Query not found")
    db.delete(q)
    db.commit()
    return {"deleted": True}


@router.post("/{query_id}/fork", response_model=QueryOut)
def fork_query(
    query_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    original = db.query(SavedQuery).filter(SavedQuery.id == query_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Query not found")
    if original.visibility == "private" and original.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    forked = SavedQuery(
        title=f"{original.title} (fork)",
        description=original.description,
        sql=original.sql,
        folder=original.folder,
        variables=original.variables,
        visibility="private",
        connection_id=original.connection_id,
        author_id=current_user.id,
    )
    db.add(forked)
    db.commit()
    db.refresh(forked)
    return forked
