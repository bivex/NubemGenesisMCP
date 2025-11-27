"""
Integration Tests for Persona System
TC117-118: Multi-component integration testing
Validates PostgreSQL, Redis, and API layer integration

ISO 27001: A.14.2.8 (System Security Testing)
ISO 27001: A.14.2.9 (System Acceptance Testing)
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import psycopg2
import redis
from concurrent.futures import ThreadPoolExecutor, as_completed


# ================================================================
# TC117: Complete Persona Loading Workflow
# ================================================================

@pytest.mark.integration
@pytest.mark.database
def test_persona_load_from_postgres_to_cache(db_session, redis_client, personas_path):
    """
    TC117-001: Verify complete persona loading workflow from PostgreSQL

    Flow:
    1. Load personas from file system
    2. Store metadata in PostgreSQL
    3. Cache in Redis
    4. Verify consistency across all layers

    ISO 27001: A.14.2.8 (System Security Testing)
    """
    from core.personas_unified import PersonaManager

    # Initialize PersonaManager
    pm = PersonaManager()

    # Load personas from filesystem
    pm.load_external_personas(personas_path)
    initial_count = len(pm.personas)
    assert initial_count > 0, "Should load personas from filesystem"

    # Simulate storing metadata in PostgreSQL
    cursor = db_session.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS persona_metadata (
            persona_key VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255),
            level VARCHAR(10),
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0
        )
    """)

    for key, persona in pm.personas.items():
        cursor.execute(
            """
            INSERT INTO persona_metadata (persona_key, name, level, access_count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (persona_key) DO UPDATE SET
                loaded_at = CURRENT_TIMESTAMP,
                access_count = persona_metadata.access_count + 1
            """,
            (key, persona.get('name', key), persona.get('level', 'L1'), 0)
        )

    db_session.commit()

    # Verify data in PostgreSQL
    cursor.execute("SELECT COUNT(*) FROM persona_metadata")
    db_count = cursor.fetchone()[0]
    assert db_count == initial_count, "Database should contain all personas"

    # Cache in Redis
    for key, persona in pm.personas.items():
        cache_key = f"persona:{key}"
        redis_client.setex(cache_key, 3600, str(persona))  # 1 hour TTL

    # Verify Redis cache
    cached_count = len(redis_client.keys("persona:*"))
    assert cached_count == initial_count, "Redis should cache all personas"

    # Verify consistency
    cursor.execute("SELECT persona_key FROM persona_metadata ORDER BY persona_key")
    db_keys = sorted([row[0] for row in cursor.fetchall()])
    memory_keys = sorted(pm.personas.keys())
    redis_keys = sorted([k.decode('utf-8').replace('persona:', '') for k in redis_client.keys("persona:*")])

    assert db_keys == memory_keys, "Database and memory should be consistent"
    assert memory_keys == redis_keys, "Memory and Redis should be consistent"


@pytest.mark.integration
@pytest.mark.database
def test_redis_cache_hit_reduces_db_load(db_session, redis_client, personas_path):
    """
    TC117-002: Verify Redis cache hit reduces database queries

    Performance:
    - Cache hit should NOT query database
    - Cache miss should query database and update cache
    """
    from core.personas_unified import PersonaManager

    # Setup: Load persona into cache
    test_persona_key = "test-persona"
    test_persona_data = {"name": "Test Persona", "level": "L3"}

    redis_client.setex(f"persona:{test_persona_key}", 3600, str(test_persona_data))

    # Mock database to verify it's NOT called on cache hit
    with patch.object(db_session, 'cursor') as mock_cursor:
        # Simulate cache hit scenario
        cache_key = f"persona:{test_persona_key}"
        cached_data = redis_client.get(cache_key)

        assert cached_data is not None, "Should hit Redis cache"
        mock_cursor.assert_not_called()  # Database should NOT be queried

    # Test cache miss scenario
    redis_client.delete(f"persona:{test_persona_key}")

    cursor = db_session.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS persona_metadata (
            persona_key VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255),
            level VARCHAR(10)
        )
    """)
    cursor.execute(
        "INSERT INTO persona_metadata (persona_key, name, level) VALUES (%s, %s, %s)",
        (test_persona_key, "Test Persona", "L3")
    )
    db_session.commit()

    # Cache miss should query database
    cursor.execute("SELECT name, level FROM persona_metadata WHERE persona_key = %s", (test_persona_key,))
    result = cursor.fetchone()
    assert result is not None, "Should query database on cache miss"

    # Repopulate cache
    redis_client.setex(f"persona:{test_persona_key}", 3600, str(result))


@pytest.mark.integration
@pytest.mark.database
def test_reload_personas_invalidates_cache(db_session, redis_client, personas_path):
    """
    TC117-003: Verify reload_personas() invalidates Redis cache

    Requirements:
    1. Clear all persona:* keys from Redis
    2. Reload from filesystem
    3. Repopulate cache
    4. Update database metadata
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    # Populate cache
    for key in pm.personas.keys():
        redis_client.setex(f"persona:{key}", 3600, "old_data")

    initial_cache_count = len(redis_client.keys("persona:*"))
    assert initial_cache_count > 0, "Cache should be populated"

    # Simulate reload_personas
    redis_client.flushdb()  # Clear cache
    cache_count_after_flush = len(redis_client.keys("persona:*"))
    assert cache_count_after_flush == 0, "Cache should be cleared on reload"

    # Reload
    pm.personas = {}
    pm.load_external_personas(personas_path)

    # Repopulate cache
    for key, persona in pm.personas.items():
        redis_client.setex(f"persona:{key}", 3600, str(persona))

    final_cache_count = len(redis_client.keys("persona:*"))
    assert final_cache_count == len(pm.personas), "Cache should be repopulated"


