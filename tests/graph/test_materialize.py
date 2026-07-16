from __future__ import annotations

import hashlib
import json
from pathlib import Path

from loci.graph.contracts import (
    GraphContribution,
    GraphEdge,
    GraphEvidence,
    GraphNodeRef,
    validate_graph_edges,
)
from loci.graph.go_modules import (
    GoModule,
    GoModuleContext,
    build_go_package_index,
    make_go_package_id,
)
from loci.graph.materialize import load_graph_extensions, materialize_graph
from loci.graph.profiles import GraphProfile, LoadedGraphProfile
from loci.graph.state import LoadedGraphContribution
from loci.parser.imports import extract_imports
from loci.parser.symbols import Symbol, make_file_symbol


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _profile(name: str) -> LoadedGraphProfile:
    path = FIXTURES / "graph_profiles" / name
    return LoadedGraphProfile(
        source=f".loci/graph/profiles/{name}",
        content_hash="f" * 64,
        profile=GraphProfile.from_dict(json.loads(path.read_text())),
    )


def _page(
    file_path: str,
    name: str,
    *,
    frontmatter: dict | None = None,
    lines: dict | None = None,
) -> Symbol:
    symbol_id = f"{file_path}::{name}#section"
    metadata = {
        "markdown": {
            "page_root": True,
            "parent_id": "",
            "root_id": symbol_id,
        },
    }
    if frontmatter:
        metadata["frontmatter"] = frontmatter
    if lines:
        metadata["frontmatter_lines"] = lines
    return Symbol(
        id=symbol_id,
        name=name,
        qualified_name=name,
        kind="section",
        language="markdown",
        file_path=file_path,
        byte_offset=0,
        byte_length=20,
        content_hash="d" * 64,
        metadata=metadata,
        line=1,
        end_line=3,
    )


def test_extension_loader_excludes_all_duplicate_namespace_profiles(tmp_path: Path):
    profile_dir = tmp_path / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    content = (FIXTURES / "graph_profiles" / "generic.json").read_text()
    (profile_dir / "first.json").write_text(content)
    (profile_dir / "second.json").write_text(content)

    loaded = load_graph_extensions(tmp_path)

    assert loaded.profiles == ()
    assert [item.code for item in loaded.diagnostics] == [
        "GRAPH_PROFILE_NAMESPACE_DUPLICATE",
        "GRAPH_PROFILE_NAMESPACE_DUPLICATE",
    ]


def test_extension_loader_keeps_valid_sibling_of_invalid_symlink(tmp_path: Path):
    profile_dir = tmp_path / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    content = (FIXTURES / "graph_profiles" / "generic.json").read_text()
    valid = profile_dir / "valid.json"
    valid.write_text(content)
    (profile_dir / "linked.json").symlink_to(valid)

    loaded = load_graph_extensions(tmp_path)

    assert [item.profile.namespace for item in loaded.profiles] == ["example"]
    assert loaded.diagnostics[0].code == "INVALID_GRAPH_PROFILE"


def test_generic_profile_materializes_overlay_and_forward_edge(tmp_path: Path):
    guide = _page(
        "guide.md",
        "Guide",
        frontmatter={"status": "current", "related": ["other.md"]},
        lines={"status": 2, "related": 3},
    )
    other = _page("other.md", "Other")
    (tmp_path / "guide.md").write_text("---\nstatus: current\nrelated: [other.md]\n---\n# Guide\n")
    (tmp_path / "other.md").write_text("# Other\n")

    state = materialize_graph(
        tmp_path,
        [guide, other],
        {"guide.md": "a" * 64, "other.md": "b" * 64},
        [_profile("generic.json")],
        [],
    )

    assert state.nodes == (GraphNodeRef(
        id=guide.id,
        namespace="example",
        kind="section",
        attributes={"status": "current"},
    ),)
    assert state.edges == (GraphEdge(
        from_id=guide.id,
        to_id=other.id,
        type="related_to",
        directed=True,
        namespace="example",
        resolution="declared",
        evidence=GraphEvidence(file="guide.md", line=3, content_hash="a" * 64),
    ),)
    assert state.diagnostics == ()


