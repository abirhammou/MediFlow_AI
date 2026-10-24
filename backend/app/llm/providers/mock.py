import json
import re
from typing import Any

from app.llm.providers.base import BaseProvider


def _mock_value(
    schema: dict[str, Any],
    root_schema: dict[str, Any] | None = None,
) -> Any:
    root_schema = root_schema or schema
    if "const" in schema:
        return schema["const"]
    reference = schema.get("$ref")
    if reference:
        target: Any = root_schema
        for segment in reference.removeprefix("#/").split("/"):
            target = target[segment.replace("~1", "/").replace("~0", "~")]
        return _mock_value(target, root_schema)
    schema_type = schema.get("type")
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            if option.get("type") != "null":
                return _mock_value(option, root_schema)
        return None
    if schema_type == "object":
        properties = schema.get("properties", {})
        required = set(schema.get("required", properties.keys()))
        return {
            name: _mock_value(value, root_schema)
            for name, value in properties.items()
            if name in required
        }
    if schema_type == "array":
        item_schema = schema.get("items", {})
        count = min(schema.get("minItems", 0), 5)
        return [_mock_value(item_schema, root_schema) for _ in range(count)]
    if schema_type == "integer":
        return schema.get("minimum", 0)
    if schema_type == "number":
        return schema.get("minimum", 0.0)
    if schema_type == "boolean":
        return False
    if schema_type == "null":
        return None
    if schema_type == "string":
        enum = schema.get("enum")
        if enum:
            return enum[0]
        fmt = schema.get("format")
        if fmt == "date":
            return "2025-01-01"
        if fmt == "date-time":
            return "2025-01-01T00:00:00Z"
        if fmt == "email":
            return "mock@example.test"
        value = "Réponse simulée."
        minimum = schema.get("minLength", 1)
        maximum = schema.get("maxLength")
        value = value.ljust(minimum, "x")
        return value[:maximum] if maximum is not None else value
    return {}


class MockProvider(BaseProvider):
    async def complete_json(
        self,
        system: str,
        user: str,
        model: str,
        timeout: float,
    ) -> str:
        match = re.search(r"<output_schema>(.*?)</output_schema>", system, re.DOTALL)
        schema = json.loads(match.group(1)) if match else {"type": "object", "properties": {}}
        return json.dumps(_mock_value(schema, schema), ensure_ascii=False)
