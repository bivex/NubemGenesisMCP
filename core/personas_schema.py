"""
JSON Schema for Dynamic Persona Validation
Validates persona YAML files before loading to prevent errors
"""

PERSONA_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "NubemSuperFClaude Dynamic Persona",
    "description": "Schema for validating dynamic persona YAML files",
    "type": "object",
    "required": ["name", "level", "category", "identity", "specialties", "capabilities", "system_prompt"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 50,
            "pattern": "^[a-z][a-z0-9-]*$",
            "description": "Persona identifier in kebab-case (e.g., 'rag-analyst')"
        },
        "level": {
            "type": "string",
            "enum": ["L1", "L2", "L3", "L4", "L5"],
            "description": "Expertise level from L1 (Junior) to L5 (Master)"
        },
        "category": {
            "type": "string",
            "enum": [
                "Core Software Development",
                "Cloud & DevOps",
                "Data & AI",
                "Security & Compliance",
                "Advanced Domains",
                "Meta & Orchestration"
            ],
            "description": "Category for persona classification"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
            "description": "Semantic version (e.g., '1.0.0')"
        },
        "identity": {
            "type": "string",
            "minLength": 50,
            "maxLength": 5000,
            "description": "Detailed identity and role description"
        },
        "specialties": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "string",
                "minLength": 3,
                "maxLength": 100
            },
            "description": "List of specialty areas"
        },
        "capabilities": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_]*$",
                "description": "Capability name in snake_case"
            },
            "description": "List of capabilities the persona can perform"
        },
        "system_prompt": {
            "type": "string",
            "minLength": 100,
            "maxLength": 50000,
            "description": "System prompt that defines persona behavior"
        },
        "commands": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "description"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "example": {"type": "string"}
                }
            },
            "description": "Optional commands the persona understands"
        },
        "confidence_scores": {
            "type": "object",
            "patternProperties": {
                ".*": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1
                }
            },
            "description": "Confidence scores for different domains (0-1)"
        },
        "collaborates_with": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9-]*$"
            },
            "description": "List of persona names this persona collaborates with"
        },
        "deprecated": {
            "type": "boolean",
            "description": "Whether this persona version is deprecated"
        },
        "breaking_changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of breaking changes from previous versions"
        }
    }
    # Note: additionalProperties not set to allow flexibility for extended persona definitions
}


def validate_persona_config(config: dict) -> tuple[bool, str]:
    """
    Validate persona configuration against schema

    Args:
        config: Persona configuration dict loaded from YAML

    Returns:
        Tuple of (is_valid, error_message)
    """
    import jsonschema

    try:
        jsonschema.validate(instance=config, schema=PERSONA_SCHEMA)
        return True, ""
    except jsonschema.ValidationError as e:
        error_path = " -> ".join(str(p) for p in e.path) if e.path else "root"
        error_msg = f"Validation error at {error_path}: {e.message}"
        return False, error_msg
    except jsonschema.SchemaError as e:
        return False, f"Schema error: {e.message}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
