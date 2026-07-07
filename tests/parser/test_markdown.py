import pytest
from pathlib import Path
from loci.parser.extractor import parse_file
from loci.parser.symbols import Symbol


@pytest.fixture
def sample_md(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample.md"


# ── Basic extraction ────────────────────────────────────────────────────────

def test_parse_markdown_returns_symbols(sample_md: Path):
    symbols = parse_file(sample_md)
    assert len(symbols) > 0
    assert all(isinstance(s, Symbol) for s in symbols)


def test_parse_markdown_kind_and_language(sample_md: Path):
    symbols = parse_file(sample_md)
    assert {s.kind for s in symbols} == {"section"}
    assert {s.language for s in symbols} == {"markdown"}


def test_parse_markdown_heading_text_is_name(sample_md: Path):
    names = [s.name for s in parse_file(sample_md)]
    assert "Overview" in names
    assert "Goals" in names
    assert "Details" in names
    assert "Architecture" in names


def test_parse_markdown_signature_is_raw_heading_line(sample_md: Path):
    symbols = parse_file(sample_md)
    details = next(s for s in symbols if s.name == "Details")
    assert details.signature == "### Details"


# ── Nesting ─────────────────────────────────────────────────────────────────

def test_parse_markdown_qualified_name_path(sample_md: Path):
    quals = {s.qualified_name for s in parse_file(sample_md)}
    assert "Overview" in quals
    assert "Overview > Goals" in quals
    assert "Overview > Goals > Details" in quals
    assert "Architecture" in quals


# ── Byte-span round-trip ────────────────────────────────────────────────────

def test_parse_markdown_byte_offsets_valid(sample_md: Path):
    source = sample_md.read_bytes()
    for sym in parse_file(sample_md):
        assert sym.byte_offset >= 0
        assert sym.byte_length > 0
        assert sym.byte_offset + sym.byte_length <= len(source)


def test_parse_markdown_unicode_byte_offsets_round_trip(tmp_path: Path):
    p = tmp_path / "unicode.md"
    p.write_text("# Café\n\nBody with π chars.\n", encoding="utf-8")
    source = p.read_bytes()

    symbols = parse_file(p)
    section = next(s for s in symbols if s.name == "Café")
    body = source[section.byte_offset:section.byte_offset + section.byte_length]

    assert section.byte_offset == 0
    assert section.byte_length == len(source)
    assert section.line == 1
    assert body.decode("utf-8") == "# Café\n\nBody with π chars.\n"


def test_parse_markdown_section_body_round_trips(sample_md: Path):
    source = sample_md.read_bytes()
    overview = next(s for s in parse_file(sample_md) if s.qualified_name == "Overview")
    body = source[overview.byte_offset:overview.byte_offset + overview.byte_length].decode()
    # A section spans its heading through the end of its whole subtree, so the
    # Overview body contains its own heading and its nested Goals/Details content,
    # but stops before the next same-level heading (Architecture).
    assert body.startswith("# Overview")
    assert "Goals" in body
    assert "Deep detail body" in body
    assert "# Architecture" not in body


def test_parse_markdown_line_numbers(sample_md: Path):
    overview = next(s for s in parse_file(sample_md) if s.name == "Overview")
    assert overview.line > 0
    assert overview.end_line >= overview.line


# ── Edge cases ──────────────────────────────────────────────────────────────

def test_parse_markdown_skips_frontmatter(sample_md: Path):
    # No symbol should be named after the frontmatter title.
    names = [s.name for s in parse_file(sample_md)]
    assert "Sample Doc" not in names
    assert "title: Sample Doc" not in names


def test_parse_markdown_frontmatter_metadata_on_page_roots(tmp_path: Path):
    p = tmp_path / "governed.md"
    p.write_text(
        "---\n"
        "title: Governed Hybrid Retrieval Pipeline\n"
        "type: ideas\n"
        "category: Retrieval Governance\n"
        "status: Draft\n"
        "source: sources/chatgpt-graph-ai-brief-2026-07-04.md\n"
        "description: Build bounded graph/vector context packs.\n"
        "tags:\n"
        "  - retrieval-governance\n"
        "  - context-packs\n"
        "created: 2026-07-06\n"
        "ignored_nested:\n"
        "  value: not searchable\n"
        "---\n\n"
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Intro paragraph stays the docstring.\n\n"
        "## Details\n\n"
        "Nested body.\n",
        encoding="utf-8",
    )

    symbols = parse_file(p)
    root = next(s for s in symbols if s.name == "Governed Hybrid Retrieval Pipeline")
    details = next(s for s in symbols if s.name == "Details")
    file_bytes = len(p.read_bytes())

    assert root.docstring == "Intro paragraph stays the docstring."
    assert root.summary == "Build bounded graph/vector context packs."
    assert root.metadata["frontmatter"] == {
        "title": "Governed Hybrid Retrieval Pipeline",
        "type": "ideas",
        "category": "Retrieval Governance",
        "status": "Draft",
        "source": "sources/chatgpt-graph-ai-brief-2026-07-04.md",
        "description": "Build bounded graph/vector context packs.",
        "tags": ["retrieval-governance", "context-packs"],
        "created": "2026-07-06",
    }
    assert root.metadata["markdown"] == {
        "page_root": True,
        "synthetic_name": False,
        "heading_level": 1,
        "parent_id": "",
        "root_id": root.id,
        "file_bytes": file_bytes,
        "saved_pct": int((file_bytes - root.byte_length) / file_bytes * 100),
        "span_kind": "page_root",
    }
    assert "retrieval" in root.keywords
    assert "governance" in root.keywords
    assert "context" in root.keywords
    assert "packs" in root.keywords
    assert "ideas" in root.keywords
    assert details.metadata == {
        "markdown": {
            "page_root": False,
            "synthetic_name": False,
            "heading_level": 2,
            "parent_id": root.id,
            "root_id": root.id,
            "file_bytes": file_bytes,
            "saved_pct": int((file_bytes - details.byte_length) / file_bytes * 100),
            "span_kind": "section",
        },
    }


def test_parse_markdown_frontmatter_on_multiple_top_level_roots(tmp_path: Path):
    p = tmp_path / "multi.md"
    p.write_text(
        "---\n"
        "title: Multi Root\n"
        "description: Shared page metadata.\n"
        "tags: [shared-tag]\n"
        "---\n\n"
        "# First\n\n"
        "First body.\n\n"
        "# Second\n\n"
        "Second body.\n",
        encoding="utf-8",
    )

    roots = [s for s in parse_file(p) if s.name in {"First", "Second"}]

    assert len(roots) == 2
    assert all(s.metadata["frontmatter"]["tags"] == ["shared-tag"] for s in roots)
    assert all(s.summary == "Shared page metadata." for s in roots)
    assert all(s.metadata["markdown"]["root_id"] == s.id for s in roots)
    assert all(s.metadata["markdown"]["span_kind"] == "page_root" for s in roots)


def test_parse_markdown_frontmatter_on_no_heading_fallback(tmp_path: Path):
    p = tmp_path / "flat.md"
    p.write_text(
        "---\n"
        "title: Flat Note\n"
        "description: Searchable flat note.\n"
        "tags: flat-tag\n"
        "---\n\n"
        "Just a flat note with no headings at all.\n",
        encoding="utf-8",
    )

    symbols = parse_file(p)

    assert len(symbols) == 1
    assert symbols[0].name == "flat"
    assert symbols[0].summary == "Searchable flat note."
    assert symbols[0].metadata["frontmatter"]["tags"] == ["flat-tag"]
    assert symbols[0].metadata["markdown"] == {
        "page_root": True,
        "synthetic_name": True,
        "heading_level": 0,
        "parent_id": "",
        "root_id": symbols[0].id,
        "file_bytes": len(p.read_bytes()),
        "saved_pct": 0,
        "span_kind": "flat_page",
    }


def test_parse_markdown_invalid_frontmatter_fails_loudly(tmp_path: Path):
    p = tmp_path / "broken.md"
    p.write_text("---\ntags: [unterminated\n---\n\n# Heading\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid markdown frontmatter"):
        parse_file(p)


def test_parse_markdown_duplicate_headings_disambiguated(sample_md: Path):
    symbols = parse_file(sample_md)
    goals = [s for s in symbols if s.qualified_name == "Overview > Goals"]
    overview = next(s for s in symbols if s.qualified_name == "Overview")
    assert len(goals) == 2
    # Duplicate ids must be disambiguated with a ~N suffix.
    assert len({s.id for s in goals}) == 2
    assert all(s.metadata["markdown"]["parent_id"] == overview.id for s in goals)
    assert all(s.metadata["markdown"]["root_id"] == overview.id for s in goals)


def test_parse_markdown_preamble_captured(tmp_path: Path):
    p = tmp_path / "pre.md"
    p.write_text("Some standalone preamble prose.\n\n# Real Heading\n\nbody\n")
    symbols = parse_file(p)
    names = [s.name for s in symbols]
    preamble = next(s for s in symbols if s.name == "(preamble)")
    assert "(preamble)" in names
    assert preamble.metadata["markdown"] == {
        "page_root": False,
        "synthetic_name": True,
        "heading_level": 0,
        "parent_id": "",
        "root_id": preamble.id,
        "file_bytes": len(p.read_bytes()),
        "saved_pct": int((len(p.read_bytes()) - preamble.byte_length) / len(p.read_bytes()) * 100),
        "span_kind": "preamble",
    }


def test_parse_markdown_no_heading_file(tmp_path: Path):
    p = tmp_path / "flat.md"
    p.write_text("Just a flat note with no headings at all.\n")
    symbols = parse_file(p)
    assert len(symbols) == 1
    assert symbols[0].name == "flat"
    assert symbols[0].kind == "section"


def test_parse_markdown_docstring_is_first_paragraph(sample_md: Path):
    overview = next(s for s in parse_file(sample_md) if s.name == "Overview")
    assert overview.docstring == "Intro paragraph under the top heading."


def test_parse_markdown_keywords_prose_tokenised(sample_md: Path):
    arch = next(s for s in parse_file(sample_md) if s.name == "Architecture")
    assert "architecture" in arch.keywords


def test_parse_markdown_extension_alias(tmp_path: Path):
    p = tmp_path / "doc.markdown"
    p.write_text("# Heading\n\nbody\n")
    symbols = parse_file(p)
    assert len(symbols) == 1
    assert symbols[0].name == "Heading"


def test_parse_markdown_parser_errors_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "broken.md"
    p.write_text("# Heading\n\nbody\n")

    import tree_sitter_language_pack

    def fail_get_language(language: str):
        raise RuntimeError(f"cannot load {language}")

    monkeypatch.setattr(tree_sitter_language_pack, "get_language", fail_get_language)

    with pytest.raises(RuntimeError, match="cannot load markdown"):
        parse_file(p)


def test_parse_markdown_content_hash_deterministic(sample_md: Path):
    first = {s.id: s.content_hash for s in parse_file(sample_md)}
    second = {s.id: s.content_hash for s in parse_file(sample_md)}
    assert first == second
    assert all(h for h in first.values())
