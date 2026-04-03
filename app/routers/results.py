import json
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.query import SavedQuery, QueryRun
from app.models.connection import DBConnection
from app.services.executor import run_query, substitute_variables
from app.services.encryption import decrypt

router = APIRouter()


class RunRequest(BaseModel):
    sql: str
    connection_id: int
    query_id: Optional[int] = None
    variables: Optional[dict] = {}


@router.post("/run")
def run(
    body: RunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = db.query(DBConnection).filter(
        DBConnection.id == body.connection_id,
        DBConnection.owner_id == current_user.id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    sql = substitute_variables(body.sql, body.variables or {})

    run_record = QueryRun(
        query_id=body.query_id,
        raw_sql=sql,
        connection_id=body.connection_id,
        run_by_id=current_user.id,
        status="running",
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)

    try:
        password = decrypt(conn.encrypted_password) if conn.encrypted_password else ""
        result = run_query(conn, password, sql)

        run_record.status = "success"
        run_record.row_count = result["row_count"]
        run_record.execution_time_ms = result["execution_time_ms"]
        run_record.result_cache_key = json.dumps({"columns": result["columns"], "rows": result["rows"]})
        db.commit()

        return {
            "run_id": run_record.id,
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "execution_time_ms": result["execution_time_ms"],
            "truncated": result["truncated"],
        }
    except PermissionError as e:
        run_record.status = "error"
        run_record.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        run_record.status = "error"
        run_record.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def history(
    connection_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(QueryRun).filter(QueryRun.run_by_id == current_user.id)
    if connection_id:
        q = q.filter(QueryRun.connection_id == connection_id)
    runs = q.order_by(QueryRun.created_at.desc()).limit(100).all()
    return [
        {
            "id": r.id,
            "query_id": r.query_id,
            "raw_sql": r.raw_sql,
            "status": r.status,
            "row_count": r.row_count,
            "execution_time_ms": r.execution_time_ms,
            "error_message": r.error_message,
            "created_at": r.created_at,
        }
        for r in runs
    ]


@router.get("/{run_id}/export/csv")
def export_csv(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run_record = db.query(QueryRun).filter(
        QueryRun.id == run_id,
        QueryRun.run_by_id == current_user.id,
        QueryRun.status == "success",
    ).first()
    if not run_record or not run_record.result_cache_key:
        raise HTTPException(status_code=404, detail="Result not found")

    cached = json.loads(run_record.result_cache_key)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cached["columns"])
    writer.writerows(cached["rows"])
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hubble_run_{run_id}.csv"},
    )
