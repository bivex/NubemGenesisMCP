#!/usr/bin/env python3
"""
Comprehensive End-to-End Tests for NubemSuperFClaude
Tests complete user workflows and system integration
"""

import asyncio
import pytest
import json
import time
from typing import Dict, Any
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_orchestrator import get_unified_orchestrator
from core.multi_level_cache import get_multi_cache
from core.connection_pool import get_connection_pool
from core.plugin_system import get_plugin_manager
from core.personas_unified import UnifiedPersonaManager


class E2ETestSuite:
    """Comprehensive end-to-end test suite"""
    
    def __init__(self):
        self.session_id = "e2e_test_session"
        self.test_results = {}
        
    async def setup(self):
        """Setup test environment"""
        print("🔧 Setting up E2E test environment...")
        
        # Initialize all systems
        self.cache = get_multi_cache()
        await self.cache.initialize()
        
        self.pool = get_connection_pool()
        await self.pool.initialize()
        
        self.plugin_manager = get_plugin_manager()
        self.persona_manager = UnifiedPersonaManager()
        
        print("✅ E2E test environment ready")
    
    async def test_auto_orchestration_flow(self):
        """Test complete auto-orchestration workflow"""
        print("\n🤖 Testing Auto-Orchestration Flow...")
        
        test_queries = [
            {
                "query": "Necesito crear una API REST para una aplicación de e-commerce",
                "expected_personas": ["backend", "architect"],
                "description": "Backend development task"
            },
            {
                "query": "Optimizar el rendimiento de mi aplicación React",
                "expected_personas": ["frontend", "performance"],
                "description": "Frontend optimization task"
            },
            {
                "query": "Implementar CI/CD pipeline con GitHub Actions",
                "expected_personas": ["devops", "cicd-specialist"],
                "description": "DevOps automation task"
            },
            {
                "query": "Crear documentación técnica para desarrolladores",
                "expected_personas": ["documenter", "mentor"],
                "description": "Documentation task"
            }
        ]
        
        results = []
        for i, test_case in enumerate(test_queries):
            print(f"  📝 Test {i+1}: {test_case['description']}")
            
            try:
                start_time = time.time()
                result = await auto_orchestrator.process_message(
                    f"{self.session_id}_{i}",
                    test_case["query"]
                )
                end_time = time.time()
                
                # Verify results
                success = bool(result.get('orchestration_performed'))
                active_personas = result.get('active_personas', [])
                confidence = result.get('confidence', 0)
                response_time = end_time - start_time
                
                # Check if expected personas are present
                persona_match = any(
                    expected in ' '.join(active_personas).lower()
                    for expected in test_case['expected_personas']
                )
                
                test_result = {
                    "query": test_case["query"],
                    "success": success,
                    "active_personas": active_personas,
                    "confidence": confidence,
                    "response_time_ms": round(response_time * 1000, 2),
                    "persona_match": persona_match,
                    "status": "✅ PASS" if success and persona_match else "❌ FAIL"
                }
                
                results.append(test_result)
                print(f"    {test_result['status']} - {len(active_personas)} personas, {confidence*100:.1f}% confidence, {test_result['response_time_ms']}ms")
                
            except Exception as e:
                print(f"    ❌ FAIL - Error: {str(e)}")
                results.append({
                    "query": test_case["query"],
                    "success": False,
                    "error": str(e),
                    "status": "❌ FAIL"
                })
        
        self.test_results['auto_orchestration'] = results
        
        # Calculate summary
        passed = sum(1 for r in results if r.get('success'))
        total = len(results)
        print(f"  📊 Auto-Orchestration Tests: {passed}/{total} passed")
        
        return passed == total
    
    async def test_cache_system_flow(self):
        """Test multi-level cache system"""
        print("\n💾 Testing Multi-Level Cache System...")
        
        test_keys = [
            ("user_session_123", {"user": "test", "session": "active"}),
            ("api_response_456", {"data": [1, 2, 3, 4, 5], "status": "success"}),
            ("computation_789", {"result": 42, "computed_at": time.time()})
        ]
        
        results = []
        
        # Test cache operations
        for key, value in test_keys:
            try:
                # Test SET operation
                start_time = time.time()
                await self.cache.set(key, value)
                set_time = time.time() - start_time
                
                # Test GET operation (should hit L1)
                start_time = time.time()
                retrieved = await self.cache.get(key)
                get_time = time.time() - start_time
                
                success = retrieved == value
                
                result = {
                    "key": key,
                    "success": success,
                    "set_time_ms": round(set_time * 1000, 3),
                    "get_time_ms": round(get_time * 1000, 3),
                    "status": "✅ PASS" if success else "❌ FAIL"
                }
                
                results.append(result)
                print(f"  {result['status']} Cache {key}: set={result['set_time_ms']}ms, get={result['get_time_ms']}ms")
                
            except Exception as e:
                print(f"  ❌ FAIL Cache {key}: {str(e)}")
                results.append({
                    "key": key,
                    "success": False,
                    "error": str(e),
                    "status": "❌ FAIL"
                })
        
        # Test cache statistics
        try:
            stats = self.cache.get_statistics()
            print(f"  📈 Cache Stats: {stats.get('hit_rate', 'N/A')} hit rate")
            results.append({
                "operation": "statistics",
                "success": bool(stats),
                "stats": stats,
                "status": "✅ PASS" if stats else "❌ FAIL"
            })
        except Exception as e:
            print(f"  ❌ FAIL Cache Statistics: {str(e)}")
        
        self.test_results['cache_system'] = results
        
        passed = sum(1 for r in results if r.get('success'))
        total = len(results)
        print(f"  📊 Cache Tests: {passed}/{total} passed")
        
        return passed == total
    
    async def test_connection_pool_flow(self):
        """Test connection pooling system"""
        print("\n🔗 Testing Connection Pool System...")
        
        results = []
        
        try:
            # Test HTTP connection pool
            async with self.pool.get_http_client() as client:
                start_time = time.time()
                # Test with a reliable endpoint
                async with client.get('http://httpbin.org/json') as response:
                    data = await response.json()
                    response_time = time.time() - start_time
                    
                    success = response.status == 200
                    
                    result = {
                        "connection_type": "http",
                        "success": success,
                        "response_time_ms": round(response_time * 1000, 2),
                        "status_code": response.status,
                        "status": "✅ PASS" if success else "❌ FAIL"
                    }
                    
                    results.append(result)
                    print(f"  {result['status']} HTTP Pool: {result['response_time_ms']}ms, status {result['status_code']}")
                    
        except Exception as e:
            print(f"  ❌ FAIL HTTP Pool: {str(e)}")
            results.append({
                "connection_type": "http",
                "success": False,
                "error": str(e),
                "status": "❌ FAIL"
            })
        
        # Test pool statistics
        try:
            stats = self.pool.get_statistics()
            print(f"  📈 Pool Stats: {len(stats)} pool types")
            
            results.append({
                "operation": "statistics",
                "success": bool(stats),
                "stats": stats,
                "status": "✅ PASS" if stats else "❌ FAIL"
            })
        except Exception as e:
            print(f"  ❌ FAIL Pool Statistics: {str(e)}")
        
        self.test_results['connection_pool'] = results
        
        passed = sum(1 for r in results if r.get('success'))
        total = len(results)
        print(f"  📊 Connection Pool Tests: {passed}/{total} passed")
        
        return passed == total
    
    async def test_persona_system_flow(self):
        """Test persona management system"""
        print("\n👤 Testing Persona System...")
        
        results = []
        
        try:
            # Test getting all personas
            personas = self.persona_manager.get_all_personas()
            
            result = {
                "operation": "get_all_personas",
                "success": len(personas) > 0,
                "persona_count": len(personas),
                "status": "✅ PASS" if len(personas) > 0 else "❌ FAIL"
            }
            
            results.append(result)
            print(f"  {result['status']} Found {result['persona_count']} personas")
            
            # Test specific persona retrieval
            test_personas = ['backend', 'frontend', 'devops', 'architect']
            for persona_id in test_personas:
                try:
                    persona = self.persona_manager.get_persona(persona_id)
                    success = persona is not None
                    
                    result = {
                        "operation": f"get_persona_{persona_id}",
                        "success": success,
                        "persona_found": bool(persona),
                        "status": "✅ PASS" if success else "❌ FAIL"
                    }
                    
                    results.append(result)
                    print(f"  {result['status']} Persona {persona_id}: {'found' if success else 'not found'}")
                    
                except Exception as e:
                    print(f"  ❌ FAIL Persona {persona_id}: {str(e)}")
                    results.append({
                        "operation": f"get_persona_{persona_id}",
                        "success": False,
                        "error": str(e),
                        "status": "❌ FAIL"
                    })
            
            # Test persona categories
            categories = self.persona_manager.persona_categories
            result = {
                "operation": "get_categories",
                "success": len(categories) > 0,
                "category_count": len(categories),
                "categories": list(categories.keys()),
                "status": "✅ PASS" if len(categories) > 0 else "❌ FAIL"
            }
            
            results.append(result)
            print(f"  {result['status']} Found {result['category_count']} categories: {', '.join(result['categories'])}")
            
        except Exception as e:
            print(f"  ❌ FAIL Persona System: {str(e)}")
            results.append({
                "operation": "persona_system",
                "success": False,
                "error": str(e),
                "status": "❌ FAIL"
            })
        
        self.test_results['persona_system'] = results
        
        passed = sum(1 for r in results if r.get('success'))
        total = len(results)
        print(f"  📊 Persona Tests: {passed}/{total} passed")
        
        return passed == total
    
    async def test_plugin_system_flow(self):
        """Test plugin system"""
        print("\n🔌 Testing Plugin System...")
        
        results = []
        
        try:
            # Test plugin discovery
            plugins = await self.plugin_manager.discover_plugins()
            
            result = {
                "operation": "discover_plugins",
                "success": True,  # Discovery should always work, even if 0 plugins
                "plugin_count": len(plugins),
                "status": "✅ PASS"
            }
            
            results.append(result)
            print(f"  {result['status']} Discovered {result['plugin_count']} plugins")
            
            # Test plugin listing
            plugin_list = self.plugin_manager.list_plugins()
            
            result = {
                "operation": "list_plugins",
                "success": isinstance(plugin_list, list),
                "listed_count": len(plugin_list),
                "status": "✅ PASS" if isinstance(plugin_list, list) else "❌ FAIL"
            }
            
            results.append(result)
            print(f"  {result['status']} Listed {result['listed_count']} plugins")
            
            # Test command listing
            commands = self.plugin_manager.list_commands()
            
            result = {
                "operation": "list_commands",
                "success": isinstance(commands, list),
                "command_count": len(commands),
                "status": "✅ PASS" if isinstance(commands, list) else "❌ FAIL"
            }
            
            results.append(result)
            print(f"  {result['status']} Found {result['command_count']} plugin commands")
            
        except Exception as e:
            print(f"  ❌ FAIL Plugin System: {str(e)}")
            results.append({
                "operation": "plugin_system",
                "success": False,
                "error": str(e),
                "status": "❌ FAIL"
            })
        
        self.test_results['plugin_system'] = results
        
        passed = sum(1 for r in results if r.get('success'))
        total = len(results)
        print(f"  📊 Plugin Tests: {passed}/{total} passed")
        
        return passed == total
    
    async def test_integration_workflow(self):
        """Test complete integration workflow"""
        print("\n🔄 Testing Complete Integration Workflow...")
        
        results = []
        workflow_start = time.time()
        
        try:
            # Step 1: Auto-orchestration selects personas
            print("  Step 1: Auto-orchestration...")
            result = await auto_orchestrator.process_message(
                f"{self.session_id}_integration",
                "Crear una aplicación web completa con autenticación y base de datos"
            )
            
            orchestration_success = result.get('orchestration_performed', False)
            active_personas = result.get('active_personas', [])
            
            # Step 2: Cache some computation result
            print("  Step 2: Caching computation...")
            computation_key = "integration_test_computation"
            computation_result = {
                "workflow_id": f"{self.session_id}_integration",
                "personas_selected": active_personas,
                "timestamp": time.time()
            }
            
            await self.cache.set(computation_key, computation_result)
            cached_result = await self.cache.get(computation_key)
            cache_success = cached_result == computation_result
            
            # Step 3: Test connection pooling during workflow
            print("  Step 3: Testing connections during workflow...")
            async with self.pool.get_http_client() as client:
                async with client.get('http://httpbin.org/status/200') as response:
                    connection_success = response.status == 200
            
            # Step 4: Get system statistics
            print("  Step 4: Collecting system statistics...")
            cache_stats = self.cache.get_statistics()
            pool_stats = self.pool.get_statistics()
            
            workflow_time = time.time() - workflow_start
            
            # Evaluate overall workflow
            overall_success = (
                orchestration_success and 
                cache_success and 
                connection_success and
                bool(cache_stats) and
                bool(pool_stats)
            )
            
            workflow_result = {
                "operation": "complete_integration_workflow",
                "success": overall_success,
                "workflow_time_ms": round(workflow_time * 1000, 2),
                "steps": {
                    "orchestration": {
                        "success": orchestration_success,
                        "personas_count": len(active_personas)
                    },
                    "caching": {
                        "success": cache_success
                    },
                    "connections": {
                        "success": connection_success
                    },
                    "statistics": {
                        "cache_stats": bool(cache_stats),
                        "pool_stats": bool(pool_stats)
                    }
                },
                "status": "✅ PASS" if overall_success else "❌ FAIL"
            }
            
            results.append(workflow_result)
            print(f"  {workflow_result['status']} Integration Workflow: {workflow_result['workflow_time_ms']}ms")
            
            # Detailed step results
            for step, step_data in workflow_result["steps"].items():
                step_status = "✅" if step_data["success"] else "❌"
                print(f"    {step_status} {step.title()}: {'success' if step_data['success'] else 'failed'}")
            
        except Exception as e:
            print(f"  ❌ FAIL Integration Workflow: {str(e)}")
            results.append({
                "operation": "complete_integration_workflow",
                "success": False,
                "error": str(e),
                "status": "❌ FAIL"
            })
        
        self.test_results['integration_workflow'] = results
        
        passed = sum(1 for r in results if r.get('success'))
        total = len(results)
        print(f"  📊 Integration Tests: {passed}/{total} passed")
        
        return passed == total
    
    async def cleanup(self):
        """Cleanup test environment"""
        print("\n🧹 Cleaning up test environment...")
        
        try:
            # Clear cache
            await self.cache.invalidate(f"integration_test_computation")
            
            # Shutdown connection pool
            # await self.pool.shutdown()  # Don't shutdown as it might be used elsewhere
            
            print("✅ Cleanup completed")
        except Exception as e:
            print(f"⚠️ Cleanup warning: {str(e)}")
    
    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "="*70)
        print("📊 COMPREHENSIVE E2E TEST REPORT")
        print("="*70)
        
        total_passed = 0
        total_tests = 0
        
        for test_suite, results in self.test_results.items():
            if isinstance(results, list):
                passed = sum(1 for r in results if r.get('success'))
                total = len(results)
            else:
                passed = 1 if results.get('success') else 0
                total = 1
            
            total_passed += passed
            total_tests += total
            
            status_emoji = "✅" if passed == total else "❌"
            print(f"{status_emoji} {test_suite.replace('_', ' ').title()}: {passed}/{total} passed")
        
        print("-"*70)
        overall_success = total_passed == total_tests
        overall_emoji = "✅" if overall_success else "❌"
        success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"{overall_emoji} OVERALL: {total_passed}/{total_tests} tests passed ({success_rate:.1f}%)")
        
        if overall_success:
            print("🎉 ALL SYSTEMS OPERATIONAL - NubemSuperFClaude is ready for production!")
        else:
            print("⚠️  SOME TESTS FAILED - Review and fix issues before production deployment")
        
        print("="*70)
        
        # Save detailed report
        report_data = {
            "timestamp": time.time(),
            "overall_success": overall_success,
            "total_passed": total_passed,
            "total_tests": total_tests,
            "success_rate": success_rate,
            "detailed_results": self.test_results
        }
        
        report_path = Path("tests/e2e_test_report.json")
        report_path.parent.mkdir(exist_ok=True)
        
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        print(f"📄 Detailed report saved to: {report_path}")
        
        return overall_success


async def main():
    """Run complete E2E test suite"""
    print("🚀 Starting NubemSuperFClaude E2E Test Suite...")
    
    suite = E2ETestSuite()
    
    try:
        # Setup
        await suite.setup()
        
        # Run all test flows
        test_results = []
        
        test_results.append(await suite.test_auto_orchestration_flow())
        test_results.append(await suite.test_cache_system_flow())
        test_results.append(await suite.test_connection_pool_flow())
        test_results.append(await suite.test_persona_system_flow())
        test_results.append(await suite.test_plugin_system_flow())
        test_results.append(await suite.test_integration_workflow())
        
        # Cleanup
        await suite.cleanup()
        
        # Generate report
        overall_success = suite.generate_report()
        
        return overall_success
        
    except Exception as e:
        print(f"❌ E2E Test Suite failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)