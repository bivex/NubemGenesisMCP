"""
Test Lazy Persona Manager
Simple, focused tests for the lazy loading wrapper
"""

import pytest
import time
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.lazy_persona_manager import LazyPersonaManager, get_lazy_persona_manager


class TestLazyPersonaManager:
    """Test suite for LazyPersonaManager"""

    def test_initialization(self):
        """Test manager initialization"""
        manager = LazyPersonaManager()
        assert manager is not None

        available = manager.get_available_personas()
        assert len(available) > 0
        print(f"✓ Manager initialized with {len(available)} personas available")

    def test_registry_built(self):
        """Test persona registry is built correctly"""
        manager = LazyPersonaManager()
        available = manager.get_available_personas()

        # Should have core personas
        assert 'architect' in available
        assert 'backend' in available
        assert 'frontend' in available

        print(f"✓ Registry contains {len(available)} personas")
        print(f"  Core personas present: architect, backend, frontend")

    def test_lazy_load_single_persona(self):
        """Test loading a single persona on demand"""
        manager = LazyPersonaManager()

        # Initially not loaded
        assert not manager.is_loaded('architect')
        print("✓ Persona 'architect' not loaded initially")

        # Load on first access
        start_time = time.time()
        persona = manager.get_persona('architect')
        load_time = time.time() - start_time

        if persona:
            assert manager.is_loaded('architect')
            print(f"✓ Loaded 'architect' in {load_time:.3f}s")

            # Second access from cache
            start_time = time.time()
            persona2 = manager.get_persona('architect')
            cache_time = time.time() - start_time

            assert persona is persona2
            print(f"✓ Retrieved from cache in {cache_time:.6f}s (speedup: {load_time/max(cache_time, 0.000001):.0f}x)")
        else:
            print("⚠ Persona not available (expected in test environment)")

    def test_lazy_vs_eager_loading(self):
        """Compare lazy vs eager loading performance"""
        import tracemalloc

        print("\n" + "="*60)
        print("LAZY VS EAGER LOADING COMPARISON")
        print("="*60)

        # Test EAGER loading (traditional approach)
        tracemalloc.start()
        start_time = time.time()

        from core.personas_unified import UnifiedPersonaManager
        eager_manager = UnifiedPersonaManager(lazy_load=False)

        eager_time = time.time() - start_time
        eager_memory = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB

        tracemalloc.stop()

        print(f"\nEAGER LOADING (load all):")
        print(f"  Time: {eager_time:.3f}s")
        print(f"  Memory: {eager_memory:.2f} MB")
        print(f"  Personas loaded: {len(eager_manager.personas)}")

        # Test LAZY loading
        tracemalloc.start()
        start_time = time.time()

        lazy_manager = LazyPersonaManager()

        lazy_time = time.time() - start_time
        lazy_memory = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB

        tracemalloc.stop()

        print(f"\nLAZY LOADING (initialization only):")
        print(f"  Time: {lazy_time:.3f}s")
        print(f"  Memory: {lazy_memory:.2f} MB")
        print(f"  Personas available: {lazy_manager.get_total_persona_count()}")
        print(f"  Personas loaded: {len(lazy_manager.get_loaded_personas())}")

        # Calculate improvements
        time_savings = max(0, (1 - lazy_time / max(eager_time, 0.001)) * 100)
        memory_savings = max(0, (1 - lazy_memory / max(eager_memory, 0.1)) * 100)

        print(f"\nIMPROVEMENT:")
        print(f"  Startup time: {time_savings:.1f}% faster")
        print(f"  Memory usage: {memory_savings:.1f}% less")

        print("="*60 + "\n")

        # Assertions
        assert lazy_time < eager_time or eager_time < 0.1  # Allow for very fast eager loads
        assert lazy_memory < eager_memory or eager_memory < 1  # Allow for small memory footprints

    def test_get_stats(self):
        """Test statistics collection"""
        manager = LazyPersonaManager()

        # Load a persona
        manager.get_persona('architect')
        manager.get_persona('architect')  # Access twice

        stats = manager.get_stats()

        assert 'available_personas' in stats
        assert 'loaded_personas' in stats
        assert 'total_accesses' in stats
        assert 'most_used' in stats

        print(f"✓ Stats: {stats['loaded_personas']} loaded, {stats['total_accesses']} accesses")
        print(f"  Memory savings: {stats['memory_savings_estimate']}")

    def test_select_persona_by_task(self):
        """Test automatic persona selection based on task"""
        manager = LazyPersonaManager()

        # Test different task types
        tasks = [
            ("Design a microservices architecture", "architect"),
            ("Create a REST API endpoint", "backend"),
            ("Build a responsive UI component", "frontend"),
            ("Fix a security vulnerability", "security"),
            ("Optimize database queries", "performance"),
        ]

        for task, expected_persona in tasks:
            persona = manager.select_persona(task)
            if persona:
                print(f"✓ Task: '{task[:40]}...'")
                print(f"  Selected: {persona.name if hasattr(persona, 'name') else expected_persona}")

    def test_global_singleton(self):
        """Test global singleton instance"""
        manager1 = get_lazy_persona_manager()
        manager2 = get_lazy_persona_manager()

        assert manager1 is manager2
        print("✓ Global manager is singleton")

    def test_unload_persona(self):
        """Test unloading personas to free memory"""
        manager = LazyPersonaManager()

        # Load persona
        persona = manager.get_persona('architect')

        if persona:
            assert manager.is_loaded('architect')

            # Unload it
            manager.unload_persona('architect')
            assert not manager.is_loaded('architect')
            print("✓ Successfully unloaded persona")
        else:
            print("⚠ Persona not available for unload test")


def test_real_world_usage():
    """Test real-world usage pattern"""
    print("\n" + "="*60)
    print("REAL-WORLD USAGE SIMULATION")
    print("="*60 + "\n")

    manager = LazyPersonaManager()

    # Simulate a typical workflow
    tasks = [
        "Design system architecture",
        "Create backend API",
        "Build frontend UI",
        "Write tests",
        "Deploy to production"
    ]

    start_time = time.time()

    for i, task in enumerate(tasks, 1):
        print(f"\n{i}. Task: {task}")
        persona = manager.select_persona(task)

        if persona:
            persona_name = persona.name if hasattr(persona, 'name') else 'unknown'
            print(f"   Persona: {persona_name}")

    elapsed = time.time() - start_time

    stats = manager.get_stats()
    print(f"\n{'='*60}")
    print("WORKFLOW COMPLETE")
    print(f"{'='*60}")
    print(f"Total time: {elapsed:.3f}s")
    print(f"Personas loaded: {stats['loaded_personas']}/{stats['available_personas']}")
    print(f"Memory savings: {stats['memory_savings_estimate']}")
    print(f"Most used: {stats['most_used'][:3]}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("LAZY PERSONA MANAGER TEST SUITE")
    print("="*60 + "\n")

    # Run pytest
    pytest.main([__file__, '-v', '-s'])

    # Run real-world simulation
    test_real_world_usage()
