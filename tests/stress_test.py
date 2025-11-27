#!/usr/bin/env python3
"""
Stress Tests para NubemSuperFClaude
Tests de carga, rendimiento y estabilidad
"""

import asyncio
import time
import random
import statistics
import psutil
import json
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import aiohttp
import uvloop
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.fast_claude import FastClaude
from core.sqlite_vector_store import SQLiteVectorStore
from core.cache_system import get_cache, close_cache
from core.rich_cli import RichCLI
from core.collaborative_mode import get_collaboration_manager, User, UserRole, Message, MessageType
from plugins.plugin_manager import get_plugin_manager
import uuid
from datetime import datetime


class StressTestSuite:
    """Suite completa de stress tests"""

    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "system_info": self._get_system_info()
        }
        self.claude = FastClaude()
        self.vector_store = SQLiteVectorStore()

    def _get_system_info(self) -> Dict:
        """Get system information"""
        return {
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "memory_available": psutil.virtual_memory().available,
            "disk_usage": psutil.disk_usage('/').percent,
            "python_version": sys.version
        }

    async def test_concurrent_queries(self, num_queries: int = 100):
        """Test concurrent query processing"""
        print(f"\n🔄 Testing {num_queries} concurrent queries...")

        queries = [
            "What is Python?",
            "Explain Docker",
            "How to use Git?",
            "What is cloud computing?",
            "Explain machine learning"
        ] * (num_queries // 5)

        start_time = time.time()
        tasks = []

        async def process_query(query: str) -> float:
            query_start = time.time()
            try:
                result = self.claude.execute(query)
                return time.time() - query_start
            except Exception as e:
                print(f"Error: {e}")
                return -1

        # Create tasks
        for query in queries:
            tasks.append(process_query(query))

        # Execute concurrently
        response_times = await asyncio.gather(*tasks)

        # Filter successful responses
        successful_times = [t for t in response_times if t > 0]

        total_time = time.time() - start_time

        self.results["tests"]["concurrent_queries"] = {
            "total_queries": num_queries,
            "successful": len(successful_times),
            "failed": num_queries - len(successful_times),
            "total_time": total_time,
            "queries_per_second": num_queries / total_time,
            "avg_response_time": statistics.mean(successful_times) if successful_times else 0,
            "p50_response_time": statistics.median(successful_times) if successful_times else 0,
            "p95_response_time": statistics.quantiles(successful_times, n=20)[18] if len(successful_times) > 20 else 0,
            "p99_response_time": statistics.quantiles(successful_times, n=100)[98] if len(successful_times) > 100 else 0
        }

        print(f"✅ Completed: {len(successful_times)}/{num_queries} queries")
        print(f"⚡ QPS: {num_queries / total_time:.2f}")
        print(f"⏱️ Avg response: {statistics.mean(successful_times) if successful_times else 0:.3f}s")

    async def test_cache_performance(self, iterations: int = 1000):
        """Test cache system performance"""
        print(f"\n💾 Testing cache with {iterations} operations...")

        cache = await get_cache()

        # Test write performance
        write_start = time.time()
        for i in range(iterations):
            await cache.set(f"test_key_{i}", f"test_value_{i}", ttl=300)
        write_time = time.time() - write_start

        # Test read performance (should hit cache)
        read_start = time.time()
        hits = 0
        for i in range(iterations):
            value = await cache.get(f"test_key_{i}")
            if value:
                hits += 1
        read_time = time.time() - read_start

        # Test mixed operations
        mixed_start = time.time()
        operations = []
        for i in range(iterations):
            if random.random() > 0.5:
                operations.append(cache.set(f"mixed_{i}", f"value_{i}"))
            else:
                operations.append(cache.get(f"mixed_{i}"))
        await asyncio.gather(*operations)
        mixed_time = time.time() - mixed_start

        # Get cache stats
        stats = await cache.get_stats()

        self.results["tests"]["cache_performance"] = {
            "iterations": iterations,
            "write_time": write_time,
            "writes_per_second": iterations / write_time,
            "read_time": read_time,
            "reads_per_second": iterations / read_time,
            "cache_hit_rate": (hits / iterations) * 100,
            "mixed_time": mixed_time,
            "mixed_ops_per_second": (iterations * 2) / mixed_time,
            "cache_stats": stats
        }

        print(f"✅ Cache hit rate: {(hits / iterations) * 100:.2f}%")
        print(f"⚡ Write ops/s: {iterations / write_time:.0f}")
        print(f"⚡ Read ops/s: {iterations / read_time:.0f}")

        await close_cache()

    async def test_vector_store_performance(self, num_vectors: int = 500):
        """Test vector store performance"""
        print(f"\n🔍 Testing vector store with {num_vectors} vectors...")

        # Test insertion
        insert_start = time.time()
        for i in range(num_vectors):
            self.vector_store.add_vector(
                f"Document {i}: This is test content for vector storage",
                {"id": i, "type": "test"},
                collection="stress_test"
            )
        insert_time = time.time() - insert_start

        # Test search
        search_times = []
        for _ in range(100):
            search_start = time.time()
            results = self.vector_store.search(
                "test content",
                collection="stress_test",
                limit=10
            )
            search_times.append(time.time() - search_start)

        # Test statistics
        stats = self.vector_store.get_stats()

        self.results["tests"]["vector_store"] = {
            "num_vectors": num_vectors,
            "insert_time": insert_time,
            "inserts_per_second": num_vectors / insert_time,
            "avg_search_time": statistics.mean(search_times),
            "p50_search_time": statistics.median(search_times),
            "p95_search_time": statistics.quantiles(search_times, n=20)[18] if len(search_times) > 20 else 0,
            "stats": stats
        }

        print(f"✅ Inserted {num_vectors} vectors")
        print(f"⚡ Insert rate: {num_vectors / insert_time:.0f} vectors/s")
        print(f"🔍 Avg search time: {statistics.mean(search_times):.3f}s")

    async def test_collaboration_scaling(self, num_sessions: int = 50, users_per_session: int = 10):
        """Test collaboration system scaling"""
        print(f"\n👥 Testing collaboration with {num_sessions} sessions, {users_per_session} users each...")

        manager = get_collaboration_manager()

        create_start = time.time()
        sessions = []

        # Create sessions
        for i in range(num_sessions):
            owner = User(
                id=f"owner_{i}",
                name=f"Owner {i}",
                email=f"owner{i}@test.com",
                role=UserRole.OWNER
            )

            session = await manager.create_session(
                name=f"Session {i}",
                owner=owner
            )
            sessions.append(session)

            # Add users
            for j in range(users_per_session - 1):
                user = User(
                    id=f"user_{i}_{j}",
                    name=f"User {i}-{j}",
                    email=f"user{i}_{j}@test.com",
                    role=UserRole.EDITOR
                )
                await manager.join_session(session.id, user)

        create_time = time.time() - create_start

        # Test message broadcasting
        message_start = time.time()
        message_tasks = []

        for session in sessions[:10]:  # Test on first 10 sessions
            for i in range(10):  # 10 messages per session
                message = Message(
                    id=str(uuid.uuid4()),
                    type=MessageType.CHAT,
                    user_id=f"owner_{sessions.index(session)}",
                    content=f"Test message {i}",
                    timestamp=datetime.now()
                )
                message_tasks.append(manager.add_message(session.id, message))

        await asyncio.gather(*message_tasks)
        message_time = time.time() - message_start

        self.results["tests"]["collaboration"] = {
            "num_sessions": num_sessions,
            "users_per_session": users_per_session,
            "total_users": num_sessions * users_per_session,
            "session_creation_time": create_time,
            "sessions_per_second": num_sessions / create_time,
            "message_broadcast_time": message_time,
            "messages_per_second": 100 / message_time,  # 10 sessions * 10 messages
            "active_sessions": len(manager.sessions)
        }

        print(f"✅ Created {num_sessions} sessions")
        print(f"👥 Total users: {num_sessions * users_per_session}")
        print(f"⚡ Session creation rate: {num_sessions / create_time:.2f} sessions/s")

    async def test_memory_usage(self):
        """Test memory usage under load"""
        print("\n💾 Testing memory usage...")

        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        # Create load
        tasks = []
        for _ in range(50):
            tasks.append(self.claude.execute("Test query"))

        await asyncio.gather(*tasks, return_exceptions=True)

        peak_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        # Cleanup and measure
        import gc
        gc.collect()

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        self.results["tests"]["memory_usage"] = {
            "initial_mb": initial_memory,
            "peak_mb": peak_memory,
            "final_mb": final_memory,
            "increase_mb": peak_memory - initial_memory,
            "leaked_mb": final_memory - initial_memory
        }

        print(f"📊 Initial: {initial_memory:.2f} MB")
        print(f"📊 Peak: {peak_memory:.2f} MB")
        print(f"📊 Final: {final_memory:.2f} MB")
        print(f"📊 Increase: {peak_memory - initial_memory:.2f} MB")

    async def test_plugin_system(self):
        """Test plugin system performance"""
        print("\n🔌 Testing plugin system...")

        manager = get_plugin_manager()

        # Discover plugins
        discover_start = time.time()
        plugins = await manager.discover_plugins()
        discover_time = time.time() - discover_start

        # List plugins
        list_start = time.time()
        plugin_list = await manager.list_plugins()
        list_time = time.time() - list_start

        # Trigger events
        event_times = []
        for _ in range(100):
            event_start = time.time()
            await manager.trigger_event("test_event", {"data": "test"})
            event_times.append(time.time() - event_start)

        self.results["tests"]["plugin_system"] = {
            "discovered_plugins": len(plugins),
            "discover_time": discover_time,
            "list_time": list_time,
            "avg_event_time": statistics.mean(event_times) if event_times else 0,
            "events_per_second": 100 / sum(event_times) if event_times else 0
        }

        print(f"✅ Discovered {len(plugins)} plugins")
        print(f"⚡ Event rate: {100 / sum(event_times) if event_times else 0:.0f} events/s")

    async def test_api_endpoints(self):
        """Test REST API endpoints"""
        print("\n🌐 Testing API endpoints...")

        base_url = "http://localhost:8000"

        async with aiohttp.ClientSession() as session:
            endpoint_times = {}

            # Test different endpoints
            endpoints = [
                ("GET", "/"),
                ("GET", "/health"),
                ("GET", "/api/docs"),
            ]

            for method, endpoint in endpoints:
                times = []
                for _ in range(10):
                    try:
                        start = time.time()
                        async with session.request(method, f"{base_url}{endpoint}") as resp:
                            await resp.text()
                        times.append(time.time() - start)
                    except:
                        times.append(-1)

                successful = [t for t in times if t > 0]
                endpoint_times[endpoint] = {
                    "avg_time": statistics.mean(successful) if successful else 0,
                    "success_rate": len(successful) / len(times) * 100
                }

            self.results["tests"]["api_endpoints"] = endpoint_times

            print(f"✅ Tested {len(endpoints)} endpoints")

    async def run_all_tests(self):
        """Run all stress tests"""
        print("=" * 60)
        print("🚀 Starting NubemSuperFClaude Stress Tests")
        print("=" * 60)

        start_time = time.time()

        # Run tests
        await self.test_concurrent_queries(100)
        await self.test_cache_performance(500)
        await self.test_vector_store_performance(200)
        await self.test_collaboration_scaling(10, 5)
        await self.test_memory_usage()
        await self.test_plugin_system()
        # API test commented as it needs server running
        # await self.test_api_endpoints()

        total_time = time.time() - start_time

        self.results["summary"] = {
            "total_time": total_time,
            "tests_run": len(self.results["tests"]),
            "status": "completed"
        }

        # Save results
        results_file = Path(__file__).parent / "stress_test_results.json"
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print("\n" + "=" * 60)
        print("✅ Stress Tests Completed")
        print(f"⏱️ Total time: {total_time:.2f}s")
        print(f"📊 Results saved to: {results_file}")
        print("=" * 60)

        self._print_summary()

    def _print_summary(self):
        """Print test summary"""
        print("\n📈 PERFORMANCE SUMMARY")
        print("-" * 40)

        if "concurrent_queries" in self.results["tests"]:
            q = self.results["tests"]["concurrent_queries"]
            print(f"Queries: {q['queries_per_second']:.2f} QPS")
            print(f"Response time P50: {q['p50_response_time']:.3f}s")

        if "cache_performance" in self.results["tests"]:
            c = self.results["tests"]["cache_performance"]
            print(f"Cache hit rate: {c['cache_hit_rate']:.2f}%")
            print(f"Cache ops/s: {c['mixed_ops_per_second']:.0f}")

        if "memory_usage" in self.results["tests"]:
            m = self.results["tests"]["memory_usage"]
            print(f"Memory usage: {m['peak_mb']:.2f} MB (peak)")
            print(f"Memory leaked: {m['leaked_mb']:.2f} MB")


async def main():
    """Main entry point"""
    # Use uvloop for better performance
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    suite = StressTestSuite()
    await suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())