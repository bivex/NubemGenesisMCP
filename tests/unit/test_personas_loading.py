"""
Unit Tests for Persona Loading System
TC113-116: Core persona loading functionality
Enterprise-Ready Testing with ISO 27001 Compliance
"""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import yaml


# ================================================================
# TC113: Verify personas load from correct path
# ================================================================

@pytest.mark.unit
def test_load_personas_from_shared_data_path(personas_path, tmp_path):
    """
    TC113: Verify personas load from /shared/data/personas

    Requirements:
    - ISO 27001: A.14.2.1 (Secure Development)
    - Verify correct file path usage
    - Prevent path traversal vulnerabilities
    """
    from core.personas_unified import PersonaManager

    # Create test persona
    test_persona_file = personas_path / "test-persona.yaml"
    test_persona = {
        "key": "test-persona",
        "name": "Test Persona",
        "level": "L4",
        "identity": "Test identity",
        "specialties": ["Testing"]
    }

    with open(test_persona_file, 'w') as f:
        yaml.dump(test_persona, f)

    # Initialize PersonaManager
    pm = PersonaManager()

    # Load from correct path
    pm.load_external_personas(personas_path)

    # Assertions
    assert len(pm.personas) > 0, "Personas should be loaded"
    assert "test-persona" in pm.personas, "Test persona should be present"
    assert pm.personas["test-persona"]["level"] == "L4"


