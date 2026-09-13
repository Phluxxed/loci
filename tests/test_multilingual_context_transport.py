from __future__ import annotations

import pytest

from benchmarks import multilingual_context_transport as transport


def test_transport_anchor_symbol_id_is_derived_from_evaluator_context() -> None:
    case = {
        "anchor": "entry",
        "context": [
            {"id": "entry", "file": "consumer.py", "symbol": {"name": "decode", "kind": "function"}},
        ],
    }
    assert transport._symbol_id(case) == "consumer.py::decode#function"


def test_transport_rejects_anchor_without_concrete_symbol() -> None:
    with pytest.raises(ValueError, match="concrete declaration"):
        transport._symbol_id({"anchor": "entry", "context": [{"id": "entry", "file": "x.py", "symbol": None}]})


def test_offline_provider_config_has_no_auth_requirement() -> None:
    value = transport._offline_config(12345)
    assert value["model_provider"] == "inspection"
    assert value["model_providers.inspection.base_url"] == "http://127.0.0.1:12345/v1"
    assert value["model_providers.inspection.requires_openai_auth"] is False
