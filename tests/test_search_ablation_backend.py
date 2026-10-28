"""Focused evidence-contract checks; the CLI smoke is recorded privately."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("ablation_backend", Path(__file__).parents[1] / "evals/search_ablation/backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class BackendTests(unittest.TestCase):
    def match(self, path, text, number=2):
        return {"type": "match", "data": {"path": {"text": str(path)}, "line_number": number, "lines": {"text": text}}}

    def test_canonical_matches_preserve_text_and_unusual_paths(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "space: and\nnewline.py"
            items = [self.match(path, "  repeated word word\r\n"), {"type": "summary"}, self.match(path, "  repeated word word\n")]
            output = b"\n".join(json.dumps(x).encode() for x in reversed(items))
            self.assertEqual(backend.canonicalize(output, root), [(path.name, 2, "  repeated word word")])

    def test_canonical_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as root:
            output = json.dumps(self.match(Path(root).parent / "outside.py", "x\n")).encode()
            with self.assertRaises(ValueError):
                backend.canonicalize(output, root)

    def test_base64_json_preserves_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as root:
            item = self.match("a.py", "unused")
            item["data"]["lines"] = {"bytes": base64.b64encode(b"\xff\n").decode()}
            result = backend.canonicalize(json.dumps(item).encode(), root)
            self.assertEqual(result[0][2].encode(errors="surrogateescape"), b"\xff")

    def test_literal_and_regex_are_explicit_and_cannot_be_options(self):
        config = {"source_root": "/tmp/root", "index_path": "/tmp/index", "tgrep": "/tmp/tgrep", "rg": "/tmp/rg"}
        case = {"id": "x", "pattern": "--evil", "literal": True, "path": ".", "glob": "*.py"}
        command = backend._case_command(case, "tgrep_index", config)
        self.assertIn("--fixed-strings", command)
        self.assertEqual(command[-3:], ["--", "--evil", str(Path("/tmp/root").resolve())])
        self.assertNotIn("--no-ignore", command)
        with self.assertRaises(ValueError):
            backend._case_command({**case, "path": "../outside"}, "rg", config)

    def test_multi_root_globs_and_ignore_case(self):
        with tempfile.TemporaryDirectory() as root:
            config = {"source_root": root, "index_path": "/tmp/index", "tgrep": "/tmp/tgrep", "rg": "/tmp/rg"}
            case = {"id": "x", "pattern": "hello", "ignore_case": True,
                    "paths": ["a", "b.py"], "globs": ["*.py", "!skip.py"]}
            command = backend._case_command(case, "rg", config)
            self.assertIn("--ignore-case", command)
            self.assertNotIn("--case-sensitive", command)
            self.assertEqual(command[-4:], ["--", "hello", str(Path(root).resolve() / "a"), str(Path(root).resolve() / "b.py")])
            self.assertEqual(command.count("--glob"), 2)

    def test_error_is_not_no_match(self):
        with tempfile.TemporaryDirectory() as root:
            config = {"source_root": root, "private_dir": root, "rg": "/missing/rg"}
            result = backend.run_case({"id": "invalid", "pattern": "["}, "rg", config)
            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["match_count"])
            self.assertFalse(backend.verify_equivalence([result])["equal"])

    def test_routing_uses_observed_cli_output(self):
        self.assertEqual(backend.routing(b"x (via server)", "tgrep_index"), "server_index")
        self.assertEqual(backend.routing(b"Query plan: x\nSearch completed in 2ms", "tgrep_index"), "local_index")
        self.assertEqual(backend.routing(b"Brute-force search completed", "tgrep_scan"), "filesystem_scan")
        self.assertEqual(backend.routing(b"", "tgrep_index"), "unconfirmed")


if __name__ == "__main__":
    unittest.main()
