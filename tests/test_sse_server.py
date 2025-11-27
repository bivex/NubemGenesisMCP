#!/usr/bin/env python3
"""
Comprehensive tests for SSE MCP Server
Tests SSE transport, session management, and MCP protocol compliance
"""

import asyncio
import aiohttp
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SSEServerTester:
    """Tester for SSE MCP Server"""

    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
        self.session_id = None
        self.results = {
            "passed": 0,
            "failed": 0,
            "errors": []
        }

    async def run_all_tests(self):
        """Run all tests"""
        print("🧪 Starting SSE Server Test Suite")
        print("=" * 70)

        async with aiohttp.ClientSession() as session:
            self.session = session

            # Basic Tests
            await self.test_health_check()
            await self.test_status()

            # MCP Protocol Tests
            await self.test_tools_list()
            await self.test_personas_list()

            # SSE Transport Tests
            await self.test_mcp_post_json_response()
            await self.test_mcp_post_sse_response()
            await self.test_mcp_get_stream()
            await self.test_session_management()
            await self.test_session_resumability()

            # Tool Execution Tests
            await self.test_system_status_tool()
            await self.test_list_personas_tool()
            await self.test_generate_embeddings_tool()

            # Stress Tests
            await self.test_concurrent_requests()
            await self.test_long_running_stream()

        # Print results
        print("\n" + "=" * 70)
        print(f"✅ Tests Passed: {self.results['passed']}")
        print(f"❌ Tests Failed: {self.results['failed']}")

        if self.results['errors']:
            print("\n❌ Errors:")
            for error in self.results['errors']:
                print(f"  - {error}")

        return self.results['failed'] == 0

    def log_test(self, name, passed, details=""):
        """Log test result"""
        if passed:
            self.results['passed'] += 1
            print(f"✅ {name}")
            if details:
                print(f"   {details}")
        else:
            self.results['failed'] += 1
            print(f"❌ {name}")
            if details:
                print(f"   {details}")
                self.results['errors'].append(f"{name}: {details}")

    async def test_health_check(self):
        """Test /health endpoint"""
        try:
            async with self.session.get(f"{self.base_url}/health") as resp:
                data = await resp.json()
                passed = (
                    resp.status == 200 and
                    data.get('status') == 'healthy' and
                    data.get('transport') == 'streamable-http'
                )
                self.log_test(
                    "Health Check",
                    passed,
                    f"Status: {data.get('status')}, Transport: {data.get('transport')}"
                )
        except Exception as e:
            self.log_test("Health Check", False, str(e))

    async def test_status(self):
        """Test /status endpoint"""
        try:
            async with self.session.get(f"{self.base_url}/status") as resp:
                data = await resp.json()
                passed = resp.status == 200 and 'jsonrpc' in data
                self.log_test("System Status", passed, f"Response: {resp.status}")
        except Exception as e:
            self.log_test("System Status", False, str(e))

    async def test_tools_list(self):
        """Test /tools/list endpoint"""
        try:
            async with self.session.get(f"{self.base_url}/tools/list") as resp:
                data = await resp.json()
                tools = data.get('result', {}).get('tools', [])
                passed = resp.status == 200 and len(tools) > 0
                self.log_test(
                    "Tools List",
                    passed,
                    f"Found {len(tools)} tools"
                )
        except Exception as e:
            self.log_test("Tools List", False, str(e))

    async def test_personas_list(self):
        """Test /personas/list endpoint"""
        try:
            async with self.session.get(f"{self.base_url}/personas/list") as resp:
                data = await resp.json()
                passed = resp.status == 200 and 'jsonrpc' in data
                self.log_test("Personas List", passed)
        except Exception as e:
            self.log_test("Personas List", False, str(e))

    async def test_mcp_post_json_response(self):
        """Test POST /mcp with JSON response"""
        try:
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            async with self.session.post(
                f"{self.base_url}/mcp",
                json=request,
                headers=headers
            ) as resp:
                data = await resp.json()
                session_id = resp.headers.get('Mcp-Session-Id')

                passed = (
                    resp.status == 200 and
                    data.get('jsonrpc') == '2.0' and
                    session_id is not None
                )

                if passed:
                    self.session_id = session_id

                self.log_test(
                    "MCP POST (JSON Response)",
                    passed,
                    f"Session-ID: {session_id}"
                )
        except Exception as e:
            self.log_test("MCP POST (JSON Response)", False, str(e))

    async def test_mcp_post_sse_response(self):
        """Test POST /mcp with SSE response"""
        try:
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json"
            }

            async with self.session.post(
                f"{self.base_url}/mcp",
                json=request,
                headers=headers
            ) as resp:
                content_type = resp.headers.get('Content-Type', '')
                passed = (
                    resp.status == 200 and
                    'text/event-stream' in content_type
                )

                # Read one SSE event
                if passed:
                    chunk = await resp.content.read(1024)
                    event_data = chunk.decode('utf-8')
                    passed = 'data:' in event_data

                self.log_test(
                    "MCP POST (SSE Response)",
                    passed,
                    f"Content-Type: {content_type}"
                )
        except Exception as e:
            self.log_test("MCP POST (SSE Response)", False, str(e))

    async def test_mcp_get_stream(self):
        """Test GET /mcp for SSE stream"""
        try:
            headers = {
                "Accept": "text/event-stream"
            }

            if self.session_id:
                headers["Mcp-Session-Id"] = self.session_id

            # Use timeout to avoid hanging
            timeout = aiohttp.ClientTimeout(total=5)

            async with self.session.get(
                f"{self.base_url}/mcp",
                headers=headers,
                timeout=timeout
            ) as resp:
                content_type = resp.headers.get('Content-Type', '')
                passed = (
                    resp.status == 200 and
                    'text/event-stream' in content_type
                )

                # Read first heartbeat
                if passed:
                    try:
                        chunk = await asyncio.wait_for(
                            resp.content.read(1024),
                            timeout=3
                        )
                        event_data = chunk.decode('utf-8')
                        passed = 'data:' in event_data or 'event:' in event_data
                    except asyncio.TimeoutError:
                        passed = False

                self.log_test(
                    "MCP GET (SSE Stream)",
                    passed,
                    f"Content-Type: {content_type}"
                )
        except asyncio.TimeoutError:
            self.log_test("MCP GET (SSE Stream)", False, "Timeout waiting for stream")
        except Exception as e:
            self.log_test("MCP GET (SSE Stream)", False, str(e))

    async def test_session_management(self):
        """Test session creation and tracking"""
        try:
            # First request without session ID
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1
            }

            async with self.session.post(
                f"{self.base_url}/mcp",
                json=request,
                headers={"Accept": "application/json"}
            ) as resp:
                session_id_1 = resp.headers.get('Mcp-Session-Id')

            # Second request with session ID
            async with self.session.post(
                f"{self.base_url}/mcp",
                json=request,
                headers={
                    "Accept": "application/json",
                    "Mcp-Session-Id": session_id_1
                }
            ) as resp:
                session_id_2 = resp.headers.get('Mcp-Session-Id')

            passed = session_id_1 and session_id_1 == session_id_2

            self.log_test(
                "Session Management",
                passed,
                f"Session maintained: {session_id_1 == session_id_2}"
            )
        except Exception as e:
            self.log_test("Session Management", False, str(e))

    async def test_session_resumability(self):
        """Test SSE stream resumability with Last-Event-ID"""
        try:
            # This test would require capturing event IDs from a stream
            # For now, we just test that the header is accepted
            headers = {
                "Accept": "text/event-stream",
                "Last-Event-ID": "test-session-1"
            }

            timeout = aiohttp.ClientTimeout(total=3)

            async with self.session.get(
                f"{self.base_url}/mcp",
                headers=headers,
                timeout=timeout
            ) as resp:
                passed = resp.status == 200

            self.log_test("Session Resumability", passed)
        except Exception as e:
            self.log_test("Session Resumability", False, str(e))

    async def test_system_status_tool(self):
        """Test get_system_status tool"""
        try:
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "get_system_status",
                    "arguments": {}
                },
                "id": 1
            }

            async with self.session.post(
                f"{self.base_url}/mcp",
                json=request,
                headers={"Accept": "application/json"}
            ) as resp:
                data = await resp.json()
                passed = (
                    resp.status == 200 and
                    data.get('jsonrpc') == '2.0' and
                    'result' in data
                )

            self.log_test("System Status Tool", passed)
        except Exception as e:
            self.log_test("System Status Tool", False, str(e))

    async def test_list_personas_tool(self):
        """Test list_personas tool"""
        try:
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_personas",
                    "arguments": {}
                },
                "id": 1
            }

            async with self.session.post(
                f"{self.base_url}/mcp",
                json=request,
                headers={"Accept": "application/json"}
            ) as resp:
                data = await resp.json()
                passed = resp.status == 200 and 'result' in data

            self.log_test("List Personas Tool", passed)
        except Exception as e:
            self.log_test("List Personas Tool", False, str(e))

    async def test_generate_embeddings_tool(self):
        """Test generate_embeddings tool"""
        try:
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "generate_embeddings",
                    "arguments": {
                        "text": "test embedding generation"
                    }
                },
                "id": 1
            }

            async with self.session.post(
                f"{self.base_url}/mcp",
                json=request,
                headers={"Accept": "application/json"}
            ) as resp:
                data = await resp.json()
                passed = resp.status == 200 and 'result' in data

            self.log_test("Generate Embeddings Tool", passed)
        except Exception as e:
            self.log_test("Generate Embeddings Tool", False, str(e))

    async def test_concurrent_requests(self):
        """Test concurrent requests handling"""
        try:
            tasks = []
            for i in range(10):
                request = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": i
                }

                task = self.session.post(
                    f"{self.base_url}/mcp",
                    json=request,
                    headers={"Accept": "application/json"}
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            successful = sum(
                1 for r in responses
                if not isinstance(r, Exception) and r.status == 200
            )

            passed = successful == 10

            self.log_test(
                "Concurrent Requests",
                passed,
                f"{successful}/10 successful"
            )
        except Exception as e:
            self.log_test("Concurrent Requests", False, str(e))

    async def test_long_running_stream(self):
        """Test long-running SSE stream with heartbeats"""
        try:
            headers = {
                "Accept": "text/event-stream"
            }

            timeout = aiohttp.ClientTimeout(total=35)  # 35 seconds

            async with self.session.get(
                f"{self.base_url}/mcp",
                headers=headers,
                timeout=timeout
            ) as resp:
                # Read for 32 seconds (should get at least 1 heartbeat at 30s)
                start_time = asyncio.get_event_loop().time()
                events_received = 0

                while asyncio.get_event_loop().time() - start_time < 32:
                    try:
                        chunk = await asyncio.wait_for(
                            resp.content.read(1024),
                            timeout=5
                        )
                        if chunk:
                            events_received += chunk.decode('utf-8').count('data:')
                    except asyncio.TimeoutError:
                        break

                passed = events_received > 0

            self.log_test(
                "Long-Running Stream",
                passed,
                f"{events_received} events in 32s"
            )
        except Exception as e:
            self.log_test("Long-Running Stream", False, str(e))


async def main():
    """Main test runner"""
    import argparse

    parser = argparse.ArgumentParser(description='Test SSE MCP Server')
    parser.add_argument(
        '--url',
        default='http://localhost:8080',
        help='Base URL of MCP server (default: http://localhost:8080)'
    )

    args = parser.parse_args()

    tester = SSEServerTester(base_url=args.url)
    success = await tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
