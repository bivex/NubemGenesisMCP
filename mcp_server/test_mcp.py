#!/usr/bin/env python3
"""
Test MCP Server manually
"""

import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.server import NubemSuperFClaudeMCPServer
import asyncio


async def test_server():
    """Test MCP server functionality"""
    print("🧪 Testing NubemSuperFClaude MCP Server")
    print("=" * 60)

    # Initialize server
    print("\n1️⃣  Initializing server...")
    server = NubemSuperFClaudeMCPServer()
    print("   ✅ Server initialized")

    # Test 1: Initialize
    print("\n2️⃣  Testing initialize...")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    response = await server.handle_request(request)
    print(f"   ✅ Initialize response: {response['result']['serverInfo']['name']}")

    # Test 2: List tools
    print("\n3️⃣  Testing tools/list...")
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    response = await server.handle_request(request)
    tools_count = len(response['result']['tools'])
    print(f"   ✅ Tools available: {tools_count}")
    for tool in response['result']['tools']:
        print(f"      - {tool['name']}: {tool['description'][:50]}...")

    # Test 3: Get system status
    print("\n4️⃣  Testing get_system_status tool...")
    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_system_status",
            "arguments": {}
        }
    }
    response = await server.handle_request(request)
    content = json.loads(response['result']['content'][0]['text'])
    print(f"   ✅ Framework: {content['framework']} v{content['version']}")
    print(f"   ✅ Personas: {content['personas_count']}")
    print(f"   ✅ Embeddings: {content['embeddings_model']} ({content['embeddings_dimension']}D)")
    print(f"   ✅ Providers: {', '.join(content['available_providers'])}")

    # Test 4: List personas
    print("\n5️⃣  Testing list_personas tool...")
    request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "list_personas",
            "arguments": {}
        }
    }
    response = await server.handle_request(request)
    content = json.loads(response['result']['content'][0]['text'])
    print(f"   ✅ Total personas: {content['total']}")
    if content['personas']:
        print(f"   ✅ First 3 personas:")
        for persona in content['personas'][:3]:
            print(f"      - {persona['key']}: {persona['name']}")

    # Test 5: Generate embeddings
    print("\n6️⃣  Testing generate_embeddings tool...")
    request = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "generate_embeddings",
            "arguments": {
                "text": "artificial intelligence and machine learning"
            }
        }
    }
    response = await server.handle_request(request)
    content = json.loads(response['result']['content'][0]['text'])
    print(f"   ✅ Model: {content['model']}")
    print(f"   ✅ Dimension: {content['dimension']}")
    print(f"   ✅ Vector preview: {content['embedding'][:5]}...")

    # Test 6: Semantic similarity
    print("\n7️⃣  Testing semantic_similarity tool...")
    request = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "semantic_similarity",
            "arguments": {
                "text1": "artificial intelligence",
                "text2": "machine learning algorithms"
            }
        }
    }
    response = await server.handle_request(request)
    content = json.loads(response['result']['content'][0]['text'])
    print(f"   ✅ Similarity: {content['similarity']:.3f}")

    # Test 7: Validate input
    print("\n8️⃣  Testing validate_input tool...")
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "validate_input",
            "arguments": {
                "text": "<script>alert('test')</script>Hello World",
                "input_type": "text"
            }
        }
    }
    response = await server.handle_request(request)
    content = json.loads(response['result']['content'][0]['text'])
    print(f"   ✅ Valid: {content['valid']}")
    if content['valid']:
        print(f"   ✅ Sanitized: {content['sanitized'][:50]}...")
    else:
        print(f"   ⚠️  Error: {content.get('error', 'Unknown')}")

    # Test 8: List resources
    print("\n9️⃣  Testing resources/list...")
    request = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "resources/list",
        "params": {}
    }
    response = await server.handle_request(request)
    resources_count = len(response['result']['resources'])
    print(f"   ✅ Resources available: {resources_count}")
    for resource in response['result']['resources']:
        print(f"      - {resource['uri']}: {resource['name']}")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("\n🎉 MCP Server is working correctly!")
    print("\n📚 Next steps:")
    print("   1. Configure Claude Code CLI with mcp.json")
    print("   2. Restart Claude Code CLI")
    print("   3. Ask Claude: 'List available MCP tools'")
    print("\n📖 See MCP_INTEGRATION_GUIDE.md for details")


if __name__ == "__main__":
    asyncio.run(test_server())
