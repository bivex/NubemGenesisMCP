"""
Database Connection Manager

Provides async session management for PostgreSQL with SQLAlchemy.
Supports both Cloud SQL Proxy (production) and direct connection (development).

Design considerations:
- Async sessions for FastAPI compatibility
- Connection pooling for performance
- Graceful error handling
- Support for both environments (GKE + local)
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    AsyncEngine,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool, QueuePool

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine: AsyncEngine = None
_async_session_factory: async_sessionmaker = None


def get_database_url() -> str:
    """
    Get database URL from environment

    Supports two modes:
    1. Cloud SQL Proxy (production): postgresql+asyncpg://user:pass@cloudsql-proxy:5432/dbname
    2. Direct connection (development): postgresql+asyncpg://user:pass@host:5432/dbname

    Environment variables:
    - DATABASE_URL: Full database URL (highest priority)
    - POSTGRES_USER: Database user
    - POSTGRES_PASSWORD: Database password
    - POSTGRES_DB: Database name
    - POSTGRES_HOST: Database host (default: cloudsql-proxy)
    - POSTGRES_PORT: Database port (default: 5432)

    Returns:
        Database URL string

    Raises:
        ValueError: If required environment variables missing
    """
    # Check for full DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Convert to asyncpg if needed
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return database_url

    # Build from components
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    host = os.getenv("POSTGRES_HOST", "cloudsql-proxy")
    port = os.getenv("POSTGRES_PORT", "5432")

    if not all([user, password, db]):
        raise ValueError(
            "Database configuration missing. Set DATABASE_URL or "
            "POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB"
        )

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def init_database_engine(
    pool_size: int = 20,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    pool_recycle: int = 3600,
    echo: bool = False
) -> AsyncEngine:
    """
    Initialize database engine

    Args:
        pool_size: Number of connections to maintain (default: 20)
        max_overflow: Max connections beyond pool_size (default: 10)
        pool_timeout: Seconds to wait for connection (default: 30)
        pool_recycle: Seconds before recycling connection (default: 3600)
        echo: Log all SQL statements (default: False)

    Returns:
        AsyncEngine instance
    """
    global _engine, _async_session_factory

    if _engine is not None:
        logger.warning("Database engine already initialized")
        return _engine

    database_url = get_database_url()

    # Create engine with connection pooling
    _engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,  # Verify connections before using
        echo=echo,
        future=True
    )

    # Create session factory
    _async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )

    logger.info(f"✅ Database engine initialized: {database_url.split('@')[1] if '@' in database_url else 'unknown'}")
    logger.info(f"   Pool size: {pool_size}, Max overflow: {max_overflow}")

    return _engine


async def close_database_engine():
    """
    Close database engine and all connections

    Should be called on application shutdown
    """
    global _engine, _async_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("✅ Database engine closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session

    Usage:
        async with get_db_session() as session:
            result = await session.execute(select(Tenant))
            tenants = result.scalars().all()

    Yields:
        AsyncSession instance

    Raises:
        RuntimeError: If engine not initialized
    """
    global _async_session_factory

    if _async_session_factory is None:
        raise RuntimeError(
            "Database engine not initialized. Call init_database_engine() first."
        )

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """
    Check if database connection is working

    Returns:
        True if connection successful

    Raises:
        Exception: If connection fails
    """
    async with get_db_session() as session:
        result = await session.execute("SELECT 1")
        return result.scalar() == 1


async def get_connection_info() -> dict:
    """
    Get database connection information

    Returns:
        Dict with connection info:
        {
            "url": str (sanitized),
            "pool_size": int,
            "pool_checked_out": int,
            "pool_overflow": int,
            "pool_checked_in": int
        }
    """
    global _engine

    if _engine is None:
        return {"error": "Engine not initialized"}

    # Sanitize URL (hide password)
    url = str(_engine.url)
    if "@" in url:
        parts = url.split("@")
        user_pass = parts[0].split("://")[1]
        if ":" in user_pass:
            user = user_pass.split(":")[0]
            url = f"postgresql+asyncpg://{user}:***@{parts[1]}"

    # Pool stats
    pool = _engine.pool
    stats = {
        "url": url,
        "pool_size": pool.size(),
        "pool_checked_out": pool.checkedout(),
        "pool_overflow": pool.overflow(),
    }

    return stats
