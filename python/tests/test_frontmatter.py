import pytest

from nova.lib.frontmatter import read_frontmatter, write_frontmatter


def test_read_frontmatter(tmp_path):
    md = tmp_path / "test.md"
    md.write_text(
        "---\ntitle: Test\nsummary: A test file\nrepos: [foo]\n---\nBody content here.\n"
    )
    meta, content = read_frontmatter(md)
    assert meta["title"] == "Test"
    assert meta["summary"] == "A test file"
    assert meta["repos"] == ["foo"]
    assert "Body content" in content


def test_write_frontmatter(tmp_path):
    path = tmp_path / "out.md"
    write_frontmatter(path, {"title": "Test", "repos": ["bar"]}, "Body text here.")
    meta, content = read_frontmatter(path)
    assert meta["title"] == "Test"
    assert "Body text" in content


def test_roundtrip_preserves_types(tmp_path):
    path = tmp_path / "types.md"
    write_frontmatter(path, {"count": 42, "tags": ["a", "b"], "flag": True}, "Content.")
    meta, _ = read_frontmatter(path)
    assert meta["count"] == 42
    assert meta["tags"] == ["a", "b"]
    assert meta["flag"] is True


def test_empty_body(tmp_path):
    path = tmp_path / "empty.md"
    write_frontmatter(path, {"title": "Empty"}, "")
    meta, content = read_frontmatter(path)
    assert meta["title"] == "Empty"
    assert content.strip() == ""


def test_body_with_dashes(tmp_path):
    """Body content containing --- should not confuse the parser."""
    path = tmp_path / "dashes.md"
    write_frontmatter(
        path, {"title": "Tricky"}, "Some text\n---\nMore text after dashes."
    )
    meta, content = read_frontmatter(path)
    assert meta["title"] == "Tricky"
    assert "More text after dashes" in content


def test_no_frontmatter_raises(tmp_path):
    """File without frontmatter delimiter should raise ValueError."""
    path = tmp_path / "plain.md"
    path.write_text("Just plain text, no frontmatter.")
    with pytest.raises(ValueError, match="does not start with"):
        read_frontmatter(path)


def test_no_closing_delimiter_raises(tmp_path):
    """File with opening --- but no closing --- should raise ValueError."""
    path = tmp_path / "broken.md"
    path.write_text("---\ntitle: Broken\nNo closing delimiter here.")
    with pytest.raises(ValueError, match="No closing"):
        read_frontmatter(path)