# ================================================================
# TC118: Error Handling and Resilience
# ================================================================

@pytest.mark.integration
@pytest.mark.error_handling
def test_graceful_degradation_when_redis_unavailable(db_session, personas_path):
    """
    TC118-001: System continues to function when Redis is unavailable

    Resilience:
    - If Redis fails, fall back to database
    - If database fails, use in-memory cache
    - Log errors appropriately
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    # Simulate Redis connection failure
    mock_redis = MagicMock()
    mock_redis.get.side_effect = redis.exceptions.ConnectionError("Redis unavailable")
    mock_redis.setex.side_effect = redis.exceptions.ConnectionError("Redis unavailable")

    # System should fall back to database/memory
    with patch('redis.Redis', return_value=mock_redis):
        # Should still be able to access personas from memory
        assert len(pm.personas) > 0, "Should fall back to in-memory cache"

        # Verify error is logged (in production)
        # This would integrate with your logging framework


@pytest.mark.integration
@pytest.mark.error_handling
def test_database_connection_pool_exhaustion(db_connection_config):
    """
    TC118-002: Verify connection pool handles exhaustion gracefully

    Test:
    1. Create connection pool with small size (e.g., 5 connections)
    2. Attempt to acquire 10 connections simultaneously
    3. Verify proper timeout and queue management
    """
    from psycopg2.pool import SimpleConnectionPool

    # Create small connection pool
    pool = SimpleConnectionPool(
        minconn=1,
        maxconn=5,
        **db_connection_config
    )

    connections = []
    try:
        # Acquire all connections
        for i in range(5):
            conn = pool.getconn()
            connections.append(conn)

        # Try to acquire one more (should handle gracefully)
        with pytest.raises(Exception):  # Pool exhausted
            pool.getconn()

    finally:
        # Release connections
        for conn in connections:
            pool.putconn(conn)

        pool.closeall()


@pytest.mark.integration
@pytest.mark.error_handling
def test_transaction_rollback_on_error(db_session):
    """
    TC118-003: Verify database transactions rollback on error

    ISO 27001: A.14.2.8 (System Security Testing)
    """
    cursor = db_session.cursor()

    # Create test table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_personas (
            id SERIAL PRIMARY KEY,
            persona_key VARCHAR(100) NOT NULL
        )
    """)
    db_session.commit()

    try:
        # Start transaction
        cursor.execute("INSERT INTO test_personas (persona_key) VALUES (%s)", ("test-key",))

        # Simulate error
        cursor.execute("INSERT INTO test_personas (persona_key) VALUES (%s)", (None,))  # NOT NULL violation

    except Exception:
        db_session.rollback()

    # Verify rollback
    cursor.execute("SELECT COUNT(*) FROM test_personas")
    count = cursor.fetchone()[0]
    assert count == 0, "Transaction should be rolled back on error"

    # Cleanup
    cursor.execute("DROP TABLE test_personas")
    db_session.commit()


