from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.connection import DBConnection
from app.services.encryption import encrypt, decrypt
from app.services.executor import get_schema, run_query

router = APIRouter()


class ConnectionCreate(BaseModel):
    name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database: str
    username: Optional[str] = None
    password: Optional[str] = None


class ConnectionOut(BaseModel):
    id: int
    name: str
    db_type: str
    host: Optional[str]
    port: Optional[int]
    database: str
    username: Optional[str]

    class Config:
        from_attributes = True


@router.post("/", response_model=ConnectionOut)
def create_connection(
    body: ConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = DBConnection(
        name=body.name,
        db_type=body.db_type,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        encrypted_password=encrypt(body.password) if body.password else None,
        owner_id=current_user.id,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@router.get("/", response_model=list[ConnectionOut])
def list_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(DBConnection).filter(DBConnection.owner_id == current_user.id).all()


@router.get("/{conn_id}", response_model=ConnectionOut)
def get_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.owner_id == current_user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.delete("/{conn_id}")
def delete_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.owner_id == current_user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(conn)
    db.commit()
    return {"deleted": True}


@router.post("/{conn_id}/test")
def test_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.owner_id == current_user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        password = decrypt(conn.encrypted_password) if conn.encrypted_password else ""
        run_query(conn, password, "SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/{conn_id}/schema")
def explore_schema(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.owner_id == current_user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        password = decrypt(conn.encrypted_password) if conn.encrypted_password else ""
        schema = get_schema(conn, password)
        return {"schema": schema}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
