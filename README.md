# Cloud Genesis MCP

Infrastructure as code meets Model Context Protocol. Cloud-native automation platform.

## Architecture

A Python-based MCP server with modular core components:

| Module | Description |
|--------|-------------|
| `config_loader.py` | Configuration management |
| `secrets_manager.py` / `secure_secrets_manager.py` | Secrets and credentials handling |
| `tenant_provisioning.py` | Multi-tenant provisioning |
| `personas.py` / `personas_schema.py` | Agent persona management |
| `enhanced_claude_integration.py` | Claude API integration |
| `unified_llm_adapter.py` | Unified LLM provider adapter |
| `context_manager.py` | Conversation context management |
| `response_synthesizer.py` | Response generation |
| `rate_limiting.py` | Request rate limiting |
| `sqlite_audit_logger.py` | Audit logging |
| `github_handler.py` | GitHub integration |
| `shared_memory.py` | Shared state management |
| `rich_cli.py` | CLI interface |

## Getting Started

```bash
pip install -r requirements.txt
python -m core.config_loader
```

## License

See [LICENSE](LICENSE) for details.
