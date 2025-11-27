# NubemSuperFClaude MCP Server

Model Context Protocol server for Claude Code CLI integration.

## 🚀 Quick Start

### 1. Configure Claude Code CLI

```bash
mkdir -p ~/.config/claude
cp claude_mcp_config.json ~/.config/claude/mcp.json
```

### 2. Use from Claude Code CLI

```bash
claude
> "List available MCP tools"
> "List all personas from NubemSuperFClaude"
> "Use persona senior-developer to optimize Python code"
```

## 📦 Files

- `server.py` - MCP server implementation (500+ lines)
- `test_mcp.py` - Test suite
- `claude_mcp_config.json` - Configuration for Claude Code CLI
- `README.md` - This file

## 🛠️ Tools Exposed

1. **orchestrate** - Main orchestration
2. **use_persona** - Use specific persona (93 available)
3. **list_personas** - List all personas
4. **generate_embeddings** - 384D embeddings (TF-IDF)
5. **semantic_similarity** - Calculate similarity
6. **validate_input** - Security validation
7. **get_system_status** - System information

## 📚 Resources Exposed

1. **personas://all** - Complete persona list
2. **config://settings** - System configuration
3. **stats://orchestrator** - Usage statistics

## ✅ Testing

```bash
python3 test_mcp.py
```

Expected output:
```
✅ ALL TESTS PASSED!
🎉 MCP Server is working correctly!
```

## 📖 Documentation

See [MCP_INTEGRATION_GUIDE.md](../MCP_INTEGRATION_GUIDE.md) for complete guide.

## 🤝 Integration

This MCP server exposes the complete NubemSuperFClaude framework:
- 93 AI Personas
- RAG System
- Vector Memory
- Embeddings (TF-IDF fallback)
- Multi-LLM orchestration
- Python 3.9+ compatible

🤖 Generated with [Claude Code](https://claude.com/claude-code)
