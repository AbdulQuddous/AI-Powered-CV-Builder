import json
from functools import lru_cache
from pathlib import Path
from django.conf import settings
from jsonschema import validators

@lru_cache(maxsize=1)
def load_cv_schema():
    path = (
        Path(settings.BASE_DIR) / "shared" / "schemas" / "cv_schema.json"
    )
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)

def get_cv_errors(cv):
    """
    Return structural validation errors.
    Uses the schema already owned by M10.
    """
    schema = load_cv_schema()
    validator_class = validators.validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema)
    return [
        error.message for error in validator.iter_errors(cv)
    ]

def gemini_compatible_schema(schema):
    """
    Remove JSON Schema keywords unsupported by Gemini while preserving the local M10 contract.
    Always validate the returned result again against the ORIGINAL M10 schema.
    """
    supported = {
        "$ref",
        "$id",
        "$anchor",
        "type",
        "format",
        "title",
        "description",
        "enum",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "required",
        "additionalProperties",
    }

    def clean(node):
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return {"$ref": node["$ref"]}
        
        result = {
            key: value for key, value in node.items() if key in supported
        }
        
        # Preserve fixed-value schema requirements.
        if "const" in node:
            result["enum"] = [node["const"]]
            
        # Express unsupported regex constraints as instructions.
        if "pattern" in node:
            description = result.get("description", "")
            result["description"] = (
                f"{description} "
                f"Value must match: {node['pattern']}"
            ).strip()

        if "properties" in node:
            result["properties"] = {
                key: clean(value) for key, value in node["properties"].items()
            }
        if "$defs" in node:
            result["$defs"] = {
                key: clean(value) for key, value in node["$defs"].items()
            }
        if "definitions" in node:
            result["$defs"] = {
                key: clean(value) for key, value in node["definitions"].items()
            }
        if "items" in node:
            result["items"] = clean(node["items"])
        for keyword in ("anyOf", "oneOf"):
            if keyword in node:
                result[keyword] = [
                    clean(item) for item in node[keyword]
                ]
        if isinstance(
            node.get("additionalProperties"), dict,
        ):
            result["additionalProperties"] = clean(
                node["additionalProperties"]
            )
        return result

    return clean(schema)

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "message": {"type": "string"},
                    "recommended_action": {"type": "string"},
                },
                "required": [
                    "section",
                    "priority",
                    "message",
                    "recommended_action",
                ],
            },
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
        },
        "gaps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "match_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
    },
    "required": [
        "suggestions",
        "strengths",
        "gaps",
        "match_score",
    ],
}

WRITING_SCHEMA = {
    "type": "object",
    "properties": {
        "rewritten": {
            "type": "string",
        },
        "changes": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "string",
            },
        },
    },
    "required": [
        "rewritten",
        "changes",
    ],
}