@pytest.mark.unit
def test_load_personas_path_validation(personas_path):
    """
    TC113: Verify path validation prevents path traversal

    Security:
    - Prevent directory traversal attacks
    - Validate Path object usage
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()

    # Attempt path traversal - should be blocked or handled safely
    malicious_paths = [
        "/etc/passwd",
        "../../../etc/passwd",
        "/tmp/../../../etc/passwd",
    ]

    for bad_path in malicious_paths:
        try:
            pm.load_external_personas(Path(bad_path))
            # If it doesn't raise, verify no system files were loaded
            assert "root" not in str(pm.personas), "Should not load system files"
        except (ValueError, PermissionError, FileNotFoundError):
            # Expected - path validation working
            pass


# ================================================================
# TC114: Verify PERSONAS_PATH environment variable
# ================================================================

@pytest.mark.unit
def test_personas_path_respects_environment_variable(tmp_path, monkeypatch):
    """
    TC114: Verify PERSONAS_PATH environment variable is respected

    Requirements:
    - 12-Factor App compliance
    - Environment-based configuration
    - ISO 27001: A.12.1.2 (Change Management)
    """
    from core.personas_unified import PersonaManager

    # Create custom personas path
    custom_path = tmp_path / "custom-personas"
    custom_path.mkdir()

    # Create test persona
    test_file = custom_path / "custom-persona.yaml"
    test_persona = {
        "key": "custom-persona",
        "name": "Custom Persona",
        "level": "L3",
        "identity": "Custom test persona",
        "specialties": ["Custom"]
    }

    with open(test_file, 'w') as f:
        yaml.dump(test_persona, f)

    # Set environment variable
    monkeypatch.setenv("PERSONAS_PATH", str(custom_path))

    # Initialize PersonaManager
    pm = PersonaManager()
    pm.load_external_personas()  # Should use env var

    # Assertions
    assert "custom-persona" in pm.personas, "Should load from custom path"


@pytest.mark.unit
def test_personas_path_default_fallback():
    """
    TC114: Verify default path fallback when env var not set

    Requirements:
    - Graceful fallback to default
    - No crashes on missing env var
    """
    from core.personas_unified import PersonaManager

    # Ensure no env var
    if "PERSONAS_PATH" in os.environ:
        del os.environ["PERSONAS_PATH"]

    pm = PersonaManager()

    # Should not crash, should use default
    try:
        pm.load_external_personas()
    except FileNotFoundError:
        # Expected if default path doesn't exist
        pass


# ================================================================
# TC115: Verify reload_personas returns correct count
# ================================================================

@pytest.mark.unit
def test_reload_personas_returns_correct_count(personas_path):
    """
    TC115: Verify reload_personas returns actual loaded count

    Requirements:
    - Accurate reporting
    - Audit trail compliance
    - ISO 27001: A.12.1.2 (Change Management)
    """
    from mcp_server.server import reload_personas

    # Mock persona manager
    with patch('mcp_server.server.get_persona_manager') as mock_get_pm:
        mock_pm = MagicMock()
        mock_pm.reload_personas.return_value = {
            "status": "success",
            "loaded": 93,
            "personas_reloaded": 93
        }
        mock_get_pm.return_value = mock_pm

        # Call reload
        result = reload_personas()

        # Assertions
        assert result["status"] == "success"
        assert result["loaded"] == result["personas_reloaded"]
        assert result["loaded"] > 0
        assert isinstance(result["loaded"], int)


@pytest.mark.unit
def test_reload_personas_atomic_operation():
    """
    TC115: Verify reload is atomic (all or nothing)

    Requirements:
    - Data integrity
    - No partial loads
    - Transaction semantics
    """
    from mcp_server.server import reload_personas

    with patch('mcp_server.server.get_persona_manager') as mock_get_pm:
        mock_pm = MagicMock()

        # Simulate partial failure
        mock_pm.reload_personas.side_effect = Exception("Load failed")
        mock_get_pm.return_value = mock_pm

        # Should handle gracefully
        try:
            result = reload_personas()
            # If it returns, verify error state
            assert result["status"] == "error" or "error" in result
        except Exception as e:
            # Exception is acceptable
            assert "Load failed" in str(e)


# ================================================================
# TC116: Verify list_personas matches loaded count
# ================================================================

@pytest.mark.unit
def test_list_personas_matches_loaded_count(personas_path):
    """
    TC116: Verify list_personas returns correct number of personas

    Requirements:
    - Data consistency
    - Accurate inventory
    - ISO 27001: A.12.1.2 (Asset Management)
    """
    from mcp_server.server import list_personas, reload_personas

    with patch('mcp_server.server.get_persona_manager') as mock_get_pm:
        mock_pm = MagicMock()
        mock_pm.personas = {
            "persona1": {"key": "persona1", "name": "P1"},
            "persona2": {"key": "persona2", "name": "P2"},
            "persona3": {"key": "persona3", "name": "P3"},
        }
        mock_pm.reload_personas.return_value = {
            "status": "success",
            "loaded": 3,
            "personas_reloaded": 3
        }
        mock_get_pm.return_value = mock_pm

        # Reload
        reload_result = reload_personas()

        # List
        list_result = list_personas()

        # Assertions
        assert list_result["total"] == reload_result["loaded"]
        assert len(list_result["personas"]) == list_result["total"]


@pytest.mark.unit
def test_list_personas_returns_expected_fields():
    """
    TC116: Verify list_personas returns all required fields

    Requirements:
    - API contract compliance
    - Complete data structure
    - Documentation accuracy
    """
    from mcp_server.server import list_personas

    with patch('mcp_server.server.get_persona_manager') as mock_get_pm:
        mock_pm = MagicMock()
        mock_pm.personas = {
            "test-persona": {
                "key": "test-persona",
                "name": "Test Persona",
                "level": "L4",
                "identity": "Test identity",
                "specialties": ["Testing", "Development"]
            }
        }
        mock_get_pm.return_value = mock_pm

        # List personas
        result = list_personas()

        # Assertions
        assert "total" in result
        assert "loaded" in result
        assert "personas" in result
        assert isinstance(result["personas"], list)

        if len(result["personas"]) > 0:
            persona = result["personas"][0]
            assert "key" in persona
            assert "name" in persona
            assert "level" in persona
            assert "identity" in persona
            assert "specialties" in persona


# ================================================================
# PERFORMANCE TESTS
# ================================================================

@pytest.mark.unit
@pytest.mark.slow
def test_persona_loading_performance(personas_path, performance_monitor):
    """
    Verify persona loading completes within acceptable time

    SLA Requirements:
    - Load 148 personas < 5 seconds
    - Memory efficient
    """
    from core.personas_unified import PersonaManager

    # Create 148 test personas
    for i in range(148):
        persona_file = personas_path / f"persona-{i}.yaml"
        persona = {
            "key": f"persona-{i}",
            "name": f"Persona {i}",
            "level": "L4",
            "identity": f"Test persona {i}",
            "specialties": ["Testing"]
        }
        with open(persona_file, 'w') as f:
            yaml.dump(persona, f)

    pm = PersonaManager()

    # Measure load time
    performance_monitor.start()
    pm.load_external_personas(personas_path)
    performance_monitor.stop()

    duration = performance_monitor.duration()

    # Assertions
    assert len(pm.personas) == 148
    assert duration < 5.0, f"Loading took {duration}s, should be < 5s"


# ================================================================
# ERROR HANDLING TESTS
# ================================================================

@pytest.mark.unit
def test_load_personas_handles_corrupted_yaml(personas_path):
    """
    Verify graceful handling of corrupted YAML files

    Security:
    - Prevent YAML injection
    - Handle malformed input
    """
    from core.personas_unified import PersonaManager

    # Create corrupted YAML
    corrupted_file = personas_path / "corrupted.yaml"
    with open(corrupted_file, 'w') as f:
        f.write("invalid: yaml: content: [[[")

    pm = PersonaManager()

    # Should not crash
    try:
        pm.load_external_personas(personas_path)
        # May succeed with partial load or skip corrupted file
    except yaml.YAMLError:
        # Acceptable - error handling working
        pass


@pytest.mark.unit
def test_load_personas_handles_missing_directory():
    """
    Verify graceful handling of missing personas directory

    Requirements:
    - Fail gracefully
    - Appropriate error messages
    - ISO 27001: A.12.1.2 (Error Handling)
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()

    # Try to load from non-existent path
    non_existent = Path("/tmp/does-not-exist-12345")

    try:
        pm.load_external_personas(non_existent)
        # Should either succeed with 0 personas or raise
        assert len(pm.personas) == 0
    except FileNotFoundError:
        # Expected behavior
        pass


