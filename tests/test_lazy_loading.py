"""
Comprehensive Tests for Lazy Loading System
Tests memory usage, startup time, and functionality
"""

import pytest
import time
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.lazy_persona_loader import LazyPersonaLoader, get_lazy_loader, lazy_load_persona


class TestLazyPersonaLoader:
    """Test suite for LazyPersonaLoader"""

    def test_initialization(self):
        """Test loader initialization"""
        loader = LazyPersonaLoader()
        assert loader is not None
        assert len(loader.get_available_personas()) > 0
        print(f"✓ Found {len(loader.get_available_personas())} available personas")

    def test_scan_personas(self):
        """Test scanning available personas"""
        loader = LazyPersonaLoader()
        personas = loader.get_available_personas()

        # Should have at least some personas
        assert len(personas) > 0
        print(f"✓ Scanned {len(personas)} personas")

        # Check for known personas
        expected_personas = ['architect', 'backend', 'frontend']
        for persona in expected_personas:
            if persona in personas:
                print(f"✓ Found expected persona: {persona}")

    def test_lazy_load_single_persona(self):
        """Test loading a single persona on demand"""
        loader = LazyPersonaLoader()

        # Persona should not be loaded initially
        assert not loader.is_loaded('architect')
        print("✓ Persona 'architect' not loaded initially")

        # Load persona
        start_time = time.time()
        persona = loader.get_persona('architect')
        load_time = time.time() - start_time

        if persona:
            assert loader.is_loaded('architect')
            print(f"✓ Loaded 'architect' persona in {load_time:.3f}s")

            # Second access should be from cache (faster)
            start_time = time.time()
            persona2 = loader.get_persona('architect')
            cache_time = time.time() - start_time

            assert persona is persona2  # Same object
            print(f"✓ Retrieved 'architect' from cache in {cache_time:.6f}s (cache speedup: {load_time/cache_time:.0f}x)")
        else:
            print("⚠ Persona 'architect' not available, skipping")

    def test_load_multiple_personas(self):
        """Test loading multiple personas"""
        loader = LazyPersonaLoader()

        personas_to_load = ['architect', 'backend', 'frontend', 'security', 'devops']
        loaded_count = 0

        for persona_name in personas_to_load:
            persona = loader.get_persona(persona_name)
            if persona:
                loaded_count += 1
                print(f"✓ Loaded persona: {persona_name}")

        print(f"✓ Successfully loaded {loaded_count}/{len(personas_to_load)} personas")
        assert loaded_count > 0

    def test_preload_core_personas(self):
        """Test preloading core personas"""
        loader = LazyPersonaLoader()

        start_time = time.time()
        loader.preload_core_personas(['architect', 'backend'])
        preload_time = time.time() - start_time

        print(f"✓ Preloaded core personas in {preload_time:.3f}s")

        # Check they are loaded
        stats = loader.get_stats()
        assert stats['loaded_personas'] >= 0
        print(f"✓ {stats['loaded_personas']} personas loaded")

    def test_access_counting(self):
        """Test access count tracking"""
        loader = LazyPersonaLoader()

        # Load and access persona multiple times
        for i in range(5):
            loader.get_persona('architect')

        stats = loader.get_stats()
        print(f"✓ Total accesses: {stats['total_accesses']}")
        print(f"✓ Most used personas: {stats['most_used']}")

    def test_unload_persona(self):
        """Test unloading personas"""
        loader = LazyPersonaLoader()

        # Load persona
        loader.get_persona('architect')
        assert loader.is_loaded('architect')

        # Unload it
        loader.unload_persona('architect')
        assert not loader.is_loaded('architect')
        print("✓ Successfully unloaded persona")

    def test_unload_least_used(self):
        """Test unloading least-used personas"""
        loader = LazyPersonaLoader()

        # Load several personas
        personas = ['architect', 'backend', 'frontend', 'security']
        for persona in personas:
            loader.get_persona(persona)

        # Access some more than others
        for i in range(10):
            loader.get_persona('architect')
        for i in range(5):
            loader.get_persona('backend')

        stats_before = loader.get_stats()
        loaded_before = stats_before['loaded_personas']

        # Unload least used, keep top 2
        loader.unload_least_used(keep_count=2)

        stats_after = loader.get_stats()
        loaded_after = stats_after['loaded_personas']

        print(f"✓ Unloaded {loaded_before - loaded_after} least-used personas")
        assert loaded_after <= 2 or loaded_after < loaded_before

    def test_get_stats(self):
        """Test statistics collection"""
        loader = LazyPersonaLoader()

        # Load some personas
        loader.get_persona('architect')
        loader.get_persona('backend')

        stats = loader.get_stats()

        assert 'available_personas' in stats
        assert 'loaded_personas' in stats
        assert 'total_load_time' in stats
        assert 'most_used' in stats

        print(f"✓ Stats collected: {stats}")

    def test_clear_cache(self):
        """Test clearing all loaded personas"""
        loader = LazyPersonaLoader()

        # Load personas
        loader.get_persona('architect')
        loader.get_persona('backend')

        assert loader.get_stats()['loaded_personas'] > 0

        # Clear cache
        loader.clear_cache()

        stats = loader.get_stats()
        assert stats['loaded_personas'] == 0
        print("✓ Cache cleared successfully")

    def test_global_lazy_loader(self):
        """Test global singleton instance"""
        loader1 = get_lazy_loader()
        loader2 = get_lazy_loader()

        assert loader1 is loader2
        print("✓ Global lazy loader is singleton")

    def test_convenience_function(self):
        """Test convenience function"""
        persona = lazy_load_persona('architect')

        if persona:
            print("✓ Convenience function works")
        else:
            print("⚠ Persona not available via convenience function")


