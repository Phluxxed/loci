"""Execute the installed skill recipe against the catalog failure shape."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="discovery recipe runs in JavaScript")


def _discover(names: list[str]) -> dict:
    skill = (ROOT / "skills/loci/SKILL.md").read_text()
    recipe = skill.split("```javascript\n", 1)[1].split("```", 1)[0]
    script = """
const names = JSON.parse(process.argv[1]);
const ALL_TOOLS = names.map(name => ({
  name,
  get description() { throw new Error("names-only discovery read a description"); }
}));
const stored = new Map();
const store = (key, value) => stored.set(key, value);
const text = value => process.stdout.write(JSON.stringify(value));
""" + recipe
    result = subprocess.run(
        [NODE, "-e", script, json.dumps(names)],
        text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def test_large_unrelated_catalog_cannot_hide_normal_entrypoints():
    names = [f"mcp__other__search_read_{index}" for index in range(2000)]
    names += ["mcp__other__loci_retrieve_diagnostic", "mcp__loci__loci_search"]
    normal = ["mcp__loci__loci_read", "mcp__loci__loci_retrieve"]
    result = _discover(names + normal)
    assert result == {"status": "found", "count": 2, "names": normal}
    assert len(json.dumps(result).encode()) < 256


def test_absent_normal_tools_report_no_match():
    assert _discover(["mcp__loci__loci_search", "mcp__other__read"]) == {
        "status": "no_match", "count": 0, "names": [],
    }


def test_unprefixed_names_and_duplicate_registrations_are_explicit_and_bounded():
    names = ["loci_read", "loci_retrieve"]
    names += [f"mcp__instance_{index}__loci_retrieve" for index in range(20)]
    result = _discover(names)
    assert result["count"] == 22
    assert result["names"] == names[:8]