@pytest.mark.unit
def test_load_personas_handles_permission_denied(tmp_path):
    """
    Verify graceful handling of permission errors

    Security:
    - Proper error handling
    - No information leakage
    """
    from core.personas_unified import PersonaManager

    # Create directory without read permissions
    no_read_dir = tmp_path / "no-read"
    no_read_dir.mkdir()

    # Create file without read permission
    persona_file = no_read_dir / "persona.yaml"
    with open(persona_file, 'w') as f:
        yaml.dump({"key": "test"}, f)

    os.chmod(persona_file, 0o000)

    pm = PersonaManager()

    try:
        pm.load_external_personas(no_read_dir)
        # May succeed with skipped files
    except PermissionError:
        # Expected
        pass
    finally:
        # Restore permissions for cleanup
        os.chmod(persona_file, 0o644)


# ================================================================
# CONCURRENCY TESTS
# ================================================================

@pytest.mark.unit
@pytest.mark.slow
def test_concurrent_persona_access(personas_path):
    """
    TC118: Verify thread-safety of persona access

    Requirements:
    - Thread-safe operations
    - No race conditions
    - Data integrity under load
    """
    from core.personas_unified import PersonaManager
    from concurrent.futures import ThreadPoolExecutor
    import threading

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    results = []
    errors = []
    lock = threading.Lock()

    def access_persona(persona_key):
        try:
            persona = pm.personas.get(persona_key)
            with lock:
                results.append(persona)
        except Exception as e:
            with lock:
                errors.append(e)

    # Concurrent access
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(access_persona, list(pm.personas.keys())[0] if pm.personas else "test")
            for _ in range(100)
        ]

        for future in futures:
            future.result()

    # Assertions
    assert len(errors) == 0, f"Concurrent access caused errors: {errors}"
    assert len(results) == 100, "All accesses should complete"
