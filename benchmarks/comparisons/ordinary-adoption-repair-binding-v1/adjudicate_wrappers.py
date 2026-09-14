"""Retain exact nested JSON evidence separately from the frozen v3 readout."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
from benchmarks.ordinary_adoption_delivery_v3 import (
    _json_equal, _reject_constant, _text_blocks, _unique_object,
)

observation = json.loads((ROOT / 'runs/binding-repair-01/observation.json').read_text())['observation']
decoder = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_reject_constant)
matches = []
for output_line, wrapper_key in [(37, 'loci'), (45, 'packet')]:
    outer = next(x for x in observation['outer_code_mode'] if x['output_line'] == output_line)
    prefix = '{"' + wrapper_key + '":'
    for block_index, block in enumerate(_text_blocks(outer['output'])):
        position = block.find(prefix)
        if position < 0:
            continue
        start = position + len(prefix)
        value, end = decoder.raw_decode(block, start)
        hits = [c for c in observation['mcp_calls'] if _json_equal(value, c['result'])]
        assert len(hits) == 1
        emitted = block[start:end].encode()
        matches.append({
            'native_line': hits[0]['line'], 'native_item_id': hits[0]['item_id'],
            'output_ref': f"outer:{outer['call_id']}:line:{output_line}:block:{block_index}",
            'wrapper_key': wrapper_key, 'start_byte': len(block[:start].encode()),
            'end_byte': len(block[:end].encode()), 'emitted_value_sha256': hashlib.sha256(emitted).hexdigest(),
            'complete_native_result_json_equal': True,
            'outer_has_truncation_marker': 'tokens truncated' in block,
            'scope': 'Full nested object strictly parsed and equal in every native result field; not fragment or prefix equality.',
        })
assert len(matches) == 2
result = {
    'kind': 'post_outcome_manual_nested_json_adjudication',
    'frozen_observer_outputs_unchanged': True,
    'limitation': 'Frozen delivery-v3 recognizes whole lines/blocks but omits nested wrapper values. This adjudication preserves separate actual-output evidence; it does not rewrite the frozen score or adapter.',
    'matches': matches,
}
(ROOT / 'nested-wrapper-delivery-adjudication.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