def test_llm_wiki_profile_materializes_reverse_mentioned_in_edge(tmp_path: Path):
    overview = _page("concepts/overview.md", "Overview")
    detail = _page(
        "concepts/detail.md",
        "Detail",
        frontmatter={
            "knowledge_state": "current",
            "mentioned_in": ["concepts/overview.md"],
        },
        lines={"knowledge_state": 2, "mentioned_in": 3},
    )
    (tmp_path / "concepts").mkdir()
    (tmp_path / "concepts" / "overview.md").write_text("# Overview\n")
    (tmp_path / "concepts" / "detail.md").write_text("# Detail\n")

    state = materialize_graph(
        tmp_path,
        [overview, detail],
        {"concepts/overview.md": "a" * 64, "concepts/detail.md": "b" * 64},
        [_profile("llm-wiki.json")],
        [],
    )

    assert state.nodes[0].attributes == {"knowledge_state": "current"}
    assert state.edges[0].from_id == overview.id
    assert state.edges[0].to_id == detail.id
    assert state.edges[0].evidence.file == "concepts/detail.md"


def test_ambiguous_page_root_reference_is_diagnostic(tmp_path: Path):
    guide = _page(
        "guide.md",
        "Guide",
        frontmatter={"related": ["other.md"]},
        lines={"related": 2},
    )
    first = _page("other.md", "First")
    second = _page("other.md", "Second")

    state = materialize_graph(
        tmp_path,
        [guide, first, second],
        {"guide.md": "a" * 64, "other.md": "b" * 64},
        [_profile("generic.json")],
        [],
    )

    assert state.edges == ()
    assert state.diagnostics[0].code == "GRAPH_REFERENCE_AMBIGUOUS"


def test_unresolved_page_root_reference_is_diagnostic(tmp_path: Path):
    guide = _page(
        "guide.md",
        "Guide",
        frontmatter={"related": ["missing.md"]},
        lines={"related": 2},
    )

    state = materialize_graph(
        tmp_path,
        [guide],
        {"guide.md": "a" * 64},
        [_profile("generic.json")],
        [],
    )

    assert state.edges == ()
    assert state.diagnostics[0].code == "GRAPH_REFERENCE_UNRESOLVED"


def test_profile_reference_rejects_symlinked_target(tmp_path: Path):
    guide = _page(
        "guide.md",
        "Guide",
        frontmatter={"related": ["other.md"]},
        lines={"related": 2},
    )
    other = _page("other.md", "Other")
    outside = tmp_path.parent / "outside.md"
    outside.write_text("# Outside\n")
    (tmp_path / "other.md").symlink_to(outside)

    state = materialize_graph(
        tmp_path,
        [guide, other],
        {"guide.md": "a" * 64, "other.md": "b" * 64},
        [_profile("generic.json")],
        [],
    )

    assert state.edges == ()
    assert state.diagnostics[0].code == "GRAPH_REFERENCE_UNRESOLVED"


def test_stale_contribution_edge_is_excluded_with_diagnostic(tmp_path: Path):
    guide = _page("guide.md", "Guide")
    other = _page("other.md", "Other")
    contribution = GraphContribution(
        schema_version=1,
        namespace="example",
        nodes=(),
        edges=(GraphEdge(
            from_id=guide.id,
            to_id=other.id,
            type="related_to",
            directed=True,
            namespace="example",
            resolution="declared",
            evidence=GraphEvidence(
                file="guide.md",
                line=1,
                content_hash="0" * 64,
            ),
        ),),
    )

    state = materialize_graph(
        tmp_path,
        [guide, other],
        {"guide.md": "a" * 64, "other.md": "b" * 64},
        [_profile("generic.json")],
        [LoadedGraphContribution(
            source=".loci/graph/contributions/example.json",
            content_hash="c" * 64,
            contribution=contribution,
        )],
    )

    assert state.edges == ()
    assert state.diagnostics[0].code == "GRAPH_EVIDENCE_STALE"


