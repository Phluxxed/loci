from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.complete_work import controller, prepare


PROJECT = Path(__file__).resolve().parents[1]


class CompleteWorkPreparationTests(unittest.TestCase):
    def _prepare(self, run_id: str, root: Path, **kwargs: object) -> dict:
        return prepare.prepare_run(
            run_id,
            root / "episode",
            serving_root=PROJECT,
            **kwargs,
        )

    def test_anvil_target_and_controller_config_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self._prepare("episode-v1-b1-on", Path(temporary))
            config = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
            marker = json.loads((Path(result["target"]) / ".complete-work-isolation.json").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(Exception, "dependencies"):
                controller.load_run_config(Path(result["config_path"]))
            row = json.loads(prepare.SCHEDULE_PATH.read_text(encoding="utf-8"))["rows"][0]
            stages = [stage["id"] for stage in json.loads(prepare.EPISODES_PATH.read_text(encoding="utf-8"))["episodes"][0]["stages"]]
            instruction = Path(config["instruction_text_path"]).read_text(encoding="utf-8")
            frozen_inputs_present = all(Path(path).is_file() for path in config["frozen_inputs"])
        self.assertEqual(row["episode_id"], "anvil-creation-evidence")
        self.assertEqual(stages, ["orient", "implement", "continue"])
        self.assertEqual(config["dependencies_status"], "unprepared")
        self.assertEqual(config["freeze"]["status"], "not_created")
        self.assertEqual(marker["source"]["commit"], prepare.anvil.SOURCE_COMMIT)
        self.assertNotIn(".complete-work-isolation.json", marker["source_files"])
        self.assertFalse(Path(config["repo"]).is_relative_to(Path(config["output_dir"])))
        self.assertFalse(Path(config["output_dir"]).is_relative_to(Path(config["repo"])))
        self.assertTrue(config["readonly_roots"])
        self.assertFalse(Path(config["output_dir"]).exists())
        self.assertEqual(config["mcp_args"][-1], config["mcp_config_path"])
        self.assertNotIn("--config", config["mcp_args"])
        self.assertTrue(frozen_inputs_present)
        self.assertNotIn("graph_enrichment", instruction)

    def test_loci_export_is_commit_pinned_and_hides_benchmark_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self._prepare("episode-v1-b2-off", Path(temporary))
            target = Path(result["target"])
            marker = json.loads((target / ".complete-work-isolation.json").read_text(encoding="utf-8"))
            config = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
            row = next(row for row in json.loads(prepare.SCHEDULE_PATH.read_text(encoding="utf-8"))["rows"] if row["episode_run_id"] == "episode-v1-b2-off")
            hidden = {name: (target / name).exists() for name in prepare.LOCI_EXCLUDED_TOP_LEVEL}
            git_present = (target / ".git").exists()
            agents_present = (target / "AGENTS.md").is_file()
            source_present = (target / "src").is_dir()
        self.assertEqual(row["episode_id"], "loci-direnv-exclusion")
        self.assertEqual(marker["source"]["commit"], prepare.LOCI_COMMIT)
        self.assertEqual(marker["source"]["excluded_top_level"], sorted(prepare.LOCI_EXCLUDED_TOP_LEVEL))
        self.assertFalse(git_present)
        self.assertTrue(not any(hidden.values()))
        self.assertTrue(agents_present)
        self.assertTrue(source_present)
        self.assertEqual(config["arm"], "off")
        self.assertIsNone(config["oracle"]["python_executable"])

    def test_existing_or_in_repo_destination_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(prepare.PreparationError, "must not already exist"):
                prepare.prepare_run("episode-v1-b1-on", existing, serving_root=PROJECT)
        with self.assertRaisesRegex(prepare.PreparationError, "outside the serving repository"):
            prepare.prepare_run("episode-v1-b1-on", PROJECT / "not-a-target", serving_root=PROJECT)

    def test_prepare_records_preindex_without_a_model_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch("benchmarks.complete_work.prepare._install_dependencies", return_value={"status": "prepared", "kind": "mock"}),
                patch("benchmarks.complete_work.prepare.prepare_target_index", return_value={"indexed": 4}) as indexed,
            ):
                result = self._prepare("episode-v1-b1-off", Path(temporary), preindex=True, install_dependencies=True)
            config = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
        indexed.assert_called_once()
        self.assertEqual(config["preindex"], {"requested": True, "status": "prepared", "result": {"indexed": 4}})
        self.assertEqual(config["dependencies_status"], "prepared")

    def test_install_flag_is_the_only_dependency_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch("benchmarks.complete_work.prepare._install_dependencies", return_value={"status": "prepared", "kind": "mock"}) as install,
                patch("benchmarks.complete_work.prepare.prepare_target_index", return_value={"indexed": 4}),
            ):
                result = self._prepare("episode-v1-b3-on", Path(temporary), install_dependencies=True, preindex=True)
            config = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
            loaded, row, stages = controller.load_run_config(Path(result["config_path"]))
        install.assert_called_once()
        self.assertEqual(config["dependencies_status"], "prepared")
        self.assertEqual(config["dependency_preparation"], {"status": "prepared", "kind": "mock"})
        self.assertEqual(loaded["run_id"], "episode-v1-b3-on")
        self.assertEqual(row["graph_enrichment"], "on")
        self.assertEqual([stage["stage_id"] for stage in stages], ["orient", "implement", "continue"])

    def test_prepared_loci_sets_its_target_venv_as_oracle_python(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch("benchmarks.complete_work.prepare._install_dependencies", return_value={"status": "prepared", "kind": "mock"}):
                result = self._prepare("episode-v1-b2-on", Path(temporary), install_dependencies=True)
            config = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
        self.assertEqual(
            config["oracle"]["python_executable"],
            str(Path(result["target"]) / ".venv" / "bin" / "python"),
        )


if __name__ == "__main__":
    unittest.main()
