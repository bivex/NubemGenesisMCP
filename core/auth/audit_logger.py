"""
Audit Logger for MCP Server
Logs all authentication and authorization events for security auditing.
"""

import logging
import json
from datetime import datetime
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit logger for security events.

    Logs:
    - Authentication attempts (success/failure)
    - Authorization decisions (allow/deny)
    - MCP tool invocations
    - Rate limit violations
    """

    def __init__(self, log_to_file: bool = True, log_file: str = "logs/audit.log"):
        """
        Initialize audit logger.

        Args:
            log_to_file: Whether to log to file
            log_file: Path to audit log file
        """
        self.audit_logger = logging.getLogger("mcp_audit")
        self.audit_logger.setLevel(logging.INFO)

        # Prevent duplicate handlers
        if not self.audit_logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s - AUDIT - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            self.audit_logger.addHandler(console_handler)

            # File handler (if enabled)
            if log_to_file:
                try:
                    import os
                    os.makedirs(os.path.dirname(log_file), exist_ok=True)

                    file_handler = logging.FileHandler(log_file)
                    file_handler.setLevel(logging.INFO)
                    file_formatter = logging.Formatter(
                        '%(asctime)s - AUDIT - %(levelname)s - %(message)s'
                    )
                    file_handler.setFormatter(file_formatter)
                    self.audit_logger.addHandler(file_handler)
                except Exception as e:
                    logger.warning(f"Could not create audit log file: {e}")

        logger.info("✅ AuditLogger initialized")

    def _create_audit_entry(
        self,
        event_type: str,
        user_email: Optional[str] = None,
        user_role: Optional[str] = None,
        api_key_prefix: Optional[str] = None,
        tool_name: Optional[str] = None,
        mcp_name: Optional[str] = None,
        operation: Optional[str] = None,
        status: str = "unknown",
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        **extra_fields
    ) -> Dict[str, Any]:
        """
        Create structured audit log entry.

        Args:
            event_type: Type of event (auth_attempt, auth_success, auth_failed,
                       permission_check, permission_denied, tool_invocation, rate_limit_exceeded)
            user_email: User email
            user_role: User role
            api_key_prefix: First 15 chars of API key (for identification, not security)
            tool_name: MCP tool name
            mcp_name: MCP name
            operation: Operation type (read, write, delete, execute)
            status: Status (success, failed, denied, allowed)
            reason: Reason for denial or failure
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request tracking ID
            **extra_fields: Additional fields

        Returns:
            Audit log entry dict
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "status": status
        }

        if user_email:
            entry["user_email"] = user_email
        if user_role:
            entry["user_role"] = user_role
        if api_key_prefix:
            entry["api_key_prefix"] = api_key_prefix
        if tool_name:
            entry["tool_name"] = tool_name
        if mcp_name:
            entry["mcp_name"] = mcp_name
        if operation:
            entry["operation"] = operation
        if reason:
            entry["reason"] = reason
        if ip_address:
            entry["ip_address"] = ip_address
        if user_agent:
            entry["user_agent"] = user_agent
        if request_id:
            entry["request_id"] = request_id

        # Add extra fields
        entry.update(extra_fields)

        return entry

    def log_auth_attempt(
        self,
        api_key_prefix: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log authentication attempt."""
        entry = self._create_audit_entry(
            event_type="auth_attempt",
            api_key_prefix=api_key_prefix,
            status="attempt",
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.audit_logger.info(json.dumps(entry))

    def log_auth_success(
        self,
        user_email: str,
        user_role: str,
        api_key_prefix: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log successful authentication."""
        entry = self._create_audit_entry(
            event_type="auth_success",
            user_email=user_email,
            user_role=user_role,
            api_key_prefix=api_key_prefix,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.audit_logger.info(json.dumps(entry))

    def log_auth_failed(
        self,
        api_key_prefix: str,
        reason: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log failed authentication."""
        entry = self._create_audit_entry(
            event_type="auth_failed",
            api_key_prefix=api_key_prefix,
            status="failed",
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.audit_logger.warning(json.dumps(entry))

    def log_permission_check(
        self,
        user_email: str,
        user_role: str,
        tool_name: str,
        mcp_name: Optional[str] = None,
        operation: str = "read",
        allowed: bool = True,
        reason: Optional[str] = None
    ):
        """Log permission check (allow or deny)."""
        entry = self._create_audit_entry(
            event_type="permission_check",
            user_email=user_email,
            user_role=user_role,
            tool_name=tool_name,
            mcp_name=mcp_name,
            operation=operation,
            status="allowed" if allowed else "denied",
            reason=reason
        )

        if allowed:
            self.audit_logger.info(json.dumps(entry))
        else:
            self.audit_logger.warning(json.dumps(entry))

    def log_tool_invocation(
        self,
        user_email: str,
        user_role: str,
        tool_name: str,
        mcp_name: Optional[str] = None,
        operation: str = "read",
        status: str = "success",
        execution_time_ms: Optional[float] = None,
        error: Optional[str] = None
    ):
        """Log tool invocation."""
        entry = self._create_audit_entry(
            event_type="tool_invocation",
            user_email=user_email,
            user_role=user_role,
            tool_name=tool_name,
            mcp_name=mcp_name,
            operation=operation,
            status=status,
            execution_time_ms=execution_time_ms,
            error=error
        )

        if status == "success":
            self.audit_logger.info(json.dumps(entry))
        else:
            self.audit_logger.error(json.dumps(entry))

    def log_rate_limit_exceeded(
        self,
        user_email: str,
        user_role: str,
        api_key_prefix: str,
        ip_address: Optional[str] = None
    ):
        """Log rate limit violation."""
        entry = self._create_audit_entry(
            event_type="rate_limit_exceeded",
            user_email=user_email,
            user_role=user_role,
            api_key_prefix=api_key_prefix,
            status="blocked",
            reason="Rate limit exceeded",
            ip_address=ip_address
        )
        self.audit_logger.warning(json.dumps(entry))

    def log_security_event(
        self,
        event_type: str,
        severity: str = "warning",
        details: Optional[Dict] = None
    ):
        """Log generic security event."""
        entry = self._create_audit_entry(
            event_type=event_type,
            status=severity,
            **(details or {})
        )

        if severity == "critical":
            self.audit_logger.critical(json.dumps(entry))
        elif severity == "error":
            self.audit_logger.error(json.dumps(entry))
        elif severity == "warning":
            self.audit_logger.warning(json.dumps(entry))
        else:
            self.audit_logger.info(json.dumps(entry))


# Global instance
_global_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get or create global audit logger instance.

    Returns:
        AuditLogger instance
    """
    global _global_audit_logger

    if _global_audit_logger is None:
        _global_audit_logger = AuditLogger()

    return _global_audit_logger
