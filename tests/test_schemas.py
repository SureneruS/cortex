from pathlib import Path

from nova.lib.schemas import load_schema, validate_frontmatter

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def test_load_capture_schema():
    schema = load_schema(SCHEMAS_DIR / "capture-v1.yaml")
    assert schema["type"] == "capture"
    assert schema["version"] == 1
    assert "session" in schema["fields"]


def test_valid_capture_frontmatter():
    schema = load_schema(SCHEMAS_DIR / "capture-v1.yaml")
    meta = {
        "session": "abc123",
        "repos": ["recruitment-backend"],
        "transcript": "/path/to/file.jsonl",
        "captured_at": "2026-02-22T14:30:12Z",
        "schema_version": 1,
    }
    errors = validate_frontmatter(meta, schema)
    assert errors == []


def test_missing_required_field():
    schema = load_schema(SCHEMAS_DIR / "capture-v1.yaml")
    meta = {
        "session": "abc123"
    }  # missing repos, transcript, captured_at, schema_version
    errors = validate_frontmatter(meta, schema)
    assert len(errors) >= 4
    assert any("repos" in e for e in errors)


def test_wrong_type():
    schema = load_schema(SCHEMAS_DIR / "capture-v1.yaml")
    meta = {
        "session": "abc123",
        "repos": "not-a-list",  # should be list[string]
        "transcript": "/path",
        "captured_at": "2026-02-22T14:30:12Z",
        "schema_version": 1,
    }
    errors = validate_frontmatter(meta, schema)
    assert len(errors) >= 1
    assert any("repos" in e for e in errors)


def test_optional_field_not_required():
    schema = load_schema(SCHEMAS_DIR / "knowledge-v1.yaml")
    meta = {
        "title": "Test",
        "summary": "A test",
        "repos": ["foo"],
        # tags is optional - not included
        "sources": ["capture-1.md"],
        "created_at": "2026-02-22T20:00:00Z",
        "schema_version": 1,
    }
    errors = validate_frontmatter(meta, schema)
    assert errors == []
