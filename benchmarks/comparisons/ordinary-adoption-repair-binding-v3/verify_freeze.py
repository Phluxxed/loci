"""Read-only verification of frozen v3 inputs, runtime identity and source copies."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def activation_source_refs(raw):
    packet = raw["result"]["structuredContent"]
    records = []
    for index, item in enumerate(packet.get("items", [])):
        value = item.get("source_ref")
        if isinstance(value, str):
            records.append({"field": f"items[{index}].source_ref", "value": value})
    for index, source in enumerate(packet.get("sources", [])):
        value = source.get("source_ref")
        if isinstance(value, str):
            records.append(
                {
                    "field": f"sources[{index}].source_ref",
                    "file": source.get("file"),
                    "value": value,
                }
            )
    value = packet.get("next_source_ref")
    if isinstance(value, str):
        records.append({"field": "next_source_ref", "value": value})
    return records


freeze = json.loads((HERE / "freeze.json").read_text())
errors = []
for relative, expected in freeze["input_sha256"].items():
    path = REPO / relative
    if not path.is_file() or sha(path) != expected:
        errors.append("frozen input differs: " + relative)
for item in freeze["installed_inputs"]:
    path = Path(item["path"])
    if not path.is_file() or str(path.resolve()) != item["resolved"] or sha(path) != item["sha256"]:
        errors.append("installed input differs: " + str(path))
tree = subprocess.check_output(["git", "rev-parse", "HEAD:src"], cwd=REPO, text=True).strip()
if tree != freeze["product_src_tree"] or subprocess.check_output(["git", "diff", "HEAD", "--", "src"], cwd=REPO):
    errors.append("product source differs")
raw_activation = json.loads((REPO / freeze["activation_evidence"]["raw_function_call"]).read_text())
if activation_source_refs(raw_activation) != freeze["activation_evidence"]["source_reference_handles"]:
    errors.append("activation source-reference handles differ")
expected = json.loads((REPO / "benchmarks/comparisons/ordinary-adoption-v1/cases.json").read_text())["source_files"]
sources = []
for row in json.loads((HERE / "schedule.json").read_text())["rows"]:
    root = Path(row["source_root"]).resolve()
    actual = {
        path.relative_to(root).as_posix(): sha(path)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    unsupported = [str(path) for path in root.rglob("*") if path.is_symlink()]
    passed = actual == expected and not unsupported
    sources.append({"run_id": row["run_id"], "files": len(actual), "exact": passed})
    if not passed:
        errors.append("source identity differs: " + row["source_root"])
result = {
    "freeze_sha256": sha(HERE / "freeze.json"),
    "passed": not errors,
    "input_count": len(freeze["input_sha256"]),
    "sources": sources,
    "errors": errors,
}
print(json.dumps(result))
if errors:
    raise SystemExit(1)