def test_valid_contribution_records_are_active(tmp_path: Path):
    guide = _page("guide.md", "Guide")
    other = _page("other.md", "Other")
    (tmp_path / "guide.md").write_text("# Guide\nEvidence\n")
    (tmp_path / "other.md").write_text("# Other\n")
    payload = json.loads(
        (FIXTURES / "graph_contributions" / "example-valid.json").read_text()
    )
    contribution = GraphContribution.from_dict(payload)

    state = materialize_graph(
        tmp_path,
        [guide, other],
        {"guide.md": "a" * 64, "other.md": "b" * 64},
        [_profile("generic.json")],
        [LoadedGraphContribution(
            source=".loci/graph/contributions/example.json",
            content_hash="c" * 64,
            contribution=contribution,
        )],
    )

    assert state.nodes[0].id == other.id
    assert state.edges[0].from_id == guide.id
    assert state.diagnostics == ()


def test_llm_wiki_contribution_fixture_is_active(tmp_path: Path):
    overview = _page("concepts/overview.md", "Overview")
    detail = _page("concepts/detail.md", "Detail")
    (tmp_path / "concepts").mkdir()
    (tmp_path / "concepts" / "overview.md").write_text("# Overview\n")
    (tmp_path / "concepts" / "detail.md").write_text("# Detail\nEvidence\n")
    payload = json.loads(
        (FIXTURES / "graph_contributions" / "llm-wiki-valid.json").read_text()
    )

    state = materialize_graph(
        tmp_path,
        [overview, detail],
        {"concepts/overview.md": "a" * 64, "concepts/detail.md": "b" * 64},
        [_profile("llm-wiki.json")],
        [LoadedGraphContribution(
            source=".loci/graph/contributions/llm-wiki.json",
            content_hash="c" * 64,
            contribution=GraphContribution.from_dict(payload),
        )],
    )

    assert state.nodes[0].attributes == {"knowledge_state": "current"}
    assert state.edges[0].from_id == overview.id
    assert state.edges[0].to_id == detail.id
    assert state.diagnostics == ()


def test_contribution_missing_endpoint_is_excluded(tmp_path: Path):
    guide = _page("guide.md", "Guide")
    contribution = GraphContribution(
        schema_version=1,
        namespace="example",
        nodes=(GraphNodeRef(
            id="missing.md::Missing#section",
            namespace="example",
            kind="section",
            attributes={"status": "current"},
        ),),
        edges=(),
    )

    state = materialize_graph(
        tmp_path,
        [guide],
        {"guide.md": "a" * 64},
        [_profile("generic.json")],
        [LoadedGraphContribution(
            source=".loci/graph/contributions/example.json",
            content_hash="c" * 64,
            contribution=contribution,
        )],
    )

    assert state.nodes == ()
    assert state.diagnostics[0].code == "GRAPH_ENDPOINT_NOT_FOUND"


def test_contribution_unsupported_edge_policy_is_excluded(tmp_path: Path):
    guide = _page("guide.md", "Guide")
    other = _page("other.md", "Other")
    contribution = GraphContribution(
        schema_version=1,
        namespace="example",
        nodes=(),
        edges=(GraphEdge(
            from_id=guide.id,
            to_id=other.id,
            type="imports",
            directed=True,
            namespace="example",
            resolution="declared",
            evidence=GraphEvidence(file="guide.md", line=1, content_hash="a" * 64),
        ),),
    )

    state = materialize_graph(
        tmp_path,
        [guide, other],
        {"guide.md": "a" * 64, "other.md": "b" * 64},
        [_profile("generic.json")],
        [LoadedGraphContribution(
            source=".loci/graph/contributions/example.json",
            content_hash="c" * 64,
            contribution=contribution,
        )],
    )

    assert state.edges == ()
    assert state.diagnostics[0].code == "GRAPH_EDGE_TYPE_UNSUPPORTED"


def test_contribution_invalid_evidence_line_is_excluded(tmp_path: Path):
    guide = _page("guide.md", "Guide")
    other = _page("other.md", "Other")
    (tmp_path / "guide.md").write_text("# Guide\n")
    contribution = GraphContribution(
        schema_version=1,
        namespace="example",
        nodes=(),
        edges=(GraphEdge(
            from_id=guide.id,
            to_id=other.id,
            type="related_to",
            directed=True,
            namespace="example",
            resolution="declared",
            evidence=GraphEvidence(file="guide.md", line=2, content_hash="a" * 64),
        ),),
    )

    state = materialize_graph(
        tmp_path,
        [guide, other],
        {"guide.md": "a" * 64, "other.md": "b" * 64},
        [_profile("generic.json")],
        [LoadedGraphContribution(
            source=".loci/graph/contributions/example.json",
            content_hash="c" * 64,
            contribution=contribution,
        )],
    )

    assert state.edges == ()
    assert state.diagnostics[0].code == "GRAPH_EVIDENCE_LINE_INVALID"


