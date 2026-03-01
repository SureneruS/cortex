from pathlib import Path

import yaml

_TYPE_CHECKERS: dict[str, type] = {
    "string": str,
    "integer": int,
    "datetime": str,
}


def load_schema(schema_path: Path) -> dict:
    return yaml.safe_load(schema_path.read_text())


def _check_type(value: object, expected_type: str) -> bool:
    if expected_type.startswith("list["):
        inner = expected_type[5:-1]  # e.g. "string" from "list[string]"
        if not isinstance(value, list):
            return False
        inner_py = _TYPE_CHECKERS.get(inner)
        if inner_py is None:
            return True
        return all(isinstance(item, inner_py) for item in value)

    py_type = _TYPE_CHECKERS.get(expected_type)
    if py_type is None:
        return True
    return isinstance(value, py_type)


def validate_frontmatter(metadata: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    fields = schema.get("fields", {})

    for name, spec in fields.items():
        required = spec.get("required", False)
        if name not in metadata:
            if required:
                errors.append(f"Missing required field: {name}")
            continue

        expected = spec.get("type")
        if expected and not _check_type(metadata[name], expected):
            errors.append(
                f"Field '{name}' expected {expected}, got {type(metadata[name]).__name__}"
            )

    return errors
