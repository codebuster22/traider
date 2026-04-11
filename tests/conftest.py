"""Shared test fixtures for traider backend."""
import os
import pytest
from testcontainers.postgres import PostgresContainer

from traider import db as db_module


@pytest.fixture(scope="module")
def postgres_container():
    """Start a real Postgres container for the module's tests."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="module")
def db_url(postgres_container):
    return postgres_container.get_connection_url().replace("postgresql+psycopg2", "postgresql")


@pytest.fixture(scope="module", autouse=True)
def initialized_db(db_url, postgres_container):
    """Initialize the pool against the test container and run DDL once per module."""
    os.environ["DATABASE_URL"] = db_url
    db_module.DATABASE_URL = db_url
    db_module.init_db()
    yield
    db_module.close_db()


@pytest.fixture
def clean_db():
    """Truncate all tables before each test. Use inside tests that need isolation."""
    with db_module.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                TRUNCATE variant_aliases, stock_movements, stock_balances,
                         fabric_variants, fabric_aliases, fabrics
                RESTART IDENTITY CASCADE
            """)
        conn.commit()
    yield
