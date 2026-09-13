"""Acceptance coverage for Go aliases in the frozen multilingual corpus."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci import service
from loci.parser.extractor import parse_file


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks/corpora/multilingual-context-v1"


@contextmanager
def _indexed_go_contracts(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "go_contracts"
    materialize_snapshot(corpus, "go_contracts", repo)
    (repo / "model/grouped.go").write_text(
        """package model

type (
	GroupedAlias = UserID
	GroupedID int64
)

func local() {
	type LocalID int64
}

func (GroupedID) Method() {}
""",
        encoding="utf-8",
    )
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        (repo / "model/tagged.go").write_text(
            "//go:build linux\n\npackage model\n\ntype TaggedID int64\n",
            encoding="utf-8",
        )
        (repo / "model/cgo.go").write_text(
            "package model\n\nimport \"C\"\n\ntype CgoID int64\n",
            encoding="utf-8",
        )
        (repo / "model/platform_linux_amd64.go").write_text(
            "package model\n\ntype PlatformID int64\n",
            encoding="utf-8",
        )
        (repo / "model/plain.go").write_text(
            "package model\n\ntype PlainID int64\n",
            encoding="utf-8",
        )
        yield repo


def test_go_aliases_keep_exact_type_spec_source_and_ids(tmp_path: Path):
    with _indexed_go_contracts(tmp_path) as repo:
        extracted = {
            symbol.qualified_name: symbol
            for path in (
                repo / "app/main.go",
                repo / "model/model.go",
                repo / "model/grouped.go",
                repo / "model/tagged.go",
                repo / "model/cgo.go",
                repo / "model/platform_linux_amd64.go",
                repo / "model/plain.go",
            )
            for symbol in parse_file(path)
        }
        build, alias, defined, grouped_alias, grouped_defined, local_type = service.get_symbols(
            repo,
            [
                "app/main.go::Build#function",
                "model/model.go::AliasID#type",
                "model/model.go::UserID#type",
                "model/grouped.go::GroupedAlias#type",
                "model/grouped.go::GroupedID#type",
                "model/grouped.go::local.LocalID#type",
            ],
        )

    assert (build["id"], build["kind"]) == (
        "app/main.go::Build#function",
        "function",
    )
    assert (alias["id"], alias["kind"], alias["signature"], alias["source"]) == (
        "model/model.go::AliasID#type",
        "type",
        "AliasID = UserID",
        "AliasID = UserID",
    )
    assert (defined["id"], defined["kind"], defined["signature"], defined["source"]) == (
        "model/model.go::UserID#type",
        "type",
        "UserID int64",
        "UserID int64",
    )
    assert (grouped_alias["id"], grouped_alias["signature"], grouped_alias["source"]) == (
        "model/grouped.go::GroupedAlias#type",
        "GroupedAlias = UserID",
        "GroupedAlias = UserID",
    )
    assert (grouped_defined["id"], grouped_defined["signature"], grouped_defined["source"]) == (
        "model/grouped.go::GroupedID#type",
        "GroupedID int64",
        "GroupedID int64",
    )
    assert all(
        extracted[name].metadata == {
            "loci": {
                "go_package_level": True,
                "go_type_configuration": "unconditional",
            }
        }
        for name in ("Build", "AliasID", "UserID", "GroupedAlias", "GroupedID")
    )
    assert (local_type["id"], local_type["kind"]) == (
        "model/grouped.go::local.LocalID#type",
        "type",
    )
    assert extracted["local.LocalID"].metadata == {
        "loci": {
            "go_package_level": False,
            "go_type_configuration": "unconditional",
        }
    }
    assert extracted["Method"].metadata == {
        "loci": {
            "go_package_level": False,
            "go_type_configuration": "unconditional",
        }
    }
    assert extracted["TaggedID"].metadata["loci"]["go_type_configuration"] == "unsupported"
    assert extracted["CgoID"].metadata["loci"]["go_type_configuration"] == "unsupported"
    assert extracted["PlatformID"].metadata["loci"]["go_type_configuration"] == "unsupported"
    assert extracted["PlainID"].metadata == {
        "loci": {
            "go_package_level": True,
            "go_type_configuration": "unconditional",
        }
    }
