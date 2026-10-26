"""Experimental, request-scoped semantic proof over graph-free source inventory.

Only ``semantic_context`` imports parsers or resolvers.  The inherited source
index, lexical retrieval, and ordinary reads remain the R0.4 implementation.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import tempfile
import time
from types import SimpleNamespace
from typing import Any, Iterator

from .graph_free import (
    GraphFreeError, GraphFreeSource, MAX_FILE_BYTES, MAX_OUTPUT_BYTES,
    _account, _candidates, _canonical, _line_number, _preview, _relative,
    _repo, _skipped, _source, _source_bytes,
)


MAX_PARSED_FILES = 48
MAX_SEED_FILES = 4
MAX_REVERSE_FILES = 10
MAX_RELATIONSHIPS = 12
MAX_ITEMS = 12
MAX_EVIDENCE_BYTES = 8192
MAX_SEMANTIC_PAGE_BYTES = 8192
_SUPPORTED = frozenset({"javascript", "typescript", "rust"})
_CONTROL_NAMES = frozenset({"package.json", "pnpm-workspace.yaml", "Cargo.toml"})
_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _cpu() -> tuple[float, float, int]:
    used = resource.getrusage(resource.RUSAGE_SELF)
    return used.ru_utime, used.ru_stime, used.ru_maxrss


@contextmanager
def _phase(work: dict[str, Any], name: str) -> Iterator[None]:
    before = _cpu()
    started = time.perf_counter()
    try:
        yield
    finally:
        after = _cpu()
        work["phases"].append({
            "name": name, "elapsed_s": time.perf_counter() - started,
            "user_cpu_s": after[0] - before[0],
            "system_cpu_s": after[1] - before[1],
            "process_peak_rss": after[2],
        })


def _semantic_ref(root: Path, file: str, digest: str, start: int, end: int,
                  offset: int | None = None) -> str:
    value = {"v": 2, "repo": str(root), "file": file, "hash": digest,
             "start": start, "end": end, "offset": start if offset is None else offset}
    return "s:" + base64.urlsafe_b64encode(_canonical(value)).decode("ascii").rstrip("=")


def _decode_semantic_ref(root: Path, reference: str) -> dict[str, Any]:
    if len(reference) > 16384 or not reference.startswith("s:"):
        raise GraphFreeError("INVALID_SOURCE_REF", "Semantic source reference is invalid")
    try:
        encoded = reference[2:]
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4),
                               altchars=b"-_", validate=True)
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise GraphFreeError("INVALID_SOURCE_REF", "Semantic source reference is invalid") from exc
    if (not isinstance(value, dict)
            or set(value) != {"v", "repo", "file", "hash", "start", "end", "offset"}
            or type(value["v"]) is not int or value["v"] != 2
            or value["repo"] != str(root)
            or not isinstance(value["file"], str) or not _relative(value["file"])
            or not isinstance(value["hash"], str)
            or re.fullmatch(r"[0-9a-f]{64}", value["hash"]) is None
            or any(type(value[key]) is not int for key in ("start", "end", "offset"))
            or not 0 <= value["start"] <= value["offset"] <= value["end"] <= MAX_FILE_BYTES
            or _semantic_ref(root, value["file"], value["hash"],
                             value["start"], value["end"], value["offset"]) != reference):
        raise GraphFreeError("INVALID_SOURCE_REF", "Semantic source reference fields are invalid")
    return value


def _span(root: Path, file: str, digest: str, raw: bytes, start: int,
          end: int, source_id: int) -> dict[str, Any]:
    result = _source(root, file, digest, raw, start, end, source_id)
    result["source_ref"] = _semantic_ref(root, file, digest, start, end)
    return result


def _control_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return name in _CONTROL_NAMES or name.startswith(("tsconfig", "jsconfig")) and name.endswith(".json")


def _tokens(text: str) -> set[str]:
    return {match.group().casefold() for match in _WORD.finditer(text) if len(match.group()) > 2}


def _line_span(raw: bytes, line: int) -> tuple[int, int]:
    lines = raw.splitlines(keepends=True)
    if line < 1 or line > len(lines):
        raise ValueError("support line is outside source")
    start = sum(len(item) for item in lines[:line - 1])
    return start, start + len(lines[line - 1])


def _unique_evidence_bytes(sources: list[dict[str, Any]]) -> int:
    """Count the byte union of delivered source intervals per file and hash."""
    grouped: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for item in sources:
        grouped.setdefault((item["file"], item["content_hash"]), []).append(
            (item["start_byte"], item["end_byte"]))
    total = 0
    for intervals in grouped.values():
        end = 0
        for start, stop in sorted(intervals):
            total += max(0, stop - max(start, end))
            end = max(end, stop)
    return total


class _MemorySourceStore:
    def __init__(self, raw: dict[str, bytes]):
        self.raw = raw

    def get_file_content(self, _repo: Path, file: str) -> dict[str, str] | None:
        value = self.raw.get(file)
        return None if value is None else {"content": value.decode("utf-8")}


class DemandSource(GraphFreeSource):
    """A graph-free source service with a separate, bounded semantic question."""

    def __init__(self, store: Path):
        super().__init__(store)
        self._semantic_cache: dict[tuple[str, str, str | None], tuple[dict, dict]] = {}
        self._observer: dict[str, Any] = {"index": None, "work": {"semantic_calls": 0}}

    def semantic_observer(self) -> dict[str, Any]:
        return deepcopy(self._observer)

    def read(self, repo: str | Path, source_ref: str, **ignored: Any) -> dict[str, Any]:
        if not isinstance(source_ref, str) or not source_ref.startswith("s:"):
            return super().read(repo, source_ref, **ignored)
        root = _repo(repo)
        value = _decode_semantic_ref(root, source_ref)
        file = value["file"]
        inventory = self.inventory(root)
        if inventory["file_hashes"].get(file) != value["hash"]:
            raise GraphFreeError("SOURCE_STALE", "Semantic source differs from inventory")
        if file not in _candidates(root) or _skipped(file):
            raise GraphFreeError("SOURCE_UNAVAILABLE", "Semantic source is no longer eligible")
        raw = _source_bytes(root, file)
        if hashlib.sha256(raw).hexdigest() != value["hash"] or value["end"] > len(raw):
            raise GraphFreeError("SOURCE_STALE", "Semantic source changed")
        try:
            raw.decode("utf-8")
            raw[:value["start"]].decode("utf-8")
            raw[:value["end"]].decode("utf-8")
            raw[:value["offset"]].decode("utf-8")
        except UnicodeError as exc:
            raise GraphFreeError("INVALID_SOURCE_REF", "Semantic extent is not UTF-8 aligned") from exc
        start = value["offset"]
        end = min(value["end"], start + MAX_SEMANTIC_PAGE_BYTES)
        while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
            end -= 1

        def page(stop: int) -> dict[str, Any]:
            complete = stop == value["end"]
            result = {"schema_version": 1, "status": "ok",
                      "source": _span(root, file, value["hash"], raw, start, stop, 1),
                      "complete": complete,
                      "next_source_ref": None if complete else _semantic_ref(
                          root, file, value["hash"], value["start"], value["end"], stop),
                      "usage": {"output_bytes": 0}}
            return _account(result, stop - start)

        packet = page(end)
        while packet["usage"]["output_bytes"] > MAX_OUTPUT_BYTES and end > start:
            end = start + (end - start) // 2
            while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
                end -= 1
            packet = page(end)
        if end == start and start < value["end"]:
            raise GraphFreeError("OUTPUT_BUDGET_EXCEEDED", "Semantic page cannot fit output budget")
        return packet

    def semantic_context(self, repo: str | Path, query: str,
                         *, anchor_file: str | None = None) -> dict[str, Any]:
        root = _repo(repo)
        if not isinstance(query, str) or not query.strip() or len(query) > 1024:
            raise GraphFreeError("INVALID_QUERY", "Query must be nonempty and at most 1024 characters")
        if anchor_file is not None and not _relative(anchor_file):
            raise GraphFreeError("INVALID_QUERY", "Anchor file must be repository-relative")
        query = query.strip()
        work: dict[str, Any] = {"semantic_calls": 1, "cache_hit": False,
                                "phases": [], "discovered_paths": [], "parsed_paths": [],
                                "control_paths": [], "bytes_discovered": 0,
                                "bytes_parsed": 0, "bytes_controls": 0,
                                "resolver_inputs": {}, "omissions": {}}
        with _phase(work, "cachevalidate"):
            inventory_work = self.index_repo(root)
            inventory = self.inventory(root)
            work["inventory"] = inventory_work
            work["inventory_incomplete"] = any(inventory_work["omissions"].values())
            key = (inventory["snapshot"], query, anchor_file)
            cached = self._semantic_cache.get(key)
        if cached is not None:
            packet, old_observer = cached
            with _phase(work, "cache_freshness"):
                second = self.index_repo(root)
                if second["snapshot"] != inventory["snapshot"]:
                    raise GraphFreeError("SOURCE_STALE", "Repository changed during semantic cache validation")
            work["cache_hit"] = True
            work["cache_reused_parsed_paths"] = old_observer["work"]["parsed_paths"]
            work["cache_entries"] = len(self._semantic_cache)
            work["cache_serialized_proxy_bytes"] = sum(
                len(_canonical(packet)) + len(_canonical(observer["index"]))
                for packet, observer in self._semantic_cache.values())
            self._observer = {"index": deepcopy(old_observer["index"]), "work": work}
            return deepcopy(packet)

        from .parser.languages import EXTENSION_MAP
        from .parser.symbols import make_file_symbol
        hashes = inventory["file_hashes"]
        source_files = {file: EXTENSION_MAP.get(PurePosixPath(file).suffix.lower())
                        for file in hashes}
        source_files = {file: lang for file, lang in source_files.items() if lang in _SUPPORTED}
        file_nodes = {file: make_file_symbol(file, language=lang, content_hash=hashes[file])
                      for file, lang in source_files.items()}
        raw: dict[str, bytes] = {}
        stale: set[str] = set()
        query_terms = _tokens(query)
        ranks: list[tuple[int, str]] = []
        with _phase(work, "discovery"):
            for file in sorted(hashes):
                if file not in source_files and not _control_file(file):
                    continue
                try:
                    data = _source_bytes(root, file)
                except GraphFreeError:
                    stale.add(file)
                    continue
                work["discovered_paths"].append(file)
                work["bytes_discovered"] += len(data)
                if hashlib.sha256(data).hexdigest() != hashes[file]:
                    stale.add(file)
                    continue
                raw[file] = data
                if file not in source_files:
                    continue
                content = data.decode("utf-8")
                overlap = query_terms & _tokens(content)
                path_overlap = query_terms & _tokens(file)
                exact = bool(re.search(re.escape(query), content, re.IGNORECASE))
                score = 1000 * int(exact) + 20 * len(overlap) + 5 * len(path_overlap)
                # Prefer the file that declares the requested identifier over
                # files which merely mention it. This is a lexical prefilter;
                # the parser still decides the actual symbol identity.
                identifiers = [word for word in _WORD.findall(query) if len(word) >= 4]
                if any(re.search(r"\b(?:function|const|class|type|interface|struct|fn)\s+"
                                 + re.escape(word) + r"\b", content) for word in identifiers):
                    score += 2000
                if anchor_file == file:
                    score += 2000
                if score:
                    ranks.append((score, file))
        ranks.sort(key=lambda item: (-item[0], item[1]))
        seeds = [file for _, file in ranks[:MAX_SEED_FILES]]
        if anchor_file in raw and anchor_file in source_files and anchor_file not in seeds:
            seeds.insert(0, anchor_file)
            seeds = seeds[:MAX_SEED_FILES]
        work["seeds"] = seeds
        if query in hashes and query not in source_files:
            work["omissions"]["unsupported_language"] = 1
        if anchor_file in hashes and anchor_file not in source_files:
            work["omissions"]["unsupported_language"] = 1
        if stale:
            work["omissions"]["source_stale"] = len(stale)
        if work["inventory_incomplete"]:
            work["omissions"]["inventory_incomplete"] = sum(inventory_work["omissions"].values())
        if len(ranks) > MAX_SEED_FILES:
            work["omissions"]["anchor_limit"] = len(ranks) - MAX_SEED_FILES

        with tempfile.TemporaryDirectory(prefix="loci-demand-") as temporary:
            snapshot = Path(temporary).resolve(strict=True)
            controls = {file for file in raw if _control_file(file)}
            # A config may extend a differently named local JSON file. Copy
            # admitted JSON controls as candidates; the native loader decides.
            controls.update(file for file in raw if file.endswith(".json")
                            and ("config" in PurePosixPath(file).name))
            with _phase(work, "snapshot"):
                for file in sorted(controls):
                    destination = snapshot / file
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(raw[file])
                    work["control_paths"].append(file)
                    work["bytes_controls"] += len(raw[file])
                # Cargo target discovery checks source path existence before
                # the parser decides which module files to inspect. These are
                # byte copies, never parsed by this preparation step.
                work["rust_snapshot_paths"] = []
                work["bytes_rust_snapshot"] = 0
                for file in sorted(raw):
                    if source_files.get(file) != "rust":
                        continue
                    destination = snapshot / file
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(raw[file])
                    work["rust_snapshot_paths"].append(file)
                    work["bytes_rust_snapshot"] += len(raw[file])
            result = self._resolve_slice(root, snapshot, query, query_terms, hashes,
                                         raw, source_files, file_nodes, seeds, work)

        packet, index = result
        with _phase(work, "final_freshness"):
            second = self.index_repo(root)
            if second["snapshot"] != inventory["snapshot"]:
                raise GraphFreeError("SOURCE_STALE", "Repository changed during semantic resolution")
            work["final_inventory"] = second
        self._observer = {"index": index, "work": work}
        # A single entry serves the immediate identical repeat while bounding
        # retained packet and native projection memory across many questions.
        self._semantic_cache = {key: (deepcopy(packet), deepcopy(self._observer))}
        work["cache_entries"] = 1
        work["cache_serialized_proxy_bytes"] = len(_canonical(packet)) + len(_canonical(index))
        self._observer["work"] = work
        return packet

    def _resolve_slice(
        self, root: Path, snapshot: Path, query: str, query_terms: set[str],
        hashes: dict[str, str], raw: dict[str, bytes], source_files: dict[str, str],
        file_nodes: dict[str, Any], seeds: list[str], work: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from .parser.extractor import parse_file
        from .parser.imports import ImportExtractionError, extract_import_batch
        from .parser.type_observations import TypeExtractionError, extract_type_observations
        from .graph.imports import materialize_import_edges, resolve_imports
        from .graph.references import (
            build_reference_resolver_index, materialize_reference_edges,
            resolve_symbol_references,
        )
        from .graph.calls import materialize_call_edges, resolve_calls
        from .graph.type_relations import materialize_type_edges, resolve_type_relations
        from .graph.javascript_modules import (
            build_javascript_resolution_index, load_javascript_module_context,
        )
        from .graph.rust_crates import build_rust_crate_index, load_cargo_context
        from .graph.state import GraphIndexState
        from .exploration import _Source, _rust_controls, _rust_module_declaration_support

        symbols: list[Any] = []
        imports: list[Any] = []
        exports: list[Any] = []
        references: list[Any] = []
        calls: list[Any] = []
        type_observations: list[Any] = []
        parsed: set[str] = set()
        failed: set[str] = set()
        pending = list(seeds)
        work["snapshot_parsed_paths"] = []
        work["bytes_snapshot_parsed"] = 0

        def parse(file: str) -> None:
            if file in parsed or file in failed or file not in source_files or file not in raw:
                return
            if len(parsed) + len(failed) >= MAX_PARSED_FILES:
                work["omissions"]["parse_limit"] = work["omissions"].get("parse_limit", 0) + 1
                return
            destination = snapshot / file
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw[file])
            work["snapshot_parsed_paths"].append(file)
            work["bytes_snapshot_parsed"] += len(raw[file])
            try:
                local = parse_file(destination)
                batch = extract_import_batch(destination, source_file=file,
                                             language=source_files[file], source_hash=hashes[file])
            except ImportExtractionError:
                failed.add(file)
                work["omissions"]["source_unparsed"] = work["omissions"].get("source_unparsed", 0) + 1
                return
            for symbol in local:
                suffix = re.search(r"~\d+$", symbol.id)
                symbol.file_path = file
                symbol.id = f"{file}::{symbol.qualified_name}#{symbol.kind}{suffix.group() if suffix else ''}"
            try:
                type_observations.extend(extract_type_observations(
                    destination, source_file=file, language=source_files[file],
                    source_hash=hashes[file], symbols=local))
                work["bytes_parsed"] += len(raw[file])
            except TypeExtractionError:
                work["omissions"]["type_source_unparsed"] = work["omissions"].get("type_source_unparsed", 0) + 1
            symbols.extend(local)
            imports.extend(batch.imports)
            exports.extend(batch.exports)
            references.extend(batch.references)
            calls.extend(batch.calls)
            parsed.add(file)
            work["parsed_paths"].append(file)
            work["bytes_parsed"] += 2 * len(raw[file])

        with _phase(work, "extraction"):
            for file in pending:
                parse(file)

            # Reverse discovery is a full current-source text prefilter. The
            # parser is applied only to bounded plausible dependents.
            names = {symbol.name for symbol in symbols if
                     symbol.name.casefold() in query_terms or
                     any(term in symbol.name.casefold() for term in query_terms)}
            if not names:
                names = {word for word in _WORD.findall(query) if len(word) >= 4}
            ranked_reverse: list[tuple[int, str]] = []
            for file, data in raw.items():
                if file in parsed or file not in source_files:
                    continue
                text = data.decode("utf-8")
                hits = sum(bool(re.search(r"\b" + re.escape(name) + r"\b", text))
                           for name in names)
                if hits:
                    ranked_reverse.append((hits, file))
            ranked_reverse.sort(key=lambda item: (-item[0], item[1]))
            for _, file in ranked_reverse[:MAX_REVERSE_FILES]:
                parse(file)
            if len(ranked_reverse) > MAX_REVERSE_FILES:
                work["omissions"]["reverse_prefilter_limit"] = len(ranked_reverse) - MAX_REVERSE_FILES
            work["reverse_candidates"] = [file for _, file in ranked_reverse]

        # Controls live in the immutable snapshot and are parsed by the native
        # loaders only for semantic requests. Full admitted source file nodes
        # prevent a missing candidate from manufacturing a unique import.
        with _phase(work, "control_parse"):
            js_controls = [snapshot / file for file in work["control_paths"]
                           if PurePosixPath(file).name in {"package.json", "pnpm-workspace.yaml"}
                           or PurePosixPath(file).name.startswith(("tsconfig", "jsconfig"))]
            cargo_controls = [snapshot / file for file in work["control_paths"]
                              if PurePosixPath(file).name == "Cargo.toml"]
            js_load = load_javascript_module_context(snapshot, js_controls)
            cargo_load = load_cargo_context(snapshot, cargo_controls)
            js_build = build_javascript_resolution_index(js_load.context, file_nodes=file_nodes)
            work["control_problems"] = (
                [problem.code for problem in js_load.problems]
                + [problem.code for problem in cargo_load.problems]
                + [problem.code for problem in js_build.problems]
            )
            if work["control_problems"]:
                work["omissions"]["control_unavailable"] = len(work["control_problems"])

        def parse_rust_modules() -> None:
            for _ in range(32):
                before = len(parsed)
                for observation in tuple(imports):
                    context = observation.rust
                    if context is None or context.kind != "module" or context.inline:
                        continue
                    source = PurePosixPath(observation.source_file)
                    name = observation.specifier.split("::")[-1]
                    paths = []
                    if context.path_override:
                        paths.append((source.parent / context.path_override).as_posix())
                    else:
                        paths.extend(((source.parent / (name + ".rs")).as_posix(),
                                      (source.parent / name / "mod.rs").as_posix(),
                                      (source.parent / source.stem / (name + ".rs")).as_posix()))
                    for file in paths:
                        if file in raw and file in source_files:
                            parse(file)
                if len(parsed) == before:
                    return
            work["omissions"]["rust_module_depth"] = 1

        with _phase(work, "extraction_closure"):
            # The touched Rust packages need their crate roots and declared
            # external module descendants. Configured alternatives remain in
            # the candidate set and in the native resolver's uncertainty.
            touched = {file for file in parsed if source_files[file] == "rust"}
            touched_roots = set()
            for package in cargo_load.context.packages:
                package_prefix = package.root.rstrip("/") + "/"
                if touched and (package.root in {"", "."} or any(file.startswith(package_prefix) for file in touched)):
                    touched_roots.update(target.root_file for target in package.targets)
            for file in sorted(touched_roots):
                parse(file)
            parse_rust_modules()

        with _phase(work, "resolution"):
            all_symbols = [*file_nodes.values(), *symbols]
            all_imports = list(imports)
            rust_build = build_rust_crate_index(
                cargo_load.context, file_nodes=file_nodes, observations=all_imports)
            work["crate_roots"] = {key: crate.target.root_file
                                   for key, crate in rust_build.index.crates_by_id.items()}
            if rust_build.problems:
                work["omissions"]["rust_crate_unavailable"] = len(rust_build.problems)
            import_records = resolve_imports(
                all_imports, file_nodes=file_nodes,
                javascript_modules=js_build.index, rust_crates=rust_build.index)
            # Follow local endpoints used by the selected files. This is a
            # bounded two-hop request slice, not a repository compiler.
            for _ in range(2):
                required = [record.target_file for record in import_records
                            if record.status == "resolved" and record.target_file in raw
                            and record.raw.source_file in parsed and record.target_file not in parsed]
                for record in import_records:
                    if (record.status == "resolved" and record.raw.source_file in parsed
                            and record.target_id in rust_build.index.crates_by_id):
                        crate = rust_build.index.crates_by_id[record.target_id]
                        if crate.target.root_file in raw and crate.target.root_file not in parsed:
                            required.append(crate.target.root_file)
                if not required:
                    break
                with _phase(work, "extraction_import_closure"):
                    for file in sorted(set(required)):
                        parse(file)
                    parse_rust_modules()
                all_symbols = [*file_nodes.values(), *symbols]
                all_imports = list(imports)
                rust_build = build_rust_crate_index(
                    cargo_load.context, file_nodes=file_nodes, observations=all_imports)
                import_records = resolve_imports(
                    all_imports, file_nodes=file_nodes,
                    javascript_modules=js_build.index, rust_crates=rust_build.index)
            remaining = {record.raw.source_file for record in import_records
                         if record.status == "resolved" and record.target_file in raw
                         and record.raw.source_file in parsed and record.target_file not in parsed}
            remaining.update(record.raw.source_file for record in import_records
                             if record.status == "resolved" and record.raw.source_file in parsed
                             and record.target_id in rust_build.index.crates_by_id
                             and rust_build.index.crates_by_id[record.target_id].target.root_file not in parsed)
            if remaining:
                work["omissions"]["import_closure_limit"] = len(remaining)
            incomplete_reexports = {
                record.raw.source_file for record in import_records
                if record.raw.is_reexport and record.target_file in raw
                and record.target_file not in parsed
            }
            if incomplete_reexports:
                work["omissions"]["reexport_closure_incomplete"] = len(incomplete_reexports)
            work["incomplete_reexport_files"] = sorted(incomplete_reexports)
            work["rust_closure_incomplete"] = bool(
                any(source_files.get(file) == "rust" for file in remaining)
                or work["omissions"].get("rust_module_depth")
                or work["omissions"].get("parse_limit") and any(
                    source_files.get(file) == "rust" for file in parsed))
            all_symbols.extend(rust_build.index.crate_nodes)
            reference_index = build_reference_resolver_index(
                all_symbols, import_records, exports, rust_crates=rust_build.index)
            reference_records = resolve_symbol_references(
                references, imports=import_records, index=reference_index)
            call_records = resolve_calls(
                calls, symbols=all_symbols, symbol_references=reference_records,
                file_hashes=hashes)
            type_records = resolve_type_relations(
                type_observations, symbols=all_symbols, imports=import_records,
                exports=exports, file_hashes=hashes,
                input_hashes={**js_load.input_hashes, **cargo_load.input_hashes},
                symbol_references=reference_records)
            import_edges = materialize_import_edges(
                import_records, file_nodes=file_nodes, rust_crates=rust_build.index)
            reference_edges = materialize_reference_edges(reference_records)
            call_edges = materialize_call_edges(call_records)
            type_edges = materialize_type_edges(type_records)
            work["resolver_inputs"] = {
                "all_file_nodes": len(file_nodes), "parsed_symbols": len(symbols),
                "raw_imports": len(all_imports), "raw_references": len(references),
                "raw_calls": len(calls), "resolved_imports": sum(r.status == "resolved" for r in import_records),
                "resolved_references": sum(r.status == "resolved" for r in reference_records),
                "resolved_calls": sum(r.status == "resolved" for r in call_records),
                "raw_type_observations": len(type_observations),
                "resolved_types": sum(r.status == "resolved" for r in type_records),
            }

        input_hashes = {**js_load.input_hashes, **cargo_load.input_hashes}
        state = GraphIndexState.empty()
        from dataclasses import replace
        state = replace(
            state, imports=tuple(import_records), exports=tuple(exports),
            rust_module_observations=tuple(item for item in imports
                                           if item.rust is not None and item.rust.inline),
            symbol_references=tuple(reference_records), calls=tuple(call_records),
            type_relations=tuple(type_records),
            input_hashes=input_hashes,
        )
        node_dicts = {symbol.id: symbol.to_dict() for symbol in all_symbols}
        source = _Source(snapshot, _MemorySourceStore(raw), node_dicts)
        packet = self._pack_semantics(root, query, query_terms, hashes, raw, seeds,
                                      all_symbols, source, state,
                                      import_edges, reference_edges, call_edges, type_edges,
                                      work, _rust_controls, _rust_module_declaration_support)
        # The observer retains the entire computed slice, including edges
        # whose response proof could not fit. Scorers still require delivered
        # packet claims and source; observer membership alone earns nothing.
        state = replace(state, edges=tuple((*import_edges, *reference_edges,
                                           *call_edges, *type_edges)))
        index = {"schema_version": 1, "repo_path": str(root),
                 "file_hashes": dict(hashes),
                 "symbols": [symbol.to_dict() for symbol in all_symbols],
                 "graph": state.to_dict(), "snapshot": packet["snapshot"],
                 "semantic_scope": {
                     "inventory_incomplete": work["inventory_incomplete"],
                     "inventory_omissions": work["inventory"]["omissions"],
                     "rust_closure_incomplete": work["rust_closure_incomplete"],
                     "incomplete_reexport_files": work["incomplete_reexport_files"],
                     "parsed_paths": work["parsed_paths"],
                     "control_paths": work["control_paths"],
                     "source_stale": bool(work["omissions"].get("source_stale")),
                     "parse_limit": bool(work["omissions"].get("parse_limit")),
                     "import_closure_limit": bool(work["omissions"].get("import_closure_limit")),
                 }}
        return packet, index

    def _pack_semantics(
        self, root: Path, query: str, query_terms: set[str], hashes: dict[str, str],
        raw: dict[str, bytes], seeds: list[str], symbols: list[Any], source: Any,
        state: Any, import_edges: list[Any], reference_edges: list[Any],
        call_edges: list[Any], type_edges: list[Any], work: dict[str, Any],
        rust_controls: Any, rust_module_support: Any,
    ) -> dict[str, Any]:
        with _phase(work, "proofpacking"):
            # R0.6 changes only optional focused delivery; default R0.5 policy
            # and budgets remain identical for the retained control.
            focus_id = getattr(self, "_proof_focus_id", None)
            evidence_limit = getattr(self, "_proof_evidence_limit", MAX_EVIDENCE_BYTES)
            output_limit = getattr(self, "_proof_output_limit", MAX_OUTPUT_BYTES)
            proof_first = focus_id is not None
            symbols_by_id = {symbol.id: symbol for symbol in symbols}
            definitions = [symbol for symbol in symbols
                           if symbol.kind not in {"file", "crate", "package"}
                           and symbol.file_path in work["parsed_paths"]
                           and symbol.byte_length > 0]
            definition_scores: dict[str, int] = {}
            for symbol in definitions:
                words = _tokens(symbol.name + " " + symbol.qualified_name + " " + symbol.signature)
                score = 20 * len(query_terms & words)
                if symbol.name.casefold() in query.casefold():
                    score += 100
                if symbol.file_path in seeds:
                    score += 10
                definition_scores[symbol.id] = score
            ranked_definitions = sorted(definitions, key=lambda item: (
                -definition_scores[item.id], item.file_path, item.byte_offset, item.id))
            requested_identifiers = {word.casefold() for word in _WORD.findall(query)}
            exact_named = [symbol for symbol in ranked_definitions
                           if symbol.name.casefold() in requested_identifiers]
            if focus_id is not None:
                exact_named = [symbol for symbol in symbols if symbol.id == focus_id]
                if len(exact_named) != 1:
                    raise GraphFreeError("UNKNOWN_PROOF_ID", "Focused identity is absent from the retained slice")
            anchors = exact_named[:3]
            if len(exact_named) > 1:
                work["omissions"]["ambiguous_anchor"] = len(exact_named)
            if not exact_named:
                for file in seeds:
                    file_node = symbols_by_id.get(f"{file}::__file__#file")
                    if file_node is not None and file_node not in anchors:
                        anchors.append(file_node)
                    if len(anchors) >= 3:
                        break
                if len(anchors) > 1:
                    work["omissions"]["ambiguous_anchor"] = len(anchors)
            anchor_ids = {symbol.id for symbol in anchors}
            packet: dict[str, Any] = {
                "schema_version": 1, "policy": getattr(self, "_proof_packet_policy", "demand-semantic-v1"),
                "snapshot": self.inventory(root)["snapshot"], "status": "empty",
                "scope": {"coverage": "partial" if work["omissions"] else "complete",
                          "exhaustive": False,
                          "matching": "symbol_metadata" if anchors else "source_literal",
                          "source": "indexed_supported_source",
                          "relationships": "known_static_relationships"},
                "selection": {"mode": "inferred", "candidate_count": len(ranked_definitions),
                              "omitted_candidates": max(0, len(ranked_definitions) - 3)},
                "anchors": [{"node_id": symbol.id, "score": definition_scores.get(symbol.id, 0),
                             "matched_terms": sorted(query_terms & _tokens(symbol.name)),
                             "match_scope": ["symbol_metadata"] if symbol.kind != "file" else ["exact_file"]}
                            for symbol in anchors],
                "nodes": [], "items": [], "ownership": [], "relationships": [],
                "sources": [], "omissions": [],
                "limits": {"max_items": MAX_ITEMS, "max_relationships": MAX_RELATIONSHIPS,
                           "max_evidence_bytes": evidence_limit,
                           "max_output_bytes": output_limit,
                           "max_parsed_files": MAX_PARSED_FILES},
                "usage": {"lookup_bytes": work["bytes_discovered"],
                          "lookup_files": len(work["discovered_paths"]),
                          "nodes_examined": len(symbols),
                          "eligible_edges_considered": len(import_edges) + len(reference_edges) + len(call_edges) + len(type_edges),
                          "edges_traversed": 0, "relationships_delivered": 0,
                          "estimated_tokens": 0, "output_bytes": 0,
                          "token_estimate_method": "utf8_bytes_div_4"},
            }
            omitted = dict(work["omissions"])
            uncertainty = getattr(self, "_packet_uncertainty", None)
            if uncertainty is not None:
                packet["uncertainty"] = uncertainty
                for entry in uncertainty["counts"]:
                    if entry["status"] == "unresolved":
                        reason = entry["consumer_reason"]
                        omitted[reason] = omitted.get(reason, 0) + entry["count"]
                if uncertainty["configuration_possible_count"]:
                    omitted["configuration_dependent_relation"] = (
                        omitted.get("configuration_dependent_relation", 0)
                        + uncertainty["configuration_possible_count"])
            if focus_id is not None:
                packet["proof_request"] = {"node_id": focus_id, "scope": "same_computed_slice"}
            source_keys: dict[tuple[str, int, int], int] = {}
            node_ids: set[str] = set()

            def add_node(symbol_id: str) -> None:
                if symbol_id in node_ids:
                    return
                node = symbols_by_id.get(symbol_id)
                if node is None:
                    return
                packet["nodes"].append({"id": node.id, "name": node.name,
                                        "kind": node.kind, "file": node.file_path})
                node_ids.add(symbol_id)

            def add_source(file: str, start: int, end: int) -> int:
                key = (file, start, end)
                if key in source_keys:
                    return source_keys[key]
                if file not in raw or not 0 <= start < end <= len(raw[file]):
                    raise ValueError("proof source is unavailable")
                source_id = len(packet["sources"]) + 1
                packet["sources"].append(_span(root, file, hashes[file], raw[file],
                                               start, end, source_id))
                source_keys[key] = source_id
                return source_id

            def add_item(symbol: Any, role: str, why: str) -> bool:
                if len(packet["items"]) >= MAX_ITEMS:
                    omitted["item_limit"] = omitted.get("item_limit", 0) + 1
                    return False
                if any(item["node_id"] == symbol.id for item in packet["items"]):
                    return True
                file = symbol.file_path
                if file not in raw:
                    omitted["source_unavailable"] = omitted.get("source_unavailable", 0) + 1
                    return False
                start = symbol.byte_offset if symbol.kind != "file" else 0
                end = start + symbol.byte_length if symbol.kind != "file" else len(raw[file])
                if end <= start or end > len(raw[file]):
                    return False
                preview_end = min(end, start + 1024)
                while preview_end > start and preview_end < len(raw[file]) and raw[file][preview_end] & 0xC0 == 0x80:
                    preview_end -= 1
                if preview_end <= start:
                    return False
                current = deepcopy(packet)
                try:
                    sid = add_source(file, start, preview_end)
                    packet["items"].append({
                        "node_id": symbol.id, "role": role,
                        "depth": 0 if role == "anchor" else 1,
                        "why": why, "source_ids": [sid], "complete": preview_end == end,
                        "extent": {"file": file, "content_hash": hashes[file],
                                   "start_byte": start, "end_byte": end},
                        "source_ref": _semantic_ref(root, file, hashes[file], start, end),
                    })
                    add_node(symbol.id)
                    _account(packet, _unique_evidence_bytes(packet["sources"]))
                    if packet["usage"]["output_bytes"] > output_limit - 512:
                        raise ValueError("item exceeds output budget")
                except (UnicodeError, ValueError):
                    packet.clear()
                    packet.update(current)
                    source_keys.clear()
                    source_keys.update({(s["file"], s["start_byte"], s["end_byte"]): s["id"]
                                        for s in packet["sources"]})
                    node_ids.clear()
                    node_ids.update(node["id"] for node in packet["nodes"])
                    omitted["output_budget"] = omitted.get("output_budget", 0) + 1
                    return False
                return True

            for symbol in ([] if proof_first else anchors):
                add_item(symbol, "anchor", "matched question identifier")
            # An exact file query or a weak symbol query still gets source.
            for file in ([] if exact_named or proof_first else seeds[:2]):
                if any(symbol.file_path == file for symbol in anchors):
                    continue
                file_node = symbols_by_id.get(f"{file}::__file__#file")
                if file_node is not None:
                    add_item(file_node, "anchor" if not anchors else "related",
                             "lexical source candidate")

            import_records = state.imports
            reference_records = state.symbol_references
            call_records = state.calls
            type_records = state.type_relations
            edges = (*import_edges, *reference_edges, *call_edges, *type_edges)
            # Fixed two-hop traversal from the selected exact symbol or file
            # anchors. This does not infer that text prefiltering was exhaustive.
            eligible: dict[tuple[Any, ...], tuple[int, str]] = {}
            for direction in ("forward", "reverse"):
                frontier = set(anchor_ids)
                visited = set(anchor_ids)
                for depth in (1, 2):
                    next_frontier: set[str] = set()
                    for edge in edges:
                        key = (edge.type, edge.from_id, edge.to_id, edge.evidence.file,
                               edge.evidence.line, edge.evidence.content_hash)
                        if direction == "forward" and edge.from_id in frontier:
                            eligible.setdefault(key, (depth, direction))
                            next_frontier.add(edge.to_id)
                        if direction == "reverse" and edge.to_id in frontier:
                            eligible.setdefault(key, (depth, direction))
                            next_frontier.add(edge.from_id)
                    frontier = next_frontier - visited
                    visited.update(next_frontier)
            candidates: list[tuple[int, int, int, Any, Any]] = []
            type_priority = {"uses_type": 0, "references_type": 0, "references": 1,
                             "extends": 1, "implements": 1, "calls": 2,
                             "imports_type": 3, "imports": 3}
            for edge in edges:
                key = (edge.type, edge.from_id, edge.to_id, edge.evidence.file,
                       edge.evidence.line, edge.evidence.content_hash)
                if focus_id is not None and focus_id not in {edge.from_id, edge.to_id}:
                    continue
                if key not in eligible:
                    continue
                depth, direction = eligible[key]
                names = " ".join(symbols_by_id[node].name for node in
                                 (edge.from_id, edge.to_id) if node in symbols_by_id)
                score = 20 * len(query_terms & _tokens(names))
                if edge.from_id in anchor_ids or edge.to_id in anchor_ids:
                    score += 100
                records = (import_records if edge.type in {"imports", "imports_type"}
                           else reference_records if edge.type in {"references", "references_type"}
                           else call_records if edge.type == "calls" else type_records)
                for record in records:
                    if (getattr(record, "source_id", getattr(record, "caller_id", None)) == edge.from_id
                            and record.target_id == edge.to_id
                            and record.raw.source_file == edge.evidence.file
                            and record.raw.line == edge.evidence.line
                            and getattr(record, "status", None) == "resolved"):
                        if (edge.resolution == "import-resolved"
                                and (work["inventory_incomplete"] or work["omissions"].get("source_stale"))):
                            omitted["unresolved_relation"] = omitted.get("unresolved_relation", 0) + 1
                            break
                        if (edge.resolution == "import-resolved"
                                and (record.raw.language == "rust" and work["rust_closure_incomplete"]
                                     or record.raw.source_file in work["incomplete_reexport_files"]
                                     or getattr(record, "target_file", None) in work["incomplete_reexport_files"]
                                     or any(support.file in work["incomplete_reexport_files"]
                                            for support in getattr(record, "support", ())))):
                            omitted["unresolved_relation"] = omitted.get("unresolved_relation", 0) + 1
                            break
                        candidates.append((depth, 0 if direction == "forward" else 1,
                                           -score, edge, record))
                        break
            candidates.sort(key=lambda item: (item[1], item[0],
                                              type_priority.get(item[3].type, 2), item[2],
                                              item[3].from_id, item[3].to_id,
                                              item[3].evidence.file, item[3].evidence.line))
            work["eligible_edges"] = len(eligible)
            work["selected_edge_candidates"] = len(candidates)
            # Source first: make outward declarations reachable even when a
            # complete relationship proof is too large for the packet.
            outward_targets = [edge.to_id for depth, direction, _, edge, _ in candidates
                               if direction == 0 and edge.to_id not in anchor_ids
                               and edge.type in {"references", "references_type", "uses_type",
                                                 "extends", "implements"}]
            for target_id in ([] if proof_first else list(dict.fromkeys(outward_targets))[:3]):
                target = symbols_by_id.get(target_id)
                if target is not None and target.byte_length > 0:
                    add_item(target, "related", "two-hop outward source candidate")
            seen_edges: set[tuple[str, str, str]] = set()
            for _, _, _, edge, record in candidates:
                identity = (edge.type, edge.from_id, edge.to_id)
                if identity in seen_edges:
                    continue
                seen_edges.add(identity)
                if len(packet["relationships"]) >= MAX_RELATIONSHIPS:
                    omitted["neighbor_limit"] = omitted.get("neighbor_limit", 0) + 1
                    continue
                current = deepcopy(packet)
                try:
                    spans: list[tuple[str, int, int]] = []
                    start = getattr(record.raw, "start_byte", None)
                    end = getattr(record.raw, "end_byte", None)
                    if type(start) is int and type(end) is int and end > start:
                        spans.append((record.raw.source_file, start, end))
                    else:
                        if record.raw.rust is not None and record.raw.rust.kind == "module":
                            support_kind = "module_declaration"
                        else:
                            support_kind = "reexport" if record.raw.is_reexport else "import_binding"
                        support = SimpleNamespace(kind=support_kind, file=record.raw.source_file,
                                                  line=record.raw.line,
                                                  content_hash=record.raw.source_hash,
                                                  endpoint_id=edge.from_id)
                        item = source.support(support)
                        spans.append((item.file, item.start_byte, item.end_byte))
                    for support in getattr(record, "support", ()):
                        item = source.support(support)
                        spans.append((item.file, item.start_byte, item.end_byte))
                    if edge.type == "calls" and edge.resolution == "import-resolved":
                        joined = [reference for reference in reference_records
                                  if reference.status == "resolved"
                                  and reference.raw.source_file == record.raw.source_file
                                  and reference.raw.source_hash == record.raw.source_hash
                                  and reference.raw.start_byte == record.raw.start_byte
                                  and reference.raw.end_byte <= record.raw.end_byte
                                  and (record.resolution_basis != "imported_reference"
                                       or reference.target_id == record.target_id)]
                        if len(joined) != 1:
                            raise ValueError("imported call has no unique reference proof")
                        for support in joined[0].support:
                            item = source.support(support)
                            spans.append((item.file, item.start_byte, item.end_byte))
                        for file in joined[0].resolution_control_files:
                            if file not in raw or file not in hashes:
                                raise ValueError("call reference control is not admitted")
                            spans.append((file, 0, len(raw[file])))
                        for item in source.rust_configuration_support(joined[0]):
                            spans.append((item.file, item.start_byte, item.end_byte))
                    for support in rust_module_support(record, state):
                        item = source.support(support)
                        spans.append((item.file, item.start_byte, item.end_byte))
                    for control in rust_controls(state, getattr(record, "resolution_control_files", ())):
                        item = source.control(control)
                        spans.append((item.file, item.start_byte, item.end_byte))
                    for control in getattr(record, "resolution_controls", ()):
                        if (control.file not in raw or control.file not in hashes
                                or hashes[control.file] != control.content_hash):
                            raise ValueError("type resolution control is not admitted")
                        spans.append((control.file, 0, len(raw[control.file])))
                    for file in getattr(record, "resolution_control_files", ()):
                        if file not in raw or file not in hashes:
                            raise ValueError("resolution control is not admitted")
                        spans.append((file, 0, len(raw[file])))
                    for item in source.rust_configuration_support(record):
                        spans.append((item.file, item.start_byte, item.end_byte))
                    # Caller and target declarations are part of the emitted
                    # strict proof, even if normal traversal might show sites.
                    for endpoint in (edge.from_id, edge.to_id):
                        symbol = symbols_by_id.get(endpoint)
                        if symbol is not None and symbol.byte_length > 0:
                            item = source.definition(symbol.to_dict())
                            spans.append((item.file, item.start_byte, item.end_byte))
                    spans = list(dict.fromkeys(spans))
                    if any(file not in raw or hashes[file] != hashlib.sha256(raw[file]).hexdigest()
                           or not 0 <= start < end <= len(raw[file])
                           for file, start, end in spans):
                        raise ValueError("stale proof support")
                    source_ids = [add_source(file, start, end) for file, start, end in spans]
                    packet["relationships"].append({
                        "id": len(packet["relationships"]) + 1,
                        "edge": edge.to_dict(),
                        "traversed": "reverse" if edge.to_id in anchor_ids else "forward",
                        "source_ids": source_ids, "proof": "complete",
                        "resolution_configuration": record.resolution_configuration,
                    })
                    add_node(edge.from_id)
                    add_node(edge.to_id)
                    evidence_bytes = _unique_evidence_bytes(packet["sources"])
                    _account(packet, evidence_bytes)
                    if evidence_bytes > evidence_limit or packet["usage"]["output_bytes"] > output_limit - 512:
                        standalone = deepcopy(packet)
                        standalone["relationships"] = [packet["relationships"][-1]]
                        standalone["sources"] = [s for s in packet["sources"] if s["id"] in source_ids]
                        standalone["nodes"] = [n for n in packet["nodes"] if n["id"] in {edge.from_id, edge.to_id}]
                        standalone["anchors"] = [a for a in packet["anchors"] if a["node_id"] in {edge.from_id, edge.to_id}]
                        standalone["items"] = []
                        standalone["usage"]["relationships_delivered"] = 1
                        standalone["usage"]["edges_traversed"] = 1
                        _account(standalone, _unique_evidence_bytes(standalone["sources"]))
                        work.setdefault("budget_rejections", []).append({
                            "edge": edge.to_dict(), "evidence_bytes": evidence_bytes,
                            "output_bytes": packet["usage"]["output_bytes"],
                            "evidence_limit": evidence_limit, "output_limit": output_limit - 512,
                            "standalone_evidence_bytes": standalone["usage"]["evidence_bytes"],
                            "standalone_output_bytes": standalone["usage"]["output_bytes"],
                        })
                        raise ValueError("proof exceeds packet budget")
                    for endpoint in (edge.from_id, edge.to_id):
                        symbol = symbols_by_id.get(endpoint)
                        if symbol is not None and symbol.byte_length > 0:
                            add_item(symbol, "related", "proved relationship endpoint")
                except (KeyError, UnicodeError, ValueError) as exc:
                    packet.clear()
                    packet.update(current)
                    source_keys.clear()
                    source_keys.update({(s["file"], s["start_byte"], s["end_byte"]): s["id"]
                                        for s in packet["sources"]})
                    node_ids.clear()
                    node_ids.update(node["id"] for node in packet["nodes"])
                    omitted["proof_unavailable"] = omitted.get("proof_unavailable", 0) + 1
                    work.setdefault("proof_failures", []).append({
                        "edge": edge.to_dict(), "reason": str(exc)[:200],
                    })
                    continue

            # A relation may exceed the strict packet proof budget. Its known
            # target remains useful source context, with no asserted edge.
            for family in (() if proof_first else (reference_records, type_records, call_records)):
                targets = [record.target_id for record in family
                           if getattr(record, "status", None) == "resolved"
                           and getattr(record, "source_id", getattr(record, "caller_id", None)) in anchor_ids
                           and record.target_id in symbols_by_id]
                for target_id in list(dict.fromkeys(targets))[:3]:
                    target = symbols_by_id[target_id]
                    if target.byte_length > 0:
                        add_item(target, "related", "resolved outward source candidate")

            if not packet["items"]:
                omitted["no_anchor"] = 1
            if any(not item["complete"] for item in packet["items"]):
                omitted["source_preview"] = sum(not item["complete"] for item in packet["items"])
            packet["omissions"] = [{"reason": reason, "count": count}
                                   for reason, count in sorted(omitted.items()) if count]
            packet["scope"]["coverage"] = "partial" if omitted else "complete"
            packet["status"] = ("empty" if not packet["items"] and not packet["relationships"]
                                else "partial" if omitted else "ok")
            packet["usage"]["relationships_delivered"] = len(packet["relationships"])
            packet["usage"]["edges_traversed"] = len(packet["relationships"])
            _account(packet, _unique_evidence_bytes(packet["sources"]))
            work["emitted_relationships"] = len(packet["relationships"])
            work["emitted_items"] = len(packet["items"])
            work["omissions"] = omitted
            return packet
