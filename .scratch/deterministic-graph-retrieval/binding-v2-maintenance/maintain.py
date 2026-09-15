"""Apply the main Steward's reviewed, bounded v2 result revision."""
import hashlib
import json
from pathlib import Path
import re

import yaml
from llm_wiki_core.temporal_persistence import (
    build_temporal_claim_revision,
    parse_temporal_claim_revisions,
)

ROOT = Path('/Users/brummerv/.anvil-brain/codex')
data = json.loads(Path(__file__).with_name('decision.json').read_text())
assert data['steward_decision'] == 'adopt'
source = data['proposal']['source']['source_ref']
assert not (ROOT / source).exists()
assert hashlib.sha256(data['source'].encode()).hexdigest() == data['proposal']['source']['content_hash']
changes = {}
for candidate in data['proposal']['candidates']:
    name = candidate['subject']['page']
    edit = data['page_edits'][name]
    path = ROOT / name
    prefix, front, body = path.read_text().split('---', 2)
    metadata = yaml.safe_load(front)
    old = parse_temporal_claim_revisions(metadata)
    prior = next(r for r in reversed(old) if r.predicate == candidate['predicate'])
    revision = build_temporal_claim_revision(
        subject=candidate['subject'], predicate=candidate['predicate'],
        object_ref=candidate['object'], world_validity=candidate['proposed_world_validity'],
        recorded_at=data['recorded_at'], candidate_ids=[candidate['candidate_id']],
        observation_ids=candidate['supporting_observation_ids'],
        steward_evidence_refs=[source], decision='supersede',
        supersedes_revision_ids=[prior.revision_id],
    ).to_dict()
    parse_temporal_claim_revisions(metadata['temporal_claim_revisions'] + [revision])
    assert list(metadata)[-1] == 'temporal_claim_revisions'
    updated = front.rstrip() + '\n' + yaml.safe_dump([revision], sort_keys=False, allow_unicode=True)
    indent = re.search(r'\nevidence:\n( *)-', front).group(1)
    updated = updated.replace('evidence:\n', 'evidence:\n' + indent + '- ' + source + '\n', 1)
    updated = re.sub(r'^timestamp:.*$', 'timestamp: ' + data['recorded_at'], updated, flags=re.M)
    updated = re.sub(r'^description:.*$', 'description: ' + edit['description'], updated, flags=re.M)
    for replacement in edit['replacements']:
        if 'old' in replacement:
            assert body.count(replacement['old']) == 1
            body = body.replace(replacement['old'], replacement['new'], 1)
        else:
            start = body.index(replacement['start'])
            end = body.index(replacement['end'], start)
            body = body[:start] + replacement['new'] + body[end:]
    final = prefix + '---' + updated + '---' + body
    parsed_metadata = yaml.safe_load(final.split('---', 2)[1])
    parsed = parse_temporal_claim_revisions(parsed_metadata)
    assert len(parsed) == len(old) + 1
    assert [r.to_dict() for r in parsed[:-1]] == [r.to_dict() for r in old]
    assert parsed_metadata['evidence'] == [source] + metadata['evidence']
    changes[path] = final
    print(name, len(old), '->', len(parsed), revision['revision_id'])
index = ROOT / 'index.md'
updated_index, count = re.subn(r'^\* \[Loci\]\(\./projects/loci.md\).*$', data['index_line'], index.read_text(), flags=re.M)
assert count == 1
(ROOT / source).write_text(data['source'])
for path, content in changes.items():
    path.write_text(content)
index.write_text(updated_index)
with (ROOT / 'log.md').open('a') as stream:
    stream.write(data['log_entry'])
