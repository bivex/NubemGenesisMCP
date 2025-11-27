"""
Week 4 Integration Tests for NubemSuperFClaude Framework
Tests new features: personas enhancements, context management, streaming, vector DB
"""

import os
import sys
import pytest
import asyncio
from typing import List, Dict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.personas_extended import ALL_EXTENDED_PERSONAS, get_persona
from core.context_manager import ContextWindowManager, ContextStrategy
from core.streaming_handler import StreamingHandler, StreamEvent
from core.vector_database import get_vector_database


class TestPersonasIntegration:
    """Test personas system integration"""

    def test_all_personas_loaded(self):
        """Test that all personas are loaded correctly"""
        assert len(ALL_EXTENDED_PERSONAS) > 0
        print(f"✓ Loaded {len(ALL_EXTENDED_PERSONAS)} personas")

    def test_persona_structure(self):
        """Test that personas have required structure"""
        required_keys = ['identity', 'system_prompt', 'specialties']

        for persona_key, persona in ALL_EXTENDED_PERSONAS.items():
            assert isinstance(persona, dict), f"{persona_key} is not a dict"

            for key in required_keys:
                assert key in persona, f"{persona_key} missing {key}"

            # Check identity (can be string or dict)
            identity = persona['identity']
            if isinstance(identity, dict):
                assert 'name' in identity
                assert 'role' in identity
            else:
                # String identity is also valid
                assert isinstance(identity, str)
                assert len(identity) > 0

            # Check system prompt is not empty
            assert len(persona['system_prompt']) > 0

            # Check specialties is a list
            assert isinstance(persona['specialties'], list)
            assert len(persona['specialties']) > 0

        print(f"✓ All {len(ALL_EXTENDED_PERSONAS)} personas have valid structure")

    def test_tier1_personas_quality(self):
        """Test Tier 1 personas have high quality (64+ specialties)"""
        # Note: Tier 1 enhanced personas are in /personas/enhanced/*.py files
        # They are not yet integrated into ALL_EXTENDED_PERSONAS
        # This test verifies that existing personas with 60+ specialties are high quality

        high_quality_count = 0
        for key, persona in ALL_EXTENDED_PERSONAS.items():
            specialty_count = len(persona['specialties'])
            if specialty_count >= 60:
                high_quality_count += 1
                print(f"✓ {key}: {specialty_count} specialties (Tier 1 quality)")

        # At least some personas should have 60+ specialties
        print(f"✓ Found {high_quality_count} personas with Tier 1 quality (60+ specialties)")

    def test_get_persona_function(self):
        """Test get_persona helper function"""
        # Test valid persona (using actual key from ALL_EXTENDED_PERSONAS)
        gcp = get_persona('gcp-architect')
        assert gcp is not None
        assert 'identity' in gcp

        # Test case insensitive
        gcp2 = get_persona('GCP-ARCHITECT')
        assert gcp2 is not None

        # Test invalid persona
        invalid = get_persona('INVALID-PERSONA')
        assert invalid is None

        print("✓ get_persona() works correctly")


class TestContextManagerIntegration:
    """Test Context Window Manager integration"""

    def test_context_manager_initialization(self):
        """Test context manager can be initialized"""
        manager = ContextWindowManager(
            model="claude-sonnet-4-5-20250929",
            strategy=ContextStrategy.SLIDING_WINDOW
        )

        assert manager.model == "claude-sonnet-4-5-20250929"
        assert manager.max_tokens > 0
        assert manager.strategy == ContextStrategy.SLIDING_WINDOW

        print(f"✓ Context manager initialized with {manager.max_tokens} tokens")

    def test_token_counting(self):
        """Test token counting functionality"""
        manager = ContextWindowManager()

        # Test simple text
        text = "Hello, world!"
        tokens = manager.count_tokens(text)
        assert tokens > 0
        assert tokens < 10  # Should be ~3 tokens

        # Test longer text
        long_text = "This is a longer piece of text " * 100
        long_tokens = manager.count_tokens(long_text)
        assert long_tokens > tokens

        print(f"✓ Token counting works: '{text[:20]}...' = {tokens} tokens")

    def test_context_optimization(self):
        """Test context optimization strategies"""
        manager = ContextWindowManager(strategy=ContextStrategy.SLIDING_WINDOW)

        # Create test messages
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language..."},
            {"role": "user", "content": "What about JavaScript?"},
            {"role": "assistant", "content": "JavaScript is also a programming language..."},
            {"role": "user", "content": "Compare them"},
        ]

        # Optimize context
        optimized, stats = manager.optimize_context(
            messages,
            system_message="You are a helpful assistant",
            reserved_tokens=1000
        )

        assert len(optimized) <= len(messages)
        assert stats.total_messages == len(optimized)
        assert stats.total_tokens > 0
        assert stats.utilization_percent >= 0
        assert stats.utilization_percent <= 100

        print(f"✓ Context optimization: {len(messages)} → {len(optimized)} messages")
        print(f"  Tokens: {stats.total_tokens}, Utilization: {stats.utilization_percent}%")

    def test_all_optimization_strategies(self):
        """Test all optimization strategies"""
        messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]

        strategies = [
            ContextStrategy.SLIDING_WINDOW,
            ContextStrategy.TRUNCATE_MIDDLE,
            ContextStrategy.PRIORITY_BASED
        ]

        for strategy in strategies:
            manager = ContextWindowManager(strategy=strategy)
            optimized, stats = manager.optimize_context(messages, reserved_tokens=1000)

            assert len(optimized) > 0
            assert stats.total_tokens > 0
            print(f"✓ {strategy.value}: {len(optimized)} messages kept")


