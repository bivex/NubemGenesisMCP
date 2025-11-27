"""
SQLite-based Audit Logging Implementation
Author: PATH A Autonomous Execution
Purpose: Persistent audit trail for compliance and debugging
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class SQLiteAuditLogger:
    """
    Audit logger using SQLite for persistent storage.

    Features:
    - Structured logging with JSON support
    - Fast writes with WAL mode
    - Queryable audit trail
    - Automatic table creation
    - Thread-safe operations
    """

    def __init__(self, db_path: str = "./data/audit.db"):
        """
        Initialize audit logger with SQLite database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

        logger.info(f"SQLiteAuditLogger initialized: {db_path}")

    def _init_database(self):
        """Initialize database schema if not exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Main audit log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource_type TEXT,
                    resource_id TEXT,
                    mcp_name TEXT,
                    details TEXT,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    request_id TEXT,
                    duration_ms INTEGER,
                    metadata TEXT
                )
            ''')

            # Indexes for common queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON audit_log(timestamp)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_id
                ON audit_log(user_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_action
                ON audit_log(action)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_success
                ON audit_log(success)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_mcp_name
                ON audit_log(mcp_name)
            ''')

            # Statistics table for quick queries
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    total_requests INTEGER DEFAULT 0,
                    total_success INTEGER DEFAULT 0,
                    total_failures INTEGER DEFAULT 0,
                    unique_users INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            ''')

            conn.commit()

            # Enable WAL mode for better concurrent performance
            cursor.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def log(
        self,
        action: str,
        user_id: Optional[str] = None,
        success: bool = True,
        level: str = "INFO",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        mcp_name: Optional[str] = None,
        details: Optional[Dict] = None,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log an audit event.

        Args:
            action: Action performed (e.g., "mcp_call", "auth_attempt", "config_change")
            user_id: User or API key identifier
            success: Whether action succeeded
            level: Log level (INFO, WARNING, ERROR)
            resource_type: Type of resource affected (e.g., "mcp", "user", "secret")
            resource_id: ID of resource
            mcp_name: Name of MCP if applicable
            details: Additional details as dict
            error_message: Error message if failed
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request correlation ID
            duration_ms: Duration in milliseconds
            metadata: Additional metadata as dict

        Returns:
            ID of inserted audit log entry

        Examples:
            >>> logger = SQLiteAuditLogger()
            >>> logger.log(
            ...     action="mcp_call",
            ...     user_id="user123",
            ...     mcp_name="google-workspace",
            ...     success=True,
            ...     details={"method": "gmail.send", "to": "user@example.com"}
            ... )
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO audit_log (
                        timestamp, level, user_id, action, resource_type,
                        resource_id, mcp_name, details, success, error_message,
                        ip_address, user_agent, request_id, duration_ms, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.utcnow().isoformat(),
                    level,
                    user_id,
                    action,
                    resource_type,
                    resource_id,
                    mcp_name,
                    json.dumps(details) if details else None,
                    1 if success else 0,
                    error_message,
                    ip_address,
                    user_agent,
                    request_id,
                    duration_ms,
                    json.dumps(metadata) if metadata else None
                ))

                conn.commit()
                return cursor.lastrowid

        except sqlite3.Error as e:
            logger.error(f"SQLite error logging audit event: {e}")
            return -1

    def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        mcp_name: Optional[str] = None,
        success: Optional[bool] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Query audit logs with filters.

        Args:
            user_id: Filter by user ID
            action: Filter by action
            mcp_name: Filter by MCP name
            success: Filter by success status
            start_time: Filter by start timestamp (ISO format)
            end_time: Filter by end timestamp (ISO format)
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            List of audit log entries as dictionaries

        Examples:
            >>> logger = SQLiteAuditLogger()
            >>> # Get all failed attempts by user
            >>> failures = logger.query(user_id="user123", success=False)
            >>> # Get last 10 MCP calls
            >>> recent = logger.query(action="mcp_call", limit=10)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Build query
                where_clauses = []
                params = []

                if user_id:
                    where_clauses.append("user_id = ?")
                    params.append(user_id)

                if action:
                    where_clauses.append("action = ?")
                    params.append(action)

                if mcp_name:
                    where_clauses.append("mcp_name = ?")
                    params.append(mcp_name)

                if success is not None:
                    where_clauses.append("success = ?")
                    params.append(1 if success else 0)

                if start_time:
                    where_clauses.append("timestamp >= ?")
                    params.append(start_time)

                if end_time:
                    where_clauses.append("timestamp <= ?")
                    params.append(end_time)

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                query_sql = f'''
                    SELECT * FROM audit_log
                    {where_sql}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                '''

                params.extend([limit, offset])

                cursor.execute(query_sql, params)

                rows = cursor.fetchall()
                return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"SQLite error querying audit logs: {e}")
            return []

    def get_stats(self, days: int = 7) -> Dict:
        """
        Get audit statistics for recent days.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with statistics

        Examples:
            >>> logger = SQLiteAuditLogger()
            >>> stats = logger.get_stats(days=7)
            >>> print(f"Total requests: {stats['total_requests']}")
            >>> print(f"Success rate: {stats['success_rate']}%")
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Calculate cutoff date
                cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                cutoff = cutoff.replace(day=cutoff.day - days)
                cutoff_str = cutoff.isoformat()

                # Total requests
                cursor.execute('''
                    SELECT
                        COUNT(*) as total,
                        SUM(success) as successful,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(DISTINCT mcp_name) as unique_mcps,
                        AVG(duration_ms) as avg_duration_ms
                    FROM audit_log
                    WHERE timestamp >= ?
                ''', (cutoff_str,))

                row = cursor.fetchone()

                total = row['total'] or 0
                successful = row['successful'] or 0
                unique_users = row['unique_users'] or 0
                unique_mcps = row['unique_mcps'] or 0
                avg_duration = row['avg_duration_ms'] or 0

                # Top actions
                cursor.execute('''
                    SELECT action, COUNT(*) as count
                    FROM audit_log
                    WHERE timestamp >= ?
                    GROUP BY action
                    ORDER BY count DESC
                    LIMIT 10
                ''', (cutoff_str,))

                top_actions = [{"action": row['action'], "count": row['count']} for row in cursor.fetchall()]

                # Top users
                cursor.execute('''
                    SELECT user_id, COUNT(*) as count
                    FROM audit_log
                    WHERE timestamp >= ? AND user_id IS NOT NULL
                    GROUP BY user_id
                    ORDER BY count DESC
                    LIMIT 10
                ''', (cutoff_str,))

                top_users = [{"user_id": row['user_id'], "count": row['count']} for row in cursor.fetchall()]

                # Top MCPs
                cursor.execute('''
                    SELECT mcp_name, COUNT(*) as count
                    FROM audit_log
                    WHERE timestamp >= ? AND mcp_name IS NOT NULL
                    GROUP BY mcp_name
                    ORDER BY count DESC
                    LIMIT 10
                ''', (cutoff_str,))

                top_mcps = [{"mcp": row['mcp_name'], "count": row['count']} for row in cursor.fetchall()]

                return {
                    "period_days": days,
                    "total_requests": total,
                    "successful_requests": successful,
                    "failed_requests": total - successful,
                    "success_rate": round((successful / total * 100) if total > 0 else 0, 2),
                    "unique_users": unique_users,
                    "unique_mcps": unique_mcps,
                    "avg_duration_ms": round(avg_duration, 2),
                    "top_actions": top_actions,
                    "top_users": top_users,
                    "top_mcps": top_mcps
                }

        except sqlite3.Error as e:
            logger.error(f"SQLite error getting stats: {e}")
            return {}

    def cleanup_old_logs(self, days: int = 90) -> int:
        """
        Delete audit logs older than specified days.

        Args:
            days: Keep logs newer than this many days

        Returns:
            Number of rows deleted

        Examples:
            >>> logger = SQLiteAuditLogger()
            >>> deleted = logger.cleanup_old_logs(days=90)
            >>> print(f"Deleted {deleted} old audit logs")
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cutoff = datetime.utcnow().replace(day=datetime.utcnow().day - days)
                cutoff_str = cutoff.isoformat()

                cursor.execute('''
                    DELETE FROM audit_log
                    WHERE timestamp < ?
                ''', (cutoff_str,))

                conn.commit()
                deleted = cursor.rowcount

                logger.info(f"Deleted {deleted} audit logs older than {days} days")
                return deleted

        except sqlite3.Error as e:
            logger.error(f"SQLite error cleaning up logs: {e}")
            return 0


# Convenience function for testing
def test_audit_logger():
    """Test the audit logger."""
    import tempfile
    import os

    # Use temporary database
    temp_db = tempfile.mktemp(suffix=".db")

    try:
        print(f"✅ Creating test database: {temp_db}")
        logger_instance = SQLiteAuditLogger(temp_db)

        # Test logging
        print("\n🧪 Testing audit logging:")

        # Successful MCP call
        id1 = logger_instance.log(
            action="mcp_call",
            user_id="user123",
            mcp_name="google-workspace",
            success=True,
            details={"method": "gmail.send", "to": "test@example.com"},
            duration_ms=250
        )
        print(f"  ✅ Logged successful MCP call (ID: {id1})")

        # Failed MCP call
        id2 = logger_instance.log(
            action="mcp_call",
            user_id="user123",
            mcp_name="slack",
            success=False,
            level="ERROR",
            error_message="Channel not found",
            duration_ms=100
        )
        print(f"  ✅ Logged failed MCP call (ID: {id2})")

        # Authentication attempt
        id3 = logger_instance.log(
            action="auth_attempt",
            user_id="user456",
            success=True,
            ip_address="192.168.1.1",
            metadata={"method": "api_key"}
        )
        print(f"  ✅ Logged auth attempt (ID: {id3})")

        # Test querying
        print("\n🔍 Testing queries:")

        # All logs for user123
        logs = logger_instance.query(user_id="user123")
        print(f"  ✅ Found {len(logs)} logs for user123")

        # Failed attempts
        failures = logger_instance.query(success=False)
        print(f"  ✅ Found {len(failures)} failed attempts")

        # MCP calls
        mcp_logs = logger_instance.query(action="mcp_call")
        print(f"  ✅ Found {len(mcp_logs)} MCP calls")

        # Test statistics
        print("\n📊 Testing statistics:")
        stats = logger_instance.get_stats(days=1)
        print(f"  Total requests: {stats['total_requests']}")
        print(f"  Success rate: {stats['success_rate']}%")
        print(f"  Unique users: {stats['unique_users']}")
        print(f"  Avg duration: {stats['avg_duration_ms']}ms")

        print("\n✅ All tests passed!")

    finally:
        # Cleanup
        if os.path.exists(temp_db):
            os.remove(temp_db)
            print(f"🧹 Cleaned up test database")


if __name__ == "__main__":
    # Run tests if executed directly
    test_audit_logger()
