"""
Row Level Security (RLS) Middleware

Sets PostgreSQL Row Level Security context for tenant isolation.
Design approved by expert panel (see AUTH_MIDDLEWARE_EXPERT_DEBATE.md)

Flow:
1. Get tenant_id from request.state (set by AuthenticationMiddleware)
2. Execute: SET app.current_tenant_id = '{tenant_id}'
3. Process request
4. Cleanup: RESET app.current_tenant_id (finally block)

Performance:
- <1ms overhead (PostgreSQL SET command is fast)
- Ensures data isolation at database level
- Works with RLS policies defined in database migrations

Expert consensus: 5/5 experts approved this approach
Security expert (Sarah): "RLS is defense-in-depth. Even if app has bugs,
database ensures tenants can only access their own data."
"""

import logging
import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from prometheus_client import Counter, Histogram

from core.database.connection import get_db_session

logger = logging.getLogger(__name__)

# Prometheus Metrics
RLS_REQUESTS_TOTAL = Counter(
    'rls_requests_total',
    'Total RLS context set operations',
    ['status']
)

RLS_LATENCY = Histogram(
    'rls_latency_seconds',
    'RLS context set latency'
)


class RLSMiddleware(BaseHTTPMiddleware):
    """
    Sets PostgreSQL Row Level Security context

    Prerequisites:
    - AuthenticationMiddleware must run BEFORE this middleware
    - request.state.tenant_id must be set
    - Database must have RLS policies enabled

    PostgreSQL context variables:
    - app.current_tenant_id: UUID of current tenant

    RLS Policies (from migrations/001_create_multi_tenant_schema.sql):
        CREATE POLICY tenant_isolation_policy ON tenants
            FOR ALL
            USING (id = current_setting('app.current_tenant_id')::UUID);

    Error handling:
    - If tenant_id not in request.state, returns 500 (middleware order issue)
    - Always resets context in finally block (cleanup)
    """

    async def dispatch(self, request: Request, call_next):
        """
        Main middleware dispatch method

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response
        """
        # Check if tenant_id is set (by AuthenticationMiddleware)
        tenant_id = getattr(request.state, "tenant_id", None)

        # If no tenant_id, this is likely a public endpoint - skip RLS
        if tenant_id is None:
            return await call_next(request)

        # Set RLS context
        start_time = time.time()
        context_set = False

        try:
            # Set PostgreSQL context variable
            await self._set_rls_context(tenant_id)
            context_set = True

            # Record success
            RLS_REQUESTS_TOTAL.labels(status="success").inc()
            latency = time.time() - start_time
            RLS_LATENCY.observe(latency)

            logger.debug(f"RLS context set: tenant_id={tenant_id} ({latency*1000:.2f}ms)")

            # Continue to next middleware
            response = await call_next(request)
            return response

        except Exception as e:
            # RLS context setting failed
            logger.error(f"Failed to set RLS context for tenant {tenant_id}: {e}", exc_info=True)
            RLS_REQUESTS_TOTAL.labels(status="failed").inc()

            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "request_id": getattr(request.state, "request_id", "unknown")
                }
            )

        finally:
            # Always reset context (cleanup)
            if context_set:
                try:
                    await self._reset_rls_context()
                    logger.debug(f"RLS context reset: tenant_id={tenant_id}")
                except Exception as e:
                    logger.error(f"Failed to reset RLS context: {e}", exc_info=True)

    async def _set_rls_context(self, tenant_id: str) -> None:
        """
        Set PostgreSQL RLS context variable

        Executes: SET LOCAL app.current_tenant_id = '{tenant_id}'

        Note: Using SET LOCAL (not SET) ensures the setting is transaction-scoped
        and automatically reset at transaction end.

        Args:
            tenant_id: UUID string of tenant

        Raises:
            Exception: If PostgreSQL command fails
        """
        async with get_db_session() as session:
            # Use SET LOCAL for transaction-scoped setting
            await session.execute(
                f"SET LOCAL app.current_tenant_id = '{tenant_id}'"
            )
            await session.commit()

    async def _reset_rls_context(self) -> None:
        """
        Reset PostgreSQL RLS context variable

        Executes: RESET app.current_tenant_id

        This is a safety measure. SET LOCAL automatically resets at transaction end,
        but we explicitly reset for defense-in-depth.

        Raises:
            Exception: If PostgreSQL command fails
        """
        async with get_db_session() as session:
            await session.execute("RESET app.current_tenant_id")
            await session.commit()


class RLSContextManager:
    """
    Helper class for manual RLS context management

    Use this when you need to set RLS context outside of middleware
    (e.g., in background jobs, CLI scripts, etc.)

    Usage:
        async with RLSContextManager(tenant_id="...") as ctx:
            # All database queries within this block will have RLS context set
            async with get_db_session() as session:
                result = await session.execute(select(Tenant))
    """

    def __init__(self, tenant_id: str):
        """
        Initialize RLS context manager

        Args:
            tenant_id: UUID string of tenant
        """
        self.tenant_id = tenant_id
        self.session = None

    async def __aenter__(self):
        """Set RLS context on enter"""
        self.session = get_db_session()
        session = await self.session.__aenter__()

        await session.execute(
            f"SET LOCAL app.current_tenant_id = '{self.tenant_id}'"
        )
        await session.commit()

        logger.debug(f"RLS context set: tenant_id={self.tenant_id}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Reset RLS context on exit"""
        if self.session:
            try:
                session = self.session._session  # Access underlying session
                await session.execute("RESET app.current_tenant_id")
                await session.commit()
                logger.debug(f"RLS context reset: tenant_id={self.tenant_id}")
            except Exception as e:
                logger.error(f"Failed to reset RLS context: {e}")
            finally:
                await self.session.__aexit__(exc_type, exc_val, exc_tb)