def test_contribution_attribute_conflict_retains_profile_value(tmp_path: Path):
    guide = _page(
        "guide.md",
        "Guide",
        frontmatter={"status": "current"},
        lines={"status": 2},
    )
    contribution = GraphContribution(
        schema_version=1,
        namespace="example",
        nodes=(GraphNodeRef(
            id=guide.id,
            namespace="example",
            kind="section",
            attributes={"status": "historical"},
        ),),
        edges=(),
    )
    (tmp_path / "guide.md").write_text("# Guide\n")

    state = materialize_graph(
        tmp_path,
        [guide],
        {"guide.md": "a" * 64},
        [_profile("generic.json")],
        [LoadedGraphContribution(
            source=".loci/graph/contributions/example.json",
            content_hash="c" * 64,
            contribution=contribution,
        )],
    )

    assert state.nodes[0].attributes == {"status": "current"}
    assert state.diagnostics[0].code == "GRAPH_NODE_ATTRIBUTE_CONFLICT"


def test_python_import_materialization_is_directed_and_evidenced(tmp_path: Path):
    consumer_path = tmp_path / "consumer.py"
    target_path = tmp_path / "target.py"
    consumer_path.write_text("import target\n", encoding="utf-8")
    target_path.write_text("VALUE = 1\n", encoding="utf-8")
    consumer_hash = hashlib.sha256(consumer_path.read_bytes()).hexdigest()
    target_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
    file_nodes = [
        make_file_symbol(
            "consumer.py",
            language="python",
            content_hash=consumer_hash,
        ),
        make_file_symbol(
            "target.py",
            language="python",
            content_hash=target_hash,
        ),
    ]
    raw_imports = extract_imports(
        consumer_path,
        source_file="consumer.py",
        language="python",
        source_hash=consumer_hash,
    )

    state = materialize_graph(
        tmp_path,
        file_nodes,
        {"consumer.py": consumer_hash, "target.py": target_hash},
        [],
        [],
        raw_imports=raw_imports,
    )

    assert len(state.imports) == 1
    assert state.imports[0].status == "resolved"
    assert state.edges == (GraphEdge(
        from_id=file_nodes[0].id,
        to_id=file_nodes[1].id,
        type="imports",
        directed=True,
        namespace="loci",
        resolution="import-resolved",
        evidence=GraphEvidence(
            file="consumer.py",
            line=1,
            content_hash=consumer_hash,
        ),
    ),)