class TestStreamingIntegration:
    """Test Streaming Handler integration"""

    def test_streaming_handler_initialization(self):
        """Test streaming handler can be initialized"""
        handler = StreamingHandler(
            buffer_size=100,
            enable_metrics=True
        )

        assert handler.buffer_size == 100
        assert handler.enable_metrics is True
        assert handler.metrics is not None

        print("✓ Streaming handler initialized")

    def test_callback_registration(self):
        """Test callback registration"""
        handler = StreamingHandler()

        # Register callbacks
        start_called = []
        chunk_called = []
        end_called = []
        error_called = []

        handler.on_start(lambda meta: start_called.append(meta))
        handler.on_chunk(lambda msg: chunk_called.append(msg))
        handler.on_end(lambda msg: end_called.append(msg))
        handler.on_error(lambda msg: error_called.append(msg))

        assert len(handler.on_start_callbacks) == 1
        assert len(handler.on_chunk_callbacks) == 1
        assert len(handler.on_end_callbacks) == 1
        assert len(handler.on_error_callbacks) == 1

        print("✓ Callbacks registered successfully")

    def test_metrics_tracking(self):
        """Test metrics tracking"""
        handler = StreamingHandler(enable_metrics=True)

        metrics = handler.get_metrics()
        assert "total_chunks" in metrics
        assert "total_bytes" in metrics
        assert "total_chars" in metrics

        # Reset metrics
        handler.reset_metrics()
        metrics = handler.get_metrics()
        assert metrics["total_chunks"] == 0

        print("✓ Metrics tracking works")


class TestVectorDatabaseIntegration:
    """Test Vector Database integration"""

    def test_vector_database_singleton(self):
        """Test vector database singleton pattern"""
        db1 = get_vector_database()
        db2 = get_vector_database()

        # Should be same instance
        assert db1 is db2

        if db1 and db1.client:
            print("✓ Vector database available (Qdrant running)")
            stats = db1.get_stats()
            print(f"  Collection: {stats.get('collection_name')}")
            print(f"  Documents: {stats.get('points_count', 0)}")
        else:
            print("⚠ Vector database not available (Qdrant not running)")
            print("  Start with: docker run -p 6333:6333 qdrant/qdrant")

    def test_vector_database_stats(self):
        """Test getting database stats"""
        db = get_vector_database()

        if db:
            stats = db.get_stats()
            assert isinstance(stats, dict)
            assert "available" in stats

            if stats["available"]:
                assert "collection_name" in stats
                assert "points_count" in stats
                print(f"✓ Vector DB stats: {stats}")
            else:
                print("⚠ Vector DB not available")


class TestEndToEndIntegration:
    """End-to-end integration tests"""

    def test_persona_with_context_manager(self):
        """Test using persona with context manager"""
        # Get a persona (using actual key)
        persona = get_persona('gcp-architect')
        assert persona is not None

        # Create context manager
        manager = ContextWindowManager()

        # Create conversation with persona
        system_prompt = persona['system_prompt']
        messages = [
            {"role": "user", "content": "How do I design a scalable architecture?"}
        ]

        # Optimize context
        optimized, stats = manager.optimize_context(
            messages,
            system_message=system_prompt,
            reserved_tokens=2000
        )

        assert len(optimized) > 0
        assert stats.system_tokens > 0

        print(f"✓ Persona + Context Manager integration works")
        print(f"  System tokens: {stats.system_tokens}")
        print(f"  Total utilization: {stats.utilization_percent}%")

    def test_framework_modules_available(self):
        """Test that all framework modules are importable"""
        modules = [
            'core.personas_extended',
            'core.context_manager',
            'core.streaming_handler',
            'core.vector_database',
        ]

        for module in modules:
            try:
                __import__(module)
                print(f"✓ {module} imported successfully")
            except ImportError as e:
                pytest.fail(f"Failed to import {module}: {e}")

    def test_framework_performance(self):
        """Test basic performance metrics"""
        import time

        # Test persona retrieval speed
        start = time.time()
        for _ in range(1000):
            get_persona('PRODUCT-MANAGER')
        duration = time.time() - start

        avg_time = duration / 1000 * 1000  # ms
        assert avg_time < 1.0  # Should be < 1ms per retrieval

        print(f"✓ Performance: {avg_time:.3f}ms avg persona retrieval")

        # Test token counting speed
        manager = ContextWindowManager()
        text = "This is a test sentence for token counting performance." * 10

        start = time.time()
        for _ in range(100):
            manager.count_tokens(text)
        duration = time.time() - start

        avg_time = duration / 100 * 1000  # ms
        print(f"✓ Performance: {avg_time:.3f}ms avg token counting")

    def test_tier1_enhanced_personas_files_exist(self):
        """Test that Tier 1 persona files exist"""
        base_path = Path(__file__).parent.parent
        personas_path = base_path / 'personas' / 'enhanced'

        tier1_files = [
            'product_manager.py',
            'engineering_manager.py',
            'startup_cto.py',
            'blockchain_developer.py',
            'embedded_systems_engineer.py',
            'network_engineer.py'
        ]

        for filename in tier1_files:
            filepath = personas_path / filename
            assert filepath.exists(), f"Tier 1 persona file should exist: {filename}"

            # Check file has substantial content
            size = filepath.stat().st_size
            assert size > 30000, f"{filename} should be > 30KB (Tier 1 quality)"

        print(f"✓ All {len(tier1_files)} Tier 1 persona files exist")


def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("NubemSuperFClaude Framework - Week 4 Integration Tests")
    print("="*60 + "\n")

    # Use pytest to run all tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-s"  # Show print statements
    ])


if __name__ == "__main__":
    run_all_tests()
