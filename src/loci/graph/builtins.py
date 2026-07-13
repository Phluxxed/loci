from __future__ import annotations

from collections.abc import Sequence

from loci.graph.contracts import GraphEdge, GraphEvidence
from loci.parser.symbols import Symbol


def extract_markdown_contains_edges(
    symbols: Sequence[Symbol],
) -> list[GraphEdge]:
    """Build exact parent-to-child edges from finalized Markdown hierarchy."""
    edges: dict[tuple[str, str, str, str], GraphEdge] = {}
    for symbol in symbols:
        if symbol.language != "markdown":
            continue
        metadata = symbol.metadata if isinstance(symbol.metadata, dict) else {}
        markdown = metadata.get("markdown")
        if not isinstance(markdown, dict):
            continue
        parent_id = markdown.get("parent_id")
        if not isinstance(parent_id, str) or not parent_id:
            continue

        edge = GraphEdge(
            from_id=parent_id,
            to_id=symbol.id,
            type="contains",
            directed=True,
            namespace="loci",
            resolution="exact",
            evidence=GraphEvidence(
                file=symbol.file_path,
                line=symbol.line,
                content_hash=symbol.content_hash,
            ),
        )
        key = (edge.namespace, edge.type, edge.from_id, edge.to_id)
        edges[key] = edge

    return [edges[key] for key in sorted(edges)]
