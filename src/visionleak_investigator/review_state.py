"""Derived review coverage and durable copies of evidence-bound review inputs."""
from collections import Counter, defaultdict
from pathlib import Path

from .common import digest, file_hash, write_json


def review_coverage(reviews: list[dict]) -> dict:
    counts=Counter(r['status'] for r in reviews)
    groups=defaultdict(set)
    for row in reviews:groups[row['pair_key']].add(row['status'])
    resolved=sum(values in ({'confirmed'},{'rejected'}) for values in groups.values())
    attempted=sum(counts[s] for s in ('confirmed','rejected','unsure'))
    state='not_applicable' if not reviews else 'not_run' if not attempted else 'complete' if resolved==len(groups) else 'partial'
    return {'state':state,'total_records':len(reviews),'unique_pairs':len(groups),
            'requested_records':sum(bool(r.get('requested')) for r in reviews),
            'pending_records':counts['pending'],'confirmed_records':counts['confirmed'],
            'rejected_records':counts['rejected'],'unsure_records':counts['unsure'],
            'resolved_pairs':resolved,'unresolved_pairs':len(groups)-resolved,
            'scope':'Review applies to its bound Core witness; duplicate witnesses and unsure/conflicting decisions remain unresolved.'}


def preserve_review_inputs(evidence: list[dict], target: Path) -> dict:
    """Copy the saved payload, verifying its original params_digest, into each new revision."""
    files={}
    for item in evidence:
        if not item['kind'].startswith('human.'):continue
        payload=item['facts'];identity=digest(payload)
        if identity!=item['params_digest'] or item['evidence_id']!='review:'+identity:
            raise ValueError('Human review payload differs from its evidence identity')
        path='review-inputs/'+identity+'.json'
        if path not in files:write_json(target/path,payload,exclusive=True);files[path]=file_hash(target/path)
        item['source_positions']=[path]
    return files