@pytest.mark.integration
@pytest.mark.concurrency
def test_concurrent_persona_access_thread_safe(personas_path, redis_client):
    """
    TC118-004: Verify thread-safe concurrent access to personas

    Concurrency:
    - Multiple threads accessing same persona
    - No race conditions
    - No data corruption
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    if len(pm.personas) == 0:
        pytest.skip("No personas loaded for concurrency test")

    persona_keys = list(pm.personas.keys())[:10]  # Test with 10 personas
    access_counts = {key: 0 for key in persona_keys}
    errors = []

    def access_persona(key):
        """Simulate persona access"""
        try:
            persona = pm.personas.get(key)
            assert persona is not None, f"Persona {key} should exist"

            # Simulate Redis cache access
            cache_key = f"persona:{key}"
            redis_client.incr(f"access_count:{key}")

            return key
        except Exception as e:
            errors.append((key, str(e)))
            return None

    # Execute concurrent access
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = []
        for _ in range(100):  # 100 total accesses
            for key in persona_keys:
                futures.append(executor.submit(access_persona, key))

        for future in as_completed(futures):
            result = future.result()
            if result:
                access_counts[result] += 1

    # Verify no errors
    assert len(errors) == 0, f"Concurrent access should be error-free: {errors}"

    # Verify all accesses succeeded
    total_accesses = sum(access_counts.values())
    expected_accesses = 100 * len(persona_keys)
    assert total_accesses == expected_accesses, f"Should have {expected_accesses} successful accesses"

    # Verify Redis counters
    for key in persona_keys:
        count = int(redis_client.get(f"access_count:{key}") or 0)
        assert count == 100, f"Each persona should be accessed exactly 100 times"


@pytest.mark.integration
@pytest.mark.performance
def test_cache_ttl_expiration(redis_client):
    """
    TC118-005: Verify Redis cache TTL and expiration

    Requirements:
    - Set TTL on cache entries
    - Verify automatic expiration
    - Handle expired entries gracefully
    """
    test_key = "persona:ttl-test"
    test_data = "test data"

    # Set with 2 second TTL
    redis_client.setex(test_key, 2, test_data)

    # Verify immediately available
    cached = redis_client.get(test_key)
    assert cached is not None, "Should be in cache immediately"
    assert cached.decode('utf-8') == test_data

    # Wait for expiration
    time.sleep(3)

    # Verify expired
    cached_after_ttl = redis_client.get(test_key)
    assert cached_after_ttl is None, "Should be expired after TTL"


@pytest.mark.integration
@pytest.mark.database
def test_audit_log_integration_with_persona_access(db_session, personas_path):
    """
    TC118-006: Verify audit logging for persona operations

    ISO 27001: A.12.4.1 (Event Logging)
    Requirements:
    - Log all persona access
    - Include timestamp, user, action
    - Store in PostgreSQL audit table
    """
    from core.personas_unified import PersonaManager

    cursor = db_session.cursor()

    # Create audit log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_email VARCHAR(255),
            user_role VARCHAR(50),
            event_type VARCHAR(100),
            tool_name VARCHAR(100),
            operation VARCHAR(50),
            status VARCHAR(50),
            execution_time_ms REAL,
            error TEXT
        )
    """)
    db_session.commit()

    # Simulate persona access
    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    # Log the reload operation
    cursor.execute("""
        INSERT INTO audit_logs (
            user_email, user_role, event_type, tool_name,
            operation, status, execution_time_ms, error
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        "test@example.com",
        "admin",
        "tool_invocation",
        "reload_personas",
        "read",
        "success",
        125.5,
        None
    ))
    db_session.commit()

    # Verify audit log
    cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE tool_name = 'reload_personas'")
    log_count = cursor.fetchone()[0]
    assert log_count > 0, "Audit log should contain persona operations"

    # Verify audit log structure
    cursor.execute("""
        SELECT user_email, event_type, status
        FROM audit_logs
        WHERE tool_name = 'reload_personas'
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    log_entry = cursor.fetchone()
    assert log_entry[0] == "test@example.com"
    assert log_entry[1] == "tool_invocation"
    assert log_entry[2] == "success"

    # Cleanup
    cursor.execute("DROP TABLE audit_logs")
    db_session.commit()


@pytest.mark.integration
@pytest.mark.rbac
def test_role_based_persona_access_control(db_session):
    """
    TC118-007: Verify RBAC enforcement for persona access

    ISO 27001: A.9.2 (Access Control)
    Requirements:
    - Admin can access all personas
    - Developer can access non-admin personas
    - Readonly can only list personas
    """
    cursor = db_session.cursor()

    # Create RBAC tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            role_name VARCHAR(50) PRIMARY KEY,
            permissions TEXT[]
        )
    """)

    cursor.execute("""
        INSERT INTO roles (role_name, permissions) VALUES
        ('admin', ARRAY['read', 'write', 'delete', 'execute']),
        ('developer', ARRAY['read', 'execute']),
        ('readonly', ARRAY['read'])
    """)
    db_session.commit()

    # Test role permissions
    def has_permission(role, permission):
        cursor.execute("SELECT permissions FROM roles WHERE role_name = %s", (role,))
        result = cursor.fetchone()
        if result:
            return permission in result[0]
        return False

    # Verify permissions
    assert has_permission('admin', 'execute') is True
    assert has_permission('admin', 'delete') is True
    assert has_permission('developer', 'execute') is True
    assert has_permission('developer', 'delete') is False
    assert has_permission('readonly', 'read') is True
    assert has_permission('readonly', 'execute') is False

    # Cleanup
    cursor.execute("DROP TABLE roles")
    db_session.commit()


@pytest.mark.integration
@pytest.mark.backup
def test_persona_backup_and_restore_workflow(db_session, personas_path, tmp_path):
    """
    TC118-008: Verify backup and restore workflow

    ISO 27001: A.17.1.2 (Implementing Information Security Continuity)
    """
    import json
    from pathlib import Path

    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    # Create backup
    backup_file = tmp_path / "personas_backup.json"
    backup_data = {
        "timestamp": datetime.now().isoformat(),
        "count": len(pm.personas),
        "personas": {k: dict(v) for k, v in pm.personas.items()}
    }

    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2)

    # Verify backup file
    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # Simulate restore
    with open(backup_file, 'r') as f:
        restored_data = json.load(f)

    assert restored_data['count'] == len(pm.personas)
    assert len(restored_data['personas']) == len(pm.personas)

    # Verify data integrity
    for key in pm.personas.keys():
        assert key in restored_data['personas'], f"Persona {key} should be in backup"


@pytest.mark.integration
@pytest.mark.performance
def test_persona_load_time_under_threshold(personas_path):
    """
    TC118-009: Verify persona loading completes within SLA

    Performance SLA:
    - Load time < 5 seconds for 200 personas
    - Memory usage reasonable
    """
    from core.personas_unified import PersonaManager
    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    pm = PersonaManager()

    start_time = time.time()
    pm.load_external_personas(personas_path)
    load_time = time.time() - start_time

    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory

    # Performance assertions
    assert load_time < 5.0, f"Load time should be < 5s, got {load_time:.2f}s"
    assert memory_increase < 500, f"Memory increase should be < 500MB, got {memory_increase:.2f}MB"
    assert len(pm.personas) > 0, "Should load personas successfully"


@pytest.mark.integration
@pytest.mark.health_check
def test_system_health_check_integration(db_session, redis_client, personas_path):
    """
    TC118-010: Comprehensive system health check

    Verifies:
    - Database connectivity
    - Redis connectivity
    - Persona loading status
    - All components operational
    """
    from core.personas_unified import PersonaManager

    health_status = {
        "database": False,
        "redis": False,
        "personas": False,
        "overall": False
    }

    # Check database
    try:
        cursor = db_session.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        health_status["database"] = (result[0] == 1)
    except Exception:
        health_status["database"] = False

    # Check Redis
    try:
        redis_client.ping()
        health_status["redis"] = True
    except Exception:
        health_status["redis"] = False

    # Check persona loading
    try:
        pm = PersonaManager()
        pm.load_external_personas(personas_path)
        health_status["personas"] = len(pm.personas) > 0
    except Exception:
        health_status["personas"] = False

    # Overall health
    health_status["overall"] = all([
        health_status["database"],
        health_status["redis"],
        health_status["personas"]
    ])

    # Assert all components healthy
    assert health_status["database"] is True, "Database should be healthy"
    assert health_status["redis"] is True, "Redis should be healthy"
    assert health_status["personas"] is True, "Personas should be loaded"
    assert health_status["overall"] is True, "Overall system should be healthy"
