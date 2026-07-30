from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_first_party_guidance_uses_canonical_repository_parameter() -> None:
    skill_paths = [
        ROOT / "skills" / "loci" / "SKILL.md",
        ROOT / ".claude" / "skills" / "loci" / "SKILL.md",
    ]
    for path in skill_paths:
        text = path.read_text()
        assert "loci_index(repo, incremental=true)" in text
        assert "loci_outline(repo)" in text
        assert "loci_index(path" not in text
        assert "loci_outline(path" not in text

    hook = (ROOT / ".claude" / "hooks" / "loci-enforce-read.py").read_text()
    assert "loci_outline repo=" in hook
    assert "loci_file repo=" in hook
    assert "repo='{repo}' path='{repo}'" not in hook

    readme = (ROOT / "README.md").read_text()
    readme_words = " ".join(readme.split())
    assert "canonical repository-root parameter is `repo`" in readme
    assert "`loci-enforce-read.py`" in readme
    assert "answer-equivalent" in readme
    assert "directory searches and shell pipelines fail open" in readme_words

    design = (
        ROOT / "docs" / "design" / "2026-06-23-mcp-native-loci-design.md"
    ).read_text()
    for tool in ("loci_index", "loci_outline", "loci_verify"):
        section = design.split(f"### `{tool}`", 1)[1].split("### `", 1)[0]
        assert '"repo":' in section
        assert '"path": "/absolute/or/relative/repo/path"' not in section
