"""Private, matched CLI search replay. No product configuration is changed.

Use prepare(config), then ``with service(config): run_case(case, mode, config)``.
Modes: rg, tgrep_index (server if service is active, otherwise on-disk index),
and tgrep_scan (explicit current filesystem scan). CLI time excludes JSON parsing
and evidence persistence. Raw source-bearing evidence stays under private_dir.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import urllib.request
import uuid

VERSION = "1.2.5"
ASSET = "https://github.com/microsoft/tgrep/releases/download/v1.2.5/tgrep-v1.2.5-aarch64-apple-darwin.tar.gz"
ASSET_SHA256 = "81245bd7cb06510834f3a1d11e22f118606842ec1b06feae0261dfb0e92af401"
SOURCE_COMMIT = "0ef484c5b3bf9390520cfd3b97c8950a628f45f8"
MODES = ("rg", "tgrep_index", "tgrep_scan")


def default_config(worktree=None):
    root = Path(worktree or Path(__file__).resolve().parents[2])
    private = root / ".scratch/search-ablation/private/backend"
    return {"source_root": str(root / ".scratch/search-ablation/private/source"),
            "private_dir": str(private), "tgrep": str(private / "tgrep"),
            "rg": shutil.which("rg"), "index_path": str(private / "index"),
            "timeout_s": 30}


def _environment():
    return dict(os.environ, RIPGREP_CONFIG_PATH="", GIT_CONFIG_GLOBAL=os.devnull,
                GIT_CONFIG_NOSYSTEM="1", NO_COLOR="1")


def _flags(tgrep=False):
    # No ignore override: --no-ignore on tgrep search forces a scan. Membership
    # is checked against every immutable snapshot file before replay instead.
    flags = ["--hidden", "--no-require-git"]
    if tgrep:
        flags += ["--no-max-filesize"]
    return flags


def _invoke(command, config):
    start = time.perf_counter_ns()
    try:
        result = subprocess.run(command, capture_output=True, env=_environment(),
                                cwd=config["source_root"], timeout=config.get("timeout_s", 30))
        return result.returncode, result.stdout, result.stderr, (time.perf_counter_ns() - start) / 1e6
    except subprocess.TimeoutExpired as exc:
        return None, exc.stdout or b"", (exc.stderr or b"") + b"\nsearch timed out", (time.perf_counter_ns() - start) / 1e6
    except OSError as exc:
        return None, b"", str(exc).encode(), (time.perf_counter_ns() - start) / 1e6


def _save(config, prefix, payload, stdout=b"", stderr=b""):
    directory = Path(config["private_dir"]) / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    stem = directory / f"{prefix}-{uuid.uuid4().hex}"
    stem.with_suffix(".stdout").write_bytes(stdout)
    stem.with_suffix(".stderr").write_bytes(stderr)
    stem.with_suffix(".json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    return str(stem.with_suffix(".json"))


def install(config):
    """Download only the pinned asset; copy the sole regular executable safely."""
    private = Path(config["private_dir"])
    private.mkdir(parents=True, exist_ok=True)
    archive = private / f"tgrep-v{VERSION}.tar.gz"
    if not archive.exists():
        with urllib.request.urlopen(ASSET, timeout=60) as response:
            archive.write_bytes(response.read())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != ASSET_SHA256:
        raise ValueError("pinned tgrep asset checksum mismatch")
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        if any(Path(m.name).is_absolute() or ".." in Path(m.name).parts or m.issym() or m.islnk() for m in members):
            raise ValueError("unsafe tgrep archive member")
        candidates = [m for m in members if m.isfile() and Path(m.name).name == "tgrep"]
        if len(candidates) != 1:
            raise ValueError("archive must contain exactly one regular tgrep executable")
        executable = Path(config["tgrep"])
        executable.write_bytes(bundle.extractfile(candidates[0]).read())
        executable.chmod(0o755)
    code, output, error, _ = _invoke([config["tgrep"], "--version"], config)
    if code != 0 or output.strip() != f"tgrep {VERSION}".encode():
        raise ValueError(f"unexpected tgrep version: {output!r} {error!r}")
    metadata = {"asset": ASSET, "asset_sha256": digest, "version": output.decode().strip(),
                "source_commit": SOURCE_COMMIT, "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()}
    (private / "installation.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def _relative_path(value, root):
    path = Path(os.fsdecode(value))
    if not path.is_absolute():
        path = root / path
    # resolve rejects lexical and symlink escapes, retaining useful file names
    return path.resolve().relative_to(root.resolve()).as_posix()


def verify_membership(config):
    root = Path(config["source_root"]).resolve()
    files = list(root.rglob("*"))
    if any(p.is_symlink() for p in files):
        raise ValueError("snapshot contains a symlink")
    expected = sorted(p.relative_to(root).as_posix() for p in files if p.is_file())
    found = {}
    for mode in ("rg", "tgrep_index"):
        tgrep = mode != "rg"
        command = [config["tgrep"] if tgrep else config["rg"], "--files", "--null", *_flags(tgrep)]
        if tgrep:
            command += ["--index-path", config["index_path"]]
        command += [str(root)]
        code, output, error, elapsed = _invoke(command, config)
        paths = sorted(_relative_path(p, root) for p in output.split(b"\0") if p)
        receipt = {"mode": mode, "returncode": code, "count": len(paths), "elapsed_ms": elapsed,
                   "equal_snapshot": paths == expected}
        receipt["raw_locator"] = _save(config, "membership", {**receipt, "command": command, "paths": paths}, output, error)
        if code != 0 or paths != expected:
            raise ValueError(f"{mode} membership differs from frozen snapshot; see {receipt['raw_locator']}")
        found[mode] = receipt
    return {"snapshot_files": len(expected), "membership_sha256": hashlib.sha256(json.dumps(expected).encode()).hexdigest(), "backends": found}


def prepare(config=None, force=False):
    config = config or default_config()
    installation = install(config)
    command = [config["tgrep"], "index", config["source_root"], "--index-path", config["index_path"], *_flags(True)]
    if force:
        command.append("--force")
    code, output, error, elapsed = _invoke(command, config)
    build = {"returncode": code, "elapsed_ms": elapsed, "command": command,
             "kind": "forced rebuild" if force else "index build or incremental refresh"}
    peak = re.search(rb"peak memory ([0-9.]+) MiB", error)
    if peak:
        build["reported_peak_memory_mib"] = float(peak[1])
    build["raw_locator"] = _save(config, "build", build, output, error)
    if code != 0:
        raise RuntimeError(f"index build failed: {build['raw_locator']}")
    membership = verify_membership(config)
    disk = sum(p.stat().st_size for p in Path(config["index_path"]).rglob("*") if p.is_file())
    return {"installation": installation, "build": build, "membership": membership, "index_bytes": disk}


def _json_bytes(value):
    if "text" in value:
        return value["text"].encode("utf-8", errors="surrogateescape")
    return base64.b64decode(value["bytes"], validate=True)


def canonicalize(output, source_root):
    """Canonical full matching lines; order/submatch multiplicity is immaterial."""
    root = Path(source_root)
    matches = set()
    for line in output.splitlines():
        item = json.loads(line)
        if item["type"] != "match":
            continue
        data = item["data"]
        path = _relative_path(_json_bytes(data["path"]), root)
        number = data["line_number"]
        if not isinstance(number, int) or number < 1:
            raise ValueError("invalid matching line number")
        content = _json_bytes(data["lines"])
        if content.endswith(b"\n"):
            content = content[:-1]
            if content.endswith(b"\r"):
                content = content[:-1]
        matches.add((path, number, content.decode("utf-8", errors="surrogateescape")))
    return sorted(matches)


def _case_command(case, mode, config):
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode}")
    root = Path(config["source_root"]).resolve()
    paths = case.get("paths") or [case.get("path", ".")]
    targets = [(root / path).resolve() for path in paths]
    for target in targets:
        _relative_path(os.fsencode(target), root)
    tgrep = mode != "rg"
    command = [config["tgrep"] if tgrep else config["rg"], "--json", "--color", "never", "--ignore-case" if case.get("ignore_case") else "--case-sensitive", *_flags(tgrep)]
    if tgrep:
        command += ["--index-path", config["index_path"], "--stats"]
        if mode == "tgrep_scan":
            command.append("--no-index")
    if case.get("literal", False):
        command.append("--fixed-strings")
    glob = case.get("globs") or case.get("glob")
    if glob:
        for pattern in ([glob] if isinstance(glob, str) else glob):
            command += ["--glob", pattern]
    return command + ["--", case["pattern"], *(str(target) for target in targets)]


def routing(stderr, mode):
    if mode == "rg":
        return "filesystem_scan"
    if b"(via server)" in stderr:
        return "server_index"
    if b"Brute-force search completed" in stderr:
        return "filesystem_scan"
    if b"Query plan:" in stderr and b"Search completed" in stderr:
        return "local_index"
    return "unconfirmed"


def run_case(case, mode, config=None):
    config = config or default_config()
    command = _case_command(case, mode, config)
    code, output, error, elapsed = _invoke(command, config)
    result = {"case_id": case["id"], "mode": mode, "returncode": code, "elapsed_ms": elapsed,
              "stdout_bytes": len(output), "stderr_bytes": len(error), "routing": routing(error, mode)}
    try:
        matches = canonicalize(output, config["source_root"])
        if code not in (0, 1):
            raise ValueError(f"CLI error (exit {code}); inspect private stderr")
        if (code == 0) != bool(matches):
            raise ValueError("CLI exit code disagrees with parsed matches")
        result.update(status="match" if matches else "no_match", match_count=len(matches),
                      result_sha256=hashlib.sha256(json.dumps(matches, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest())
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        matches = None
        result.update(status="error", error=str(exc), match_count=None, result_sha256=None)
    result["raw_locator"] = _save(config, mode, {**result, "command": command, "matches": matches}, output, error)
    return result


def verify_equivalence(results):
    """Read exact canonical records as well as comparing their compact digests."""
    if not results or any(r["status"] == "error" for r in results):
        return {"equal": False, "reason": "missing result or CLI/parse error"}
    matches = [json.loads(Path(r["raw_locator"]).read_text())["matches"] for r in results]
    return {"equal": all(m == matches[0] for m in matches[1:]),
            "counts": [len(m) for m in matches], "modes": [r["mode"] for r in results]}


@contextmanager
def service(config=None, watch=False):
    """Own exactly this subprocess; never terminate a discovered external daemon."""
    config = config or default_config()
    log_path = Path(config["private_dir"]) / f"server-{uuid.uuid4().hex}.log"
    command = [config["tgrep"], "serve", config["source_root"], "--index-path", config["index_path"], *_flags(True)]
    if not watch:
        command.append("--no-watch")
    else:
        command += ["--poll-interval", "1"]
    start = time.perf_counter_ns()
    with log_path.open("wb") as log:
        proc = subprocess.Popen(command, stdout=log, stderr=log, env=_environment(), cwd=config["source_root"])
        try:
            status = b""
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError(f"owned server exited {proc.returncode}; see {log_path}")
                code, output, _, _ = _invoke([config["tgrep"], "status", config["source_root"], "--index-path", config["index_path"]], config)
                status = output
                if code == 0 and f"PID:        {proc.pid}".encode() in output and b"Indexing:   complete" in output and b"Reconcile:  idle" in output:
                    break
                time.sleep(.02)
            else:
                raise RuntimeError(f"owned server not ready; see {log_path}")
            rss_code, rss_output, _, _ = _invoke(["ps", "-o", "rss=", "-p", str(proc.pid)], config)
            metadata = {"pid": proc.pid, "rss_kib": int(rss_output.strip()) if rss_code == 0 and rss_output.strip().isdigit() else None, "ready_ms": (time.perf_counter_ns() - start) / 1e6,
                        "log_path": str(log_path), "watch": watch, "status": status.decode(errors="replace")}
            metadata["raw_locator"] = _save(config, "service-start", metadata)
            yield metadata
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
            _save(config, "service-stop", {"pid": proc.pid, "returncode": proc.returncode, "stopped": proc.poll() is not None})


def run_diagnostics(config=None):
    """Small synthetic correctness/freshness probes; never edit the real corpus."""
    config = config or default_config()
    directory = Path(config["private_dir"]) / "diagnostic"
    source = directory / "source"
    source.mkdir(parents=True, exist_ok=True)
    target = source / "name: with space.py"
    target.write_text("value = 'old_sentinel_321'\n")
    (source / ".hidden.py").write_text("hidden_sentinel_789\n")
    diagnostic = {**config, "source_root": str(source), "private_dir": str(directory), "index_path": str(directory / "index")}
    command = [config["tgrep"], "index", str(source), "--index-path", diagnostic["index_path"], *_flags(True), "--force"]
    code, output, error, elapsed = _invoke(command, diagnostic)
    build = {"returncode": code, "elapsed_ms": elapsed}
    build["raw_locator"] = _save(diagnostic, "diagnostic-build", {**build, "command": command}, output, error)
    if code != 0:
        raise RuntimeError(f"diagnostic index build failed: {build['raw_locator']}")
    probes = []
    for case in [
        {"id": "diagnostic_nonselective", "pattern": ".", "literal": False},
        {"id": "diagnostic_no_match", "pattern": "absent_sentinel_000", "literal": True},
        {"id": "diagnostic_bad_regex", "pattern": "[", "literal": False},
        {"id": "diagnostic_hidden", "pattern": "hidden_sentinel_789", "literal": True},
    ]:
        results = [run_case(case, mode, diagnostic) for mode in MODES]
        probes.append({"case_id": case["id"], "results": results, "equivalence": verify_equivalence(results)})
    old = {"id": "diagnostic_before_edit", "pattern": "old_sentinel_321", "literal": True}
    new = {"id": "diagnostic_after_edit", "pattern": "new_sentinel_654", "literal": True}
    with service(diagnostic, watch=True) as server:
        before = [run_case(old, mode, diagnostic) for mode in MODES]
        target.write_text("value = 'new_sentinel_654'\n")
        edited_at = time.perf_counter_ns()
        current = [run_case(new, mode, diagnostic) for mode in ("rg", "tgrep_scan")]
        refresh = []
        for _ in range(100):
            indexed = run_case(new, "tgrep_index", diagnostic)
            refresh.append({"after_edit_ms": (time.perf_counter_ns() - edited_at) / 1e6, "result": indexed})
            if verify_equivalence([*current, indexed])["equal"]:
                break
            time.sleep(.05)
        old_after = run_case(old, "tgrep_index", diagnostic)
        freshness = {"server": server, "before": before, "before_equal": verify_equivalence(before),
                     "current": current, "current_equal": verify_equivalence(current), "refresh_observations": refresh,
                     "eventual_equal": verify_equivalence([*current, refresh[-1]["result"]]), "old_after": old_after}
    result = {"fixture": "synthetic diagnostic, excluded from timed real-query cohort", "build": build, "probes": probes, "freshness": freshness}
    (directory / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
