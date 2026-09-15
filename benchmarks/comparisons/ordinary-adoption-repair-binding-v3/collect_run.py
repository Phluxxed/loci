"""Capture a selected v3 binding attempt without changing historical observers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
from benchmarks.ordinary_adoption_delivery_v4 import supplement_delivery
from benchmarks.ordinary_adoption_normal import observe_normal_rollout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def retain_source_ref(
    records: list[dict[str, object]], native_line: int, field: str, value: object
) -> None:
    """Retain an issued handle verbatim; it is an opaque protocol string."""
    if isinstance(value, str):
        records.append({"native_line": native_line, "field": field, "value": value})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    row = next(
        r
        for r in json.loads((ROOT / "schedule.json").read_text())["rows"]
        if r["run_id"] == args.run_id
    )
    assert sha(row["prompt"].encode()) == row["prompt_sha256"]
    records = [json.loads(line) for line in args.rollout.read_text().splitlines()]
    session = records[0]["payload"]
    start = next(
        r
        for r in records
        if r["type"] == "event_msg" and r["payload"].get("type") == "task_started"
    )
    metadata = {
        "run_id": row["run_id"],
        "purpose": "post_change",
        "thread_id": session["id"],
        "turn_id": start["payload"]["turn_id"],
        "target_repo": row["source_root"],
        "requested_model": row["model"],
        "requested_effort": row["effort"],
        "case_id": row["case_id"],
        "condition": row["condition"],
        "repetition": row["repetition"],
        "role": row["role"],
        "prompt_sha256": row["prompt_sha256"],
        "source_canonical_root": str(Path(row["source_root"]).resolve()),
    }
    captured = observe_normal_rollout(args.rollout, metadata)
    observation = captured["observation"]
    interval = observation["retained_interval"]
    raw_lines = args.rollout.read_bytes().splitlines(keepends=True)
    retained = b"".join(raw_lines[interval["start_line"] - 1 : interval["end_line"]])
    assert sha(retained) == interval["sha256"]
    supplement = supplement_delivery(observation)
    source_checks: list[dict[str, object]] = []
    source_errors: list[dict[str, object]] = []
    source_references: list[dict[str, object]] = []
    root = Path(row["source_root"]).resolve()
    for call in observation["mcp_calls"]:
        if call["server"] != "loci" or call["tool"] not in ("loci_retrieve", "loci_read"):
            continue
        packet = call["result"].get("structuredContent", {})
        retain_source_ref(source_references, call["line"], "next_source_ref", packet.get("next_source_ref"))
        for index, item in enumerate(packet.get("items", [])):
            if isinstance(item, dict):
                retain_source_ref(source_references, call["line"], f"items[{index}].source_ref", item.get("source_ref"))
        sources = packet.get("sources", [packet["source"]] if "source" in packet else [])
        for index, source in enumerate(sources):
            try:
                retain_source_ref(source_references, call["line"], f"sources[{index}].source_ref", source.get("source_ref"))
                path = (root / source["file"]).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("source is outside assigned repository")
                data = path.read_bytes()
                if sha(data) != source["content_hash"]:
                    raise ValueError("source hash mismatch")
                if data[source["start_byte"] : source["end_byte"]].decode() != source["content"]:
                    raise ValueError("source span mismatch")
                source_checks.append(
                    {"native_line": call["line"], "source_id": source["id"], "file": source["file"]}
                )
            except (KeyError, TypeError, ValueError, OSError) as error:
                source_errors.append(
                    {"native_line": call["line"], "file": source.get("file"), "error": str(error)}
                )
    output = (args.output_root or (ROOT / "runs")) / args.run_id
    output.mkdir(parents=True, exist_ok=False)
    write(output / "observation.json", captured)
    write(output / "delivery-supplement.json", supplement)
    final = observation["outcome"]["final_answer"]
    if final.get("status") == "present":
        content = final["content"]
        assert all(x.get("type") == "Text" and isinstance(x.get("text"), str) for x in content)
        (output / "finalanswer.md").write_text("".join(x["text"] for x in content))
    write(
        output / "metadata.json",
        {
            "schedule": row,
            "observer_metadata": metadata,
            "native_rollout_path": str(args.rollout),
            "native_interval": interval,
            "condition_validation": observation["native_identity"],
            "source_records_validated": source_checks,
            "source_validation_errors": source_errors,
            "source_references": source_references,
            "source_reference_retention": "Returned source_ref strings are retained verbatim as opaque handles; no decoding or encoding-shape assumption is made.",
            "prompt_capture": "Primary attests exact scheduled spawn text; encrypted child payload may prevent independent plaintext hash.",
            "publication": "Original native interval remains local; normalized observations and provenance are published.",
        },
    )
    usage = observation["provider_usage"]
    print(
        json.dumps(
            {
                "run_id": row["run_id"],
                "outcome": observation["outcome"]["boundary"],
                "duration_ms": observation["outcome"]["duration_ms"],
                "provider_usage": usage,
                "cost": observation["cost"],
                "normal_cost": captured["normal_cost"],
                "delivery": [
                    {"line": x["native_line"], "status": x["supplemental_model_delivery"]["status"]}
                    for x in supplement["calls"]
                ],
                "source_records_validated": len(source_checks),
                "source_validation_errors": source_errors,
                "source_references_retained": len(source_references),
            }
        )
    )


if __name__ == "__main__":
    main()
