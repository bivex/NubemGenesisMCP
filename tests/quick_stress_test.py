#!/usr/bin/env python3
"""Quick stress test for NubemSuperFClaude"""

import asyncio
import time
import statistics
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.sqlite_vector_store import SQLiteVectorStore
from core.cache_system import get_cache, close_cache

async def quick_stress_test():
    print("🚀 Quick Stress Test for NubemSuperFClaude")
    print("=" * 50)
    
    results = {}
    
    # Test cache performance
    print("\n💾 Testing cache performance...")
    cache = await get_cache()
    
    start = time.time()
    for i in range(100):
        await cache.set(f"key_{i}", f"value_{i}")
    write_time = time.time() - start
    
    start = time.time()
    hits = 0
    for i in range(100):
        if await cache.get(f"key_{i}"):
            hits += 1
    read_time = time.time() - start
    
    results["cache"] = {
        "writes_per_second": 100 / write_time,
        "reads_per_second": 100 / read_time,
        "hit_rate": hits
    }
    print(f"✅ Cache write: {100/write_time:.0f} ops/s")
    print(f"✅ Cache read: {100/read_time:.0f} ops/s")
    print(f"✅ Hit rate: {hits}%")
    
    await close_cache()
    
    # Test vector store
    print("\n🔍 Testing vector store...")
    vector_store = SQLiteVectorStore()
    
    start = time.time()
    for i in range(50):
        vector_store.add_vector(f"Document {i}", {"id": i})
    insert_time = time.time() - start
    
    start = time.time()
    for _ in range(10):
        vector_store.search("Document", limit=5)
    search_time = time.time() - start
    
    results["vector_store"] = {
        "inserts_per_second": 50 / insert_time,
        "searches_per_second": 10 / search_time
    }
    print(f"✅ Vector insert: {50/insert_time:.0f} ops/s")
    print(f"✅ Vector search: {10/search_time:.0f} ops/s")
    
    # Save results
    print("\n" + "=" * 50)
    print("✅ Quick stress test completed!")
    print(json.dumps(results, indent=2))
    
    return results

if __name__ == "__main__":
    asyncio.run(quick_stress_test())
