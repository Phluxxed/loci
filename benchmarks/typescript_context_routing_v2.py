"""Declare qualification of the repaired exploration routing workflow."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_explore_transport import audit_request as audit_tools


VERSION = "typescript-context-routing-v2"
ROOT = Path(__file__).resolve().parents[1]
DECLARATION_ROOT = ROOT / "benchmarks" / "comparisons" / VERSION
POLICY_PATH = DECLARATION_ROOT / "selection-policy.md"
CALL_TARGET_CASES = frozenset({
    "exported_arrow", "default_identifier", "named_function_control", "inline_default_control",
})


def build_prompt(corpus: dict[str, Any], controls: dict[str, Any], case_id: str, arm: str) -> str:
    """Keep the complete original task prompt as an unchanged suffix."""
    if arm not in {"A", "B"}:
        raise ValueError("routing arm must be A or B")
    case = next(case for case in corpus["cases"] if case["id"] == case_id)
    original = controls["agent"]["common_prompt"] + case["prompt"]
    return original if arm == "A" else POLICY_PATH.read_text(encoding="utf-8") + "\n" + original


def audit_request(request: dict[str, Any], prompt: str) -> dict[str, Any]:
    """Both routing conditions use the same repaired exploration schema."""
    audit = audit_tools(request, prompt, "B")
    return {**audit, "routing_version": VERSION, "prompt_sha256": sha256(prompt.encode()).hexdigest()}


def prompt_manifest(corpus: dict[str, Any], controls: dict[str, Any]) -> dict[str, Any]:
    """List all prompt identities and predeclared routing branches, without gold."""
    policy = POLICY_PATH.read_bytes()
    return {
        "version": VERSION,
        "status": "qualification_defined_not_frozen_or_measured",
        "policy_sha256": sha256(policy).hexdigest(),
        "policy_utf8_bytes": len(policy),
        "candidate_prefix_utf8_bytes": len(policy) + 1,
        "tool_arm": {"A": "B", "B": "B"},
        "cases": [
            {
                "case_id": case["id"],
                "initial_route": "call_target" if case["id"] in CALL_TARGET_CASES else "type_dependencies",
                "prompts": {
                    arm: {
                        "sha256": sha256(build_prompt(corpus, controls, case["id"], arm).encode()).hexdigest(),
                        "utf8_bytes": len(build_prompt(corpus, controls, case["id"], arm).encode()),
                    }
                    for arm in ("A", "B")
                },
            }
            for case in corpus["cases"]
        ],
    }
