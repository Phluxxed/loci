"""Apply the main Steward's reviewed task-structure correction."""
import hashlib
import json
from pathlib import Path
import re

import yaml
from llm_wiki_core.temporal_persistence import build_temporal_claim_revision, parse_temporal_claim_revisions

root = Path('/Users/brummerv/.anvil-brain/codex')
data = json.loads(Path(__file__).with_name('decision.json').read_text())
assert data['steward_decision'] == 'adopt'
source = data['proposal']['source']['source_ref']
assert not (root / source).exists()
assert hashlib.sha256(data['source'].encode()).hexdigest() == data['proposal']['source']['content_hash']
changes = {}
for candidate in data['proposal']['candidates']:
    name = candidate['subject']['page']
    path = root / name
    prefix, front, body = path.read_text().split('---', 2)
    metadata = yaml.safe_load(front)
    old = parse_temporal_claim_revisions(metadata)
    prior = next((r for r in reversed(old) if r.predicate == candidate['predicate']), None)
    revision = build_temporal_claim_revision(
        subject=candidate['subject'], predicate=candidate['predicate'],
        object_ref=candidate['object'], world_validity=candidate['proposed_world_validity'],
        recorded_at=data['recorded_at'], candidate_ids=[candidate['candidate_id']],
        observation_ids=candidate['supporting_observation_ids'], steward_evidence_refs=[source],
        decision='supersede' if prior else 'accept',
        supersedes_revision_ids=[prior.revision_id] if prior else [],
    ).to_dict()
    parse_temporal_claim_revisions(metadata['temporal_claim_revisions'] + [revision])
    block = re.search(r'^temporal_claim_revisions:\n.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)', front, re.M | re.S)
    assert block
    replacement = block.group().rstrip() + '\n' + yaml.safe_dump([revision], sort_keys=False, allow_unicode=True)
    updated = front[:block.start()] + replacement + front[block.end():]
    indent = re.search(r'\nevidence:\n( *)-', front).group(1)
    updated = updated.replace('evidence:\n', 'evidence:\n' + indent + '- ' + source + '\n', 1)
    updated = re.sub(r'^timestamp:.*$', 'timestamp: ' + data['recorded_at'], updated, flags=re.M)
    if name in data['page_edits']:
        edit = data['page_edits'][name]
        start = body.index(edit['start'])
        end = body.index(edit['end'], start)
        body = body[:start] + edit['new'] + body[end:]
    else:
        anchor = 'Objective graph.\n'
        assert body.count(anchor) == 1
        rule = ('\nWhen an existing Manifest Task expands into successive repairs, tests or\n'
                'experiments, retain its identity as a parent and create distinct child Tasks\n'
                'before executing the additional work. Each completed round keeps its own\n'
                'outcome, evidence and completion state. Negative completed investigations do\n'
                'not satisfy product acceptance. Report the actual next child card instead of\n'
                'repeatedly appending work to the same leaf. See the\n'
                '[15 September correction](./' + source + ').\n')
        body = body.replace(anchor, anchor + rule, 1)
    final = prefix + '---' + updated + '---' + body
    parsed_metadata = yaml.safe_load(final.split('---', 2)[1])
    parsed = parse_temporal_claim_revisions(parsed_metadata)
    assert len(parsed) == len(old) + 1
    assert [r.to_dict() for r in parsed[:-1]] == [r.to_dict() for r in old]
    assert parsed_metadata['evidence'] == [source] + metadata['evidence']
    for key, value in metadata.items():
        if key not in {'evidence', 'timestamp', 'temporal_claim_revisions'}:
            assert parsed_metadata[key] == value, (name, key)
    changes[path] = final
    print(name, len(old), '->', len(parsed), revision['revision_id'])
index = root / 'index.md'
updated_index, count = re.subn(r'^\* \[Loci\]\(\./projects/loci.md\).*$', data['index_line'], index.read_text(), flags=re.M)
assert count == 1
(root / source).write_text(data['source'])
for path, content in changes.items():
    path.write_text(content)
index.write_text(updated_index)
with (root / 'log.md').open('a') as stream:
    stream.write(data['log_entry'])
