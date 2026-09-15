#!/usr/bin/env python3
"""Replay the retained named-identity request through the local normal service."""
from __future__ import annotations

import json

from loci.service import retrieve


SOURCE_ROOT = "/tmp/anvil-source-tasks-20260914/t16"
QUERY = "captureCommandResult work context binding accepted type imported public contract"


result = retrieve(SOURCE_ROOT, query=QUERY, ensure_fresh=True)
print(json.dumps(
    {"content": [], "structuredContent": result, "isError": False},
    ensure_ascii=False,
    separators=(",", ":"),
))
