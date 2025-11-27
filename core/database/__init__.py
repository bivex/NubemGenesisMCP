"""
Database Module for Multi-Tenant Architecture
Handles database connections, sessions, and initialization
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool

from .models import Base, Tenant, APIKey, UsageMetric, TenantEvent, TenantSecret, TenantQuota

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_SessionFactory = None


def get_database_url() -> str:
    """
    Get database URL from environment variables

    Returns:
        Database connection URL
    """
    # Try standard PostgreSQL environment variables
    db_url = os.getenv('DATABASE_URL')

    if db_url:
        # Handle Heroku/Cloud Run style URLs (postgres:// -> postgresql://)
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        return db_url

    # Construct from individual components
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'nubemsfc')
    db_user = os.getenv('DB_USER', 'postgres')
    db_password = os.getenv('DB_PASSWORD', '')

    if db_password:
        return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    else:
        return f"postgresql://{db_user}@{db_host}:{db_port}/{db_name}"


def init_database(
    database_url: Optional[str] = None,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_recycle: int = 3600,
    connect_timeout: int = 10
) -> None:
    """
    Initialize database engine and session factory

    Args:
        database_url: Database connection URL (optional, defaults to env)
        echo: Log SQL queries (for debugging)
        pool_size: Number of connections to maintain
        max_overflow: Max connections beyond pool_size
        pool_recycle: Recycle connections after N seconds
        connect_timeout: Connection timeout in seconds
    """
    global _engine, _SessionFactory

    if _engine is not None:
        logger.warning("Database already initialized")
        return

    url = database_url or get_database_url()

    logger.info(f"Initializing database connection to {url.split('@')[1] if '@' in url else url}")

    # Create engine
    _engine = create_engine(
        url,
        echo=echo,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,  # Verify connections before using
        connect_args={
            'connect_timeout': connect_timeout,
            'options': '-c timezone=utc'
        }
    )

    # Test connection
    try:
        with _engine.connect() as conn:
            result = conn.execute("SELECT version()")
            version = result.scalar()
            logger.info(f"Connected to PostgreSQL: {version}")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        _engine = None
        raise

    # Create session factory
    _SessionFactory = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False
    )

    # Register event listeners
    _register_event_listeners(_engine)

    logger.info("✅ Database initialized successfully")


def _register_event_listeners(engine):
    """Register SQLAlchemy event listeners for enhanced functionality"""

    @event.listens_for(engine, "connect")
    def receive_connect(dbapi_conn, connection_record):
        """Set up connection on connect"""
        # Set timezone to UTC
        cursor = dbapi_conn.cursor()
        cursor.execute("SET TIME ZONE 'UTC'")
        cursor.close()

    @event.listens_for(engine, "checkout")
    def receive_checkout(dbapi_conn, connection_record, connection_proxy):
        """Check connection health on checkout"""
        # Verify connection is alive
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SELECT 1")
        except:
            # Connection is dead, raise DisconnectionError
            raise Exception("Connection is dead")
        finally:
            cursor.close()


def get_engine():
    """
    Get the global database engine

    Returns:
        SQLAlchemy engine

    Raises:
        RuntimeError: If database not initialized
    """
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _engine


def get_session() -> Session:
    """
    Get a new database session

    Returns:
        SQLAlchemy session

    Raises:
        RuntimeError: If database not initialized
    """
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _SessionFactory()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Provide a transactional scope for database operations

    Usage:
        with session_scope() as session:
            tenant = session.query(Tenant).filter_by(email='test@example.com').first()
            session.add(tenant)
            # Commit happens automatically
            # Rollback happens on exception

    Yields:
        Database session
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database error, rolling back: {e}")
        raise
    finally:
        session.close()


def set_tenant_context(session: Session, tenant_id: str) -> None:
    """
    Set tenant context for Row Level Security

    Args:
        session: Database session
        tenant_id: Tenant UUID
    """
    session.execute(f"SET app.current_tenant_id = '{tenant_id}'")


def reset_tenant_context(session: Session) -> None:
    """
    Reset tenant context (for admin operations)

    Args:
        session: Database session
    """
    session.execute("RESET app.current_tenant_id")


def health_check() -> dict:
    """
    Check database health

    Returns:
        Health status dictionary
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            result.scalar()

            # Get pool status
            pool = engine.pool
            pool_status = {
                'size': pool.size(),
                'checked_in': pool.checkedin(),
                'overflow': pool.overflow(),
                'checked_out': pool.checkedout()
            }

            return {
                'status': 'healthy',
                'connected': True,
                'pool': pool_status
            }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            'status': 'unhealthy',
            'connected': False,
            'error': str(e)
        }


def close_database() -> None:
    """Close database connections and clean up"""
    global _engine, _SessionFactory

    if _engine:
        _engine.dispose()
        _engine = None

    _SessionFactory = None
    logger.info("Database connections closed")


# Export commonly used objects
__all__ = [
    # Connection management
    'init_database',
    'get_engine',
    'get_session',
    'session_scope',
    'close_database',
    'health_check',

    # Tenant context (for RLS)
    'set_tenant_context',
    'reset_tenant_context',

    # Models
    'Base',
    'Tenant',
    'APIKey',
    'UsageMetric',
    'TenantEvent',
    'TenantSecret',
    'TenantQuota',
]
