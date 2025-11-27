#!/usr/bin/env python3
"""
Integration Test for HTTP Server with Auth Middleware
Tests the complete authentication flow in http_server.py
"""

import os
import sys
import json
import asyncio
import aiohttp
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock Kubernetes secrets by setting environment variables
# This allows local testing without K8s cluster
print("\n🔧 Setting up mock environment (simulating K8s secrets)...\n")

# Admin user config
admin_config = {
    "api_key": "nsfc_admin_q8D4DLmEKH1GSJp406P-Gooyj-4Q_uOdxk3xBC9Rggg",
    "user_email": "david.anguera@nubemsystems.es",
    "role": "admin",
    "created_at": "2025-10-23",
    "status": "active"
}

# Readonly user config
readonly_config = {
    "api_key": "nsfc_readonly_O0_h10lWcBO31DmPVIgQmq-lpxq_ThyM3VczXDN-4fc",
    "user_email": "joseluis.manzanares@nubemsystems.es",
    "role": "readonly",
    "created_at": "2025-10-23",
    "status": "active"
}

# Roles configuration
roles_config = {
    "roles": {
        "admin": {
            "permissions": {
                "mcps": ["*"],
                "operations": ["read", "write", "delete", "execute"],
                "blocked_mcps": []
            },
            "rate_limit": {
                "requests_per_minute": 100,
                "burst": 20
            }
        },
        "readonly": {
            "permissions": {
                "mcps": [
                    "intelligent_respond",
                    "list_personas",
                    "use_persona",
                    "orchestrate",
                    "get_system_status",
                    "generate_embeddings",
                    "semantic_similarity",
                    "validate_input"
                ],
                "operations": ["read"],
                "blocked_mcps": [
                    "kubernetes",
                    "docker",
                    "gcp",
                    "github",
                    "filesystem",
                    "terraform",
                    "intelligent_execute"
                ]
            },
            "rate_limit": {
                "requests_per_minute": 30,
                "burst": 5
            }
        }
    }
}

# Set environment variables (simulating K8s secrets)
os.environ['MCP_AUTH_ADMIN_CONFIG'] = json.dumps(admin_config)
os.environ['MCP_AUTH_READONLY_CONFIG'] = json.dumps(readonly_config)
os.environ['MCP_AUTH_ROLES_CONFIG'] = json.dumps(roles_config)

print("✅ Mock environment configured\n")