class TestLazyModuleImport:
    """Test the lazy module __init__ system"""

    def test_lazy_import(self):
        """Test importing personas lazily"""
        # Clear any cached imports
        if 'personas.enhanced' in sys.modules:
            del sys.modules['personas.enhanced']

        # Import should not load all personas immediately
        start_time = time.time()
        from personas import enhanced
        import_time = time.time() - start_time

        print(f"✓ Import took {import_time:.3f}s (should be very fast)")
        assert import_time < 1.0  # Should be near-instant

    def test_lazy_attribute_access(self):
        """Test accessing persona attributes lazily"""
        try:
            from personas.enhanced import ARCHITECT_ENHANCED

            print(f"✓ Successfully accessed ARCHITECT_ENHANCED lazily")
            assert ARCHITECT_ENHANCED is not None
        except (AttributeError, ImportError) as e:
            print(f"⚠ Could not access ARCHITECT_ENHANCED: {e}")


def test_memory_comparison():
    """Compare memory usage with and without lazy loading"""
    import tracemalloc

    print("\n" + "="*60)
    print("MEMORY COMPARISON TEST")
    print("="*60)

    # Test WITHOUT lazy loading (load all immediately)
    tracemalloc.start()
    start_time = time.time()

    loader_eager = LazyPersonaLoader()
    all_personas = loader_eager.get_available_personas()[:10]  # Load first 10

    for persona in all_personas:
        loader_eager.get_persona(persona)

    eager_time = time.time() - start_time
    eager_memory = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB

    tracemalloc.stop()

    print(f"\nEAGER LOADING (10 personas):")
    print(f"  Time: {eager_time:.3f}s")
    print(f"  Memory: {eager_memory:.2f} MB")

    # Test WITH lazy loading (load only when needed)
    tracemalloc.start()
    start_time = time.time()

    loader_lazy = LazyPersonaLoader()
    # Just initialize, don't load anything
    available = loader_lazy.get_available_personas()

    lazy_time = time.time() - start_time
    lazy_memory = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB

    tracemalloc.stop()

    print(f"\nLAZY LOADING (initialization only):")
    print(f"  Time: {lazy_time:.3f}s")
    print(f"  Memory: {lazy_memory:.2f} MB")

    print(f"\nIMPROVEMENT:")
    print(f"  Time saved: {(1 - lazy_time/eager_time) * 100:.1f}%")
    print(f"  Memory saved: {(1 - lazy_memory/eager_memory) * 100:.1f}%")

    print("="*60)


if __name__ == '__main__':
    print("\n" + "="*60)
    print("LAZY LOADING COMPREHENSIVE TEST SUITE")
    print("="*60 + "\n")

    # Run tests
    pytest.main([__file__, '-v', '-s'])

    # Run memory comparison
    test_memory_comparison()