def test_materialization_retains_duplicate_import_records_and_one_edge(tmp_path: Path):
    source = tmp_path / "consumer.py"
    target = tmp_path / "target.py"
    source.write_text("import target\nimport target\n", encoding="utf-8")
    target.write_text("VALUE = 1\n", encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    target_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    file_nodes = [
        make_file_symbol("consumer.py", language="python", content_hash=source_hash),
        make_file_symbol("target.py", language="python", content_hash=target_hash),
    ]
    raw_imports = extract_imports(
        source,
        source_file="consumer.py",
        language="python",
        source_hash=source_hash,
    )

    state = materialize_graph(
        tmp_path,
        file_nodes,
        {"consumer.py": source_hash, "target.py": target_hash},
        [],
        [],
        raw_imports=list(reversed(raw_imports)),
    )

    assert len(state.imports) == 2
    assert len(state.edges) == 1
    assert state.edges[0].evidence.line == 1


def test_missing_python_import_is_retained_without_an_edge(tmp_path: Path):
    source = tmp_path / "consumer.py"
    source.write_text("import missing\n", encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    file_node = make_file_symbol(
        "consumer.py",
        language="python",
        content_hash=source_hash,
    )
    raw_imports = extract_imports(
        source,
        source_file="consumer.py",
        language="python",
        source_hash=source_hash,
    )

    state = materialize_graph(
        tmp_path,
        [file_node],
        {"consumer.py": source_hash},
        [],
        [],
        raw_imports=raw_imports,
    )

    assert state.edges == ()
    assert state.imports[0].status == "unresolved"
    assert state.imports[0].unresolved_reason == "not_indexed"


def test_materialize_graph_threads_go_package_index_into_import_edges(
    tmp_path: Path,
):
    source = tmp_path / "cmd" / "server" / "main.go"
    target = tmp_path / "internal" / "store" / "store.go"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text(
        'package main\n\nimport "example.com/project/internal/store"\n',
        encoding="utf-8",
    )
    target.write_text("package store\n", encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    target_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    source_node = make_file_symbol(
        "cmd/server/main.go",
        language="go",
        content_hash=source_hash,
    )
    source_node.metadata["loci"]["go_package"] = {"name": "main", "line": 1}
    target_node = make_file_symbol(
        "internal/store/store.go",
        language="go",
        content_hash=target_hash,
    )
    target_node.metadata["loci"]["go_package"] = {"name": "store", "line": 1}
    file_nodes = {
        source_node.file_path: source_node,
        target_node.file_path: target_node,
    }
    package_build = build_go_package_index(
        GoModuleContext(
            modules=(GoModule(
                source="go.mod",
                root=".",
                module_path="example.com/project",
                requirements=(),
                exclusions=(),
                replacements=(),
            ),),
            workspaces=(),
        ),
        file_nodes=file_nodes,
    )
    assert package_build.problems == ()
    raw_imports = extract_imports(
        source,
        source_file=source_node.file_path,
        language="go",
        source_hash=source_hash,
    )

    state = materialize_graph(
        tmp_path,
        [source_node, target_node, *package_build.index.package_nodes],
        {
            source_node.file_path: source_hash,
            target_node.file_path: target_hash,
        },
        [],
        [],
        raw_imports=raw_imports,
        go_packages=package_build.index,
    )

    assert len(state.imports) == 1
    assert state.imports[0].target_kind == "package"
    assert state.imports[0].target_package == "example.com/project/internal/store"
    assert state.edges == (GraphEdge(
        from_id=source_node.id,
        to_id=make_go_package_id(
            "internal/store",
            "example.com/project/internal/store",
        ),
        type="imports",
        directed=True,
        namespace="loci",
        resolution="import-resolved",
        evidence=GraphEvidence(
            file=source_node.file_path,
            line=3,
            content_hash=source_hash,
        ),
    ),)
    validate_graph_edges(
        list(state.edges),
        indexed_nodes={
            symbol.id: symbol.to_dict()
            for symbol in [
                source_node,
                target_node,
                *package_build.index.package_nodes,
            ]
        },
        file_hashes={source_node.file_path: source_hash},
        imports=state.imports,
    )


def test_typescript_imports_preserve_reexports_and_separate_type_edges(
    tmp_path: Path,
):
    source = tmp_path / "index.ts"
    types = tmp_path / "types.ts"
    runtime = tmp_path / "runtime.ts"
    source.write_text(
        'import type {Shape} from "./types";\n'
        'export {run} from "./runtime";\n',
        encoding="utf-8",
    )
    types.write_text("export type Shape = string;\n", encoding="utf-8")
    runtime.write_text("export const run = () => 1;\n", encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    types_hash = hashlib.sha256(types.read_bytes()).hexdigest()
    runtime_hash = hashlib.sha256(runtime.read_bytes()).hexdigest()
    file_nodes = [
        make_file_symbol("index.ts", language="typescript", content_hash=source_hash),
        make_file_symbol("types.ts", language="typescript", content_hash=types_hash),
        make_file_symbol("runtime.ts", language="typescript", content_hash=runtime_hash),
    ]
    raw_imports = extract_imports(
        source,
        source_file="index.ts",
        language="typescript",
        source_hash=source_hash,
    )

    state = materialize_graph(
        tmp_path,
        file_nodes,
        {
            "index.ts": source_hash,
            "types.ts": types_hash,
            "runtime.ts": runtime_hash,
        },
        [],
        [],
        raw_imports=raw_imports,
    )

    assert {
        record.target_file: (record.raw.type_only, record.raw.is_reexport)
        for record in state.imports
    } == {
        "types.ts": (True, False),
        "runtime.ts": (False, True),
    }
    assert {edge.to_id: edge.type for edge in state.edges} == {
        file_nodes[1].id: "imports_type",
        file_nodes[2].id: "imports",
    }
