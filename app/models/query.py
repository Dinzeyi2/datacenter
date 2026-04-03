from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    sql = Column(Text, nullable=False)
    folder = Column(String, default="general")
    variables = Column(JSON, default=dict)
    visibility = Column(String, default="private")  # private, team, public
    connection_id = Column(Integer, ForeignKey("db_connections.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    author = relationship("User", back_populates="queries")
    connection = relationship("DBConnection", back_populates="queries")
    runs = relationship("QueryRun", back_populates="query")


class QueryRun(Base):
    __tablename__ = "query_runs"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("saved_queries.id"), nullable=True)
    raw_sql = Column(Text, nullable=False)
    connection_id = Column(Integer, ForeignKey("db_connections.id"))
    run_by_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")  # pending, running, success, error
    row_count = Column(Integer)
    execution_time_ms = Column(Float)
    error_message = Column(Text)
    result_cache_key = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    query = relationship("SavedQuery", back_populates="runs")
    run_by = relationship("User", back_populates="query_runs")
