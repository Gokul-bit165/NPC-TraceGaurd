"""Tests verifying schema generation, index coverage, and query compilation
for MySQL and PostgreSQL as well as SQLite.
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateTable, CreateIndex

from app.db import Base, get_engine_kwargs
from app.models import (
    UserRow, LoginRow, EmailRow, CaseRow, ActionRow, AuditRow, FeedbackRow, NotificationRow
)


def test_ddl_compilation_postgresql():
    """Verify all tables and indexes compile to valid PostgreSQL DDL without errors."""
    from sqlalchemy import create_mock_engine
    pg_engine = create_mock_engine("postgresql+psycopg2://mock:mock@localhost:5432/mock", executor=lambda *_: None)
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert f"CREATE TABLE {table.name}" in ddl
        for index in table.indexes:
            idx_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
            assert f"CREATE INDEX {index.name}" in idx_ddl


def test_ddl_compilation_mysql():
    """Verify all tables and indexes compile to valid MySQL DDL without errors."""
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert f"CREATE TABLE {table.name}" in ddl
        for index in table.indexes:
            idx_ddl = str(CreateIndex(index).compile(dialect=mysql.dialect()))
            assert f"CREATE INDEX {index.name}" in idx_ddl


def test_query_compilation_dialects():
    """Verify core cross-user and case queries compile cleanly for PostgreSQL and MySQL."""
    # 1. IP touch query within 24 hours
    now = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)
    q1 = select(LoginRow.user_id).where(LoginRow.ip == "198.51.100.1", LoginRow.ts > now).distinct()
    pg_sql1 = str(q1.compile(dialect=postgresql.dialect()))
    my_sql1 = str(q1.compile(dialect=mysql.dialect()))
    assert "DISTINCT" in pg_sql1 and "DISTINCT" in my_sql1

    # 2. Shared device query
    q2 = select(LoginRow.user_id).where(
        LoginRow.device == "windows|chrome",
        LoginRow.ip == "198.51.100.1",
        LoginRow.success.is_(True)
    ).distinct()
    pg_sql2 = str(q2.compile(dialect=postgresql.dialect()))
    my_sql2 = str(q2.compile(dialect=mysql.dialect()))
    assert "device" in pg_sql2 and "device" in my_sql2

    # 3. Case listing query with join and order
    q3 = select(CaseRow, UserRow).join(UserRow, UserRow.id == CaseRow.user_id, isouter=True)\
        .where(CaseRow.status.in_(["open", "investigating"]))\
        .order_by(CaseRow.score.desc(), CaseRow.campaign_size.desc())
    pg_sql3 = str(q3.compile(dialect=postgresql.dialect()))
    my_sql3 = str(q3.compile(dialect=mysql.dialect()))
    assert "LEFT OUTER JOIN" in pg_sql3 and "LEFT OUTER JOIN" in my_sql3


def test_indexes_present_on_critical_columns():
    """Verify that all required indexes exist on models for high-scale operation."""
    login_idx_names = {idx.name for idx in LoginRow.__table__.indexes}
    assert "ix_login_user_ts" in login_idx_names
    assert "ix_login_ip_ts" in login_idx_names
    assert "ix_login_dev_ip_succ" in login_idx_names
    assert "ix_login_risk_ts" in login_idx_names

    email_idx_names = {idx.name for idx in EmailRow.__table__.indexes}
    assert "ix_email_user_recv" in email_idx_names
    assert "ix_email_camp_recv" in email_idx_names

    case_idx_names = {idx.name for idx in CaseRow.__table__.indexes}
    assert "ix_case_user_status" in case_idx_names
    assert "ix_case_band_status" in case_idx_names
    assert "ix_case_score_camp" in case_idx_names


def test_connection_pool_kwargs():
    """Verify pool parameters for postgresql/mysql vs sqlite."""
    sq_kwargs = get_engine_kwargs("sqlite:///test.db")
    assert "connect_args" in sq_kwargs
    assert sq_kwargs["connect_args"].get("check_same_thread") is False

    pg_kwargs = get_engine_kwargs("postgresql://user:pass@localhost/db")
    assert pg_kwargs.get("pool_pre_ping") is True
    assert pg_kwargs.get("pool_size", 0) >= 10
    assert pg_kwargs.get("max_overflow", 0) >= 10

    my_kwargs = get_engine_kwargs("mysql+pymysql://user:pass@localhost/db")
    assert my_kwargs.get("pool_pre_ping") is True
    assert my_kwargs.get("pool_size", 0) >= 10
