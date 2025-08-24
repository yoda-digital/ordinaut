MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["id", "name", "version", "module"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-zA-Z0-9_\-]+$"},
        "name": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "module": {"type": "string"},
        "enabled": {"type": "boolean", "default": True},
        "grants": {
            "type": "array",
            "items": {"type": "string"}
        },
        "eager": {"type": "boolean", "default": False}
    },
    "additionalProperties": True
}
