"""Frozen exact-source requests and independent read receipts for architecture.py."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


def locator(root: Path, file: str, raw: bytes, **changes) -> str:
    value = {"v": 1, "repo": str(root.resolve()), "file": file,
             "hash": hashlib.sha256(raw).hexdigest(), "start": 0,
             "end": len(raw), "offset": 0}
    value.update(changes)
    return base64.urlsafe_b64encode(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).decode().rstrip("=")


def requests(snapshots: dict[str, str], specifications: list[str], *, negatives: bool = False) -> list[dict]:
    result = []
    for specification in specifications:
        snapshot, separator, file = specification.partition(":")
        if not separator or snapshot not in snapshots or not file or file.startswith("/") or ".." in Path(file).parts:
            raise ValueError(f"invalid --read-file {specification!r}; expected snapshot:relative/path")
        repo = Path(snapshots[snapshot])
        path = repo / file
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(repo.resolve()):
            raise ValueError(f"missing or linked read file: {specification}")
        raw = path.read_bytes()
        raw.decode("utf-8")
        result.append({"case_id": f"read-{len(result) + 1}", "snapshot": snapshot,
                       "file": file, "sha256": hashlib.sha256(raw).hexdigest(),
                       "size": len(raw), "negatives": negatives})
    if not result:
        raise ValueError("exact-source requires at least one --read-file")
    return result


def errors(repo: Path, file: str, raw: bytes) -> list[tuple[str, str]]:
    """Small fixed negative inventory; mutation tests are handled in the worker."""
    unindexed = repo / "not-indexed.txt"
    unindexed_raw = unindexed.read_bytes() if unindexed.is_file() else raw
    items = [
        ("foreign", locator(repo, file, raw, repo="/foreign-repository")),
        ("extent", locator(repo, file, raw, end=len(raw) + 1)),
        ("hash", locator(repo, file, raw, hash="0" * 64)),
        ("unindexed", locator(repo, "not-indexed.txt", unindexed_raw)),
        ("malformed", "not-a-source-reference"),
    ]
    for position in range(1, len(raw)):
        try:
            raw[:position].decode("utf-8")
        except UnicodeDecodeError:
            items.append(("utf8_boundary", locator(repo, file, raw, start=position, offset=position)))
            break
    return items


def check_case(repo: Path, request: dict, receipt: dict) -> dict:
    """Verify all delivered bytes against the frozen source, independent of either index."""
    from loci.mcp_output_models import LociReadOutput

    raw = (repo / request["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != request["sha256"] or len(raw) != request["size"]:
        raise ValueError("frozen exact source differs")
    pages = receipt["pages"]
    if not pages or receipt["repeat"] != pages[0] or receipt["without_refresh"] != pages[0]:
        raise ValueError("repeated or no-refresh first page differs")
    position = 0
    for number, page in enumerate(pages):
        LociReadOutput.model_validate(page)
        source = page["source"]
        start, end = source["start_byte"], source["end_byte"]
        if (source["file"] != request["file"] or source["content_hash"] != request["sha256"]
                or start != position or end <= start or end > len(raw)
                or source["content"].encode() != raw[start:end]
                or source["start_line"] != raw[:start].count(b"\n") + 1
                or source["end_line"] != max(source["start_line"], source["start_line"]
                    + raw[start:end].count(b"\n") - int(raw[start:end].endswith(b"\n")))
                or page["complete"] != (end == len(raw))
                or page["usage"]["evidence_bytes"] != end - start
                or page["usage"]["evidence_bytes"] > 8192):
            raise ValueError(f"incorrect source page {number}")
        envelope = {"content": [], "structuredContent": page, "isError": False}
        actual_size = len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode())
        if actual_size != page["usage"]["output_bytes"] or actual_size > 16384:
            raise ValueError(f"incorrect source output accounting {number}")
        if number + 1 < len(pages) and page["next_source_ref"] is None:
            raise ValueError("missing continuation")
        position = end
    if position != len(raw) or pages[-1]["next_source_ref"] is not None:
        raise ValueError("exact source was not completed")
    expected_codes = {"foreign": "INVALID_SOURCE_REF", "extent": "INVALID_SOURCE_REF",
                      "hash": "SOURCE_STALE", "unindexed": "INVALID_SOURCE_REF",
                      "malformed": "INVALID_SOURCE_REF", "utf8_boundary": "INVALID_SOURCE_REF",
                      "stale": "SOURCE_STALE", "stale_refresh": "SOURCE_STALE",
                      "outside_symlink": "SOURCE_UNAVAILABLE"}
    negatives = receipt["negatives"]
    for name, error in negatives.items():
        if error.get("code") != expected_codes[name] or not isinstance(error.get("message"), str) or not isinstance(error.get("details"), dict):
            raise ValueError(f"negative {name} unexpectedly succeeded or changed code")
    if request.get("negatives"):
        required = {"foreign", "extent", "hash", "unindexed", "malformed",
                    "stale", "stale_refresh", "outside_symlink"}
        if not raw.isascii():
            required.add("utf8_boundary")
        if not required <= negatives.keys():
            raise ValueError("negative request inventory incomplete")
    elif negatives:
        raise ValueError("unrequested negative reads were supplied")
    return {"case_id": request["case_id"], "integrity_ok": True,
            "file": request["file"], "sha256": request["sha256"],
            "bytes": len(raw), "pages": len(pages), "negative_codes": {k: v["code"] for k, v in negatives.items()}}


def comparable(receipt: dict, repo: Path | None = None) -> dict:
    """Remove only root-bound opaque handles from otherwise exact comparisons."""
    def source(page):
        return {**page, "source": {k: v for k, v in page["source"].items() if k != "source_ref"},
                "next_source_ref": bool(page["next_source_ref"])}
    def normalize(value):
        if isinstance(value, str) and repo is not None:
            return value.replace(str(repo), "<isolated-repo>")
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value
    return {"pages": [source(page) for page in receipt["pages"]],
            "repeat": source(receipt["repeat"]),
            "without_refresh": source(receipt["without_refresh"]),
            "negatives": normalize(receipt["negatives"])}


def build_small_suite(destination: Path) -> Path:
    """Create a frozen, small multilingual exact-read input from the pinned TS case."""
    from benchmarks.architecture_cases import load_suite
    from benchmarks.typescript_context_corpus import _snapshot_files

    root = Path(__file__).resolve().parent / "corpora/typescript-context-v1"
    corpus = load_suite(root)
    case = next(case for case in corpus["cases"] if case["id"] == "imported_interface")
    snapshot_id = case["snapshot"]
    files = _snapshot_files(corpus, snapshot_id)
    files.update({
        "unicode.md": ("# Exact source\n" + "🙂\\\"" * 2500 + "\nFinal line\n").encode(),
        "go.mod": b"module example.com/exactread\n\ngo 1.22\n",
        "main.go": b"package exactread\n\nfunc Value() int { return 1 }\n",
        "Cargo.toml": b"[package]\nname = \"exactread\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
        "src/lib.rs": b"pub fn value() -> usize { 1 }\n",
        "package.json": b'{"name":"exactread","type":"module"}\n',
        "jsconfig.json": b'{"compilerOptions":{"baseUrl":".","paths":{"@lib":["dep.js"]}}}\n',
        "main.js": b'import { value } from "@lib";\nexport { value };\n',
        "dep.js": b"export const value = 1;\n",
        "not-indexed.txt": b"present but outside indexed source and resolver controls\n",
    })
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / "fixtures.tar.gz"
    with archive.open("wb") as target, gzip.GzipFile(fileobj=target, mode="wb", mtime=0,
                                                      filename="") as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as tar:
            for file, data in sorted(files.items()):
                info = tarfile.TarInfo(f"{snapshot_id}/{file}")
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
    corpus.pop("_root")
    corpus["cases"] = [case]
    corpus["snapshots"] = {snapshot_id: {**corpus["snapshots"][snapshot_id],
        "archive": archive.name, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": {file: hashlib.sha256(data).hexdigest() for file, data in files.items()},
        "provenance": {"kind": "deterministic_exact_source_fixture",
                       "base_case": "typescript-context-v1/imported_interface"}}}
    raw = json.dumps(corpus, ensure_ascii=False, sort_keys=True, indent=2).encode()
    (destination / "corpus.json").write_bytes(raw)
    (destination / "corpus.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    load_suite(destination)
    return destination
