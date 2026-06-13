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


def test_parse_markdown_duplicate_headings_disambiguated(sample_md: Path):
    symbols = parse_file(sample_md)
    goals = [s for s in symbols if s.qualified_name == "Overview > Goals"]
    assert len(goals) == 2
    # Duplicate ids must be disambiguated with a ~N suffix.
    assert len({s.id for s in goals}) == 2


def test_parse_markdown_preamble_captured(tmp_path: Path):
    p = tmp_path / "pre.md"
    p.write_text("Some standalone preamble prose.\n\n# Real Heading\n\nbody\n")
    names = [s.name for s in parse_file(p)]
    assert "(preamble)" in names


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


def test_parse_markdown_content_hash_deterministic(sample_md: Path):
    first = {s.id: s.content_hash for s in parse_file(sample_md)}
    second = {s.id: s.content_hash for s in parse_file(sample_md)}
    assert first == second
    assert all(h for h in first.values())
