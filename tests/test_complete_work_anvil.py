from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmarks.complete_work.oracles import anvil


class AnvilOracleTests(unittest.TestCase):
    def test_pinned_export_matches_complete_file_map(self) -> None:
        result = anvil.validate_pinned_source()
        self.assertEqual(result["id"], "pinned_source_identity")
        self.assertTrue(result["passed"], result["detail"])

    def test_prepare_target_makes_a_verified_isolated_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            result = anvil.prepare_target(target)
            self.assertEqual(result["source_commit"], anvil.SOURCE_COMMIT)
            self.assertEqual(result["source_file_count"], 638)
            self.assertTrue((target / "package-lock.json").is_file())
            self.assertTrue(anvil.validate_pinned_source(target)["passed"])

    def test_missing_candidate_environment_is_unavailable_with_documented_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = anvil.evaluate(root, work_dir=root / "work")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["episode_id"], "anvil-creation-evidence")
        self.assertEqual(result["status"], "unavailable")
        self.assertIsInstance(result["checks"], list)
        self.assertIsInstance(result["errors"], list)
        self.assertIn("runtime", result)
        self.assertIn("provenance", result)

    def test_cli_writes_json_for_an_unavailable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmarks.complete_work.oracles.anvil",
                    "--repo",
                    str(root),
                    "--work-dir",
                    str(root / "work"),
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["schema_version"], 1)

    def test_fixture_is_valid_node_module(self) -> None:
        result = subprocess.run(
            ["node", "--check", str(anvil.FIXTURE)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