async def test_http_auth_integration():
    """Test HTTP server with authentication middleware"""

    print("=" * 70)
    print("🧪 TESTING HTTP SERVER AUTHENTICATION INTEGRATION")
    print("=" * 70 + "\n")

    # Test configuration
    base_url = "http://localhost:8080"
    admin_api_key = admin_config["api_key"]
    readonly_api_key = readonly_config["api_key"]
    invalid_api_key = "nsfc_invalid_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

    tests_passed = 0
    tests_failed = 0

    # Give server time to start (if running separately)
    print("⏳ Waiting for server to be ready...\n")
    await asyncio.sleep(2)

    async with aiohttp.ClientSession() as session:

        # Test 1: Health check (public endpoint, no auth required)
        print("Test 1: Health check endpoint (public, no auth)")
        print("-" * 70)
        try:
            async with session.get(f"{base_url}/health") as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("status") == "healthy":
                    print(f"✅ Status: {resp.status}")
                    print(f"✅ Response: {json.dumps(data, indent=2)}")
                    print("✅ PASS: Public endpoint accessible without auth\n")
                    tests_passed += 1
                else:
                    print(f"❌ FAIL: Expected 200, got {resp.status}\n")
                    tests_failed += 1
        except Exception as e:
            print(f"❌ FAIL: {e}\n")
            tests_failed += 1


        # Test 2: Request without API key (should return 401)
        print("Test 2: Request without API key")
        print("-" * 70)
        try:
            async with session.get(f"{base_url}/tools/list") as resp:
                data = await resp.json()
                if resp.status == 401:
                    print(f"✅ Status: {resp.status} (Unauthorized)")
                    print(f"✅ Response: {json.dumps(data, indent=2)}")
                    print("✅ PASS: Auth required for protected endpoints\n")
                    tests_passed += 1
                else:
                    print(f"❌ FAIL: Expected 401, got {resp.status}\n")
                    tests_failed += 1
        except Exception as e:
            print(f"❌ FAIL: {e}\n")
            tests_failed += 1


        # Test 3: Request with invalid API key (should return 401)
        print("Test 3: Request with invalid API key")
        print("-" * 70)
        try:
            headers = {"X-API-Key": invalid_api_key}
            async with session.get(f"{base_url}/tools/list", headers=headers) as resp:
                data = await resp.json()
                if resp.status == 401:
                    print(f"✅ Status: {resp.status} (Unauthorized)")
                    print(f"✅ Response: {json.dumps(data, indent=2)}")
                    print("✅ PASS: Invalid API key rejected\n")
                    tests_passed += 1
                else:
                    print(f"❌ FAIL: Expected 401, got {resp.status}\n")
                    tests_failed += 1
        except Exception as e:
            print(f"❌ FAIL: {e}\n")
            tests_failed += 1


        # Test 4: Valid admin API key (should return 200)
        print("Test 4: Valid admin API key")
        print("-" * 70)
        try:
            headers = {"X-API-Key": admin_api_key}
            async with session.get(f"{base_url}/tools/list", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Status: {resp.status} (OK)")
                    print(f"✅ Admin access granted")
                    print(f"✅ X-User-Role header: {resp.headers.get('X-User-Role')}")
                    print("✅ PASS: Admin authenticated successfully\n")
                    tests_passed += 1
                else:
                    print(f"❌ FAIL: Expected 200, got {resp.status}\n")
                    data = await resp.json()
                    print(f"Response: {json.dumps(data, indent=2)}\n")
                    tests_failed += 1
        except Exception as e:
            print(f"❌ FAIL: {e}\n")
            tests_failed += 1


        # Test 5: Valid readonly API key accessing allowed tool
        print("Test 5: Readonly user accessing allowed tool (list_personas)")
        print("-" * 70)
        try:
            headers = {"X-API-Key": readonly_api_key, "Content-Type": "application/json"}
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_personas",
                    "arguments": {}
                },
                "id": 1
            }
            async with session.post(f"{base_url}/mcp", headers=headers, json=payload) as resp:
                if resp.status == 200:
                    print(f"✅ Status: {resp.status} (OK)")
                    print(f"✅ Readonly user allowed to access list_personas")
                    print(f"✅ X-User-Role header: {resp.headers.get('X-User-Role')}")
                    print("✅ PASS: Readonly user can access allowed tools\n")
                    tests_passed += 1
                else:
                    data = await resp.json()
                    print(f"❌ FAIL: Expected 200, got {resp.status}\n")
                    print(f"Response: {json.dumps(data, indent=2)}\n")
                    tests_failed += 1
        except Exception as e:
            print(f"❌ FAIL: {e}\n")
            tests_failed += 1


        # Test 6: Readonly user accessing blocked MCP (should return 403)
        print("Test 6: Readonly user accessing blocked MCP (kubernetes)")
        print("-" * 70)
        try:
            headers = {"X-API-Key": readonly_api_key, "Content-Type": "application/json"}
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "intelligent_execute",
                    "arguments": {
                        "task": "List Kubernetes pods",
                        "mcp_name": "kubernetes"
                    }
                },
                "id": 1
            }
            async with session.post(f"{base_url}/mcp", headers=headers, json=payload) as resp:
                data = await resp.json()
                if resp.status == 403:
                    print(f"✅ Status: {resp.status} (Forbidden)")
                    print(f"✅ Response: {json.dumps(data, indent=2)}")
                    print("✅ PASS: Readonly user blocked from accessing kubernetes MCP\n")
                    tests_passed += 1
                else:
                    print(f"❌ FAIL: Expected 403, got {resp.status}\n")
                    print(f"Response: {json.dumps(data, indent=2)}\n")
                    tests_failed += 1
        except Exception as e:
            print(f"❌ FAIL: {e}\n")
            tests_failed += 1


        # Test 7: Rate limiting (readonly has 30 req/min, 5 burst)
        print("Test 7: Rate limiting (readonly: 5 burst limit)")
        print("-" * 70)
        try:
            headers = {"X-API-Key": readonly_api_key, "Content-Type": "application/json"}
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "get_system_status",
                    "arguments": {}
                },
                "id": 1
            }

            # Make 5 rapid requests (burst limit)
            rate_limited = False
            for i in range(6):
                async with session.post(f"{base_url}/mcp", headers=headers, json=payload) as resp:
                    if resp.status == 429:
                        rate_limited = True
                        data = await resp.json()
                        print(f"✅ Request {i+1}: Status 429 (Rate Limited)")
                        print(f"✅ Response: {json.dumps(data, indent=2)}")
                        break
                    elif i < 5:
                        print(f"   Request {i+1}: Status {resp.status} (OK)")

            if rate_limited:
                print("✅ PASS: Rate limiting enforced correctly\n")
                tests_passed += 1
            else:
                print("❌ FAIL: Rate limiting not enforced\n")
                tests_failed += 1

        except Exception as e:
            print(f"❌ FAIL: {e}\n")
            tests_failed += 1


    # Summary
    print("=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    print(f"✅ Passed: {tests_passed}/7")
    print(f"❌ Failed: {tests_failed}/7")
    print("=" * 70 + "\n")

    if tests_failed == 0:
        print("🎉 ALL TESTS PASSED! Authentication integration is working correctly.\n")
        return True
    else:
        print(f"⚠️  {tests_failed} test(s) failed. Please review.\n")
        return False


async def main():
    """Main test runner"""
    print("\n" + "=" * 70)
    print("🚀 HTTP SERVER AUTHENTICATION INTEGRATION TEST")
    print("=" * 70)
    print("\n⚠️  IMPORTANT: Make sure the HTTP server is running:")
    print("   cd /Users/david/NubemSuperFClaude_git")
    print("   python3 mcp_server/http_server.py\n")
    print("Press Ctrl+C to cancel, or wait 5 seconds to start testing...")
    print("=" * 70 + "\n")

    try:
        await asyncio.sleep(5)
        result = await test_http_auth_integration()
        return result
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user.\n")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
