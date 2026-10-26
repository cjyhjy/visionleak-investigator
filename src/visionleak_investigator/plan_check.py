"""Read-only manifest checking against accepted, unchanged audit evidence."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .common import digest, file_hash, no_symlink, now, read_json, write_json
from .domain import Registry, input_manifest, validate


def known_conflicts(task: dict, evidence: list[dict], manifest: dict) -> list[dict]:
    """Candidates and human same-source reviews are not exact/entity constraints."""
    paths = {r['path']: r for r in manifest['files'] if r['supported_image']}
    conflicts = []
    for item in evidence:
        if item['dataset_manifest_digest'] != manifest['digest']:
            raise ValueError('Evidence belongs to a different input manifest')
        exact = item['kind'] in ('core.byte_identical', 'core.pixel_identical') and item['verification_state'].get('exact_recomputed') == 'valid'
        entity = (item['kind'] == 'metadata.entity_overlap' and task['goal_confirmed']
                  and task['goal'] == 'new_entity_generalization'
                  and item['verification_state'].get('metadata_integrity') == 'valid'
                  and item['facts'].get('entity_key_confirmed') is True)
        if not (exact or entity):
            continue
        files = item['files']
        if len(set(files)) != len(files) or any(p not in paths for p in files):
            raise ValueError('Known conflict has an invalid source mapping')
        if len({paths[p]['image_split'] for p in files}) > 1:
            conflicts.append({'evidence_ref': item['evidence_id'], 'kind': item['kind'], 'files': files})
    return conflicts


def check_manifest(task: dict, evidence: list[dict], manifest: dict, plan: dict) -> dict:
    """Shared by proposal generation and the standalone checker; never mutates input."""
    validate(plan, 'plan-manifest')
    if plan['source_manifest_digest'] != manifest['digest']:
        raise ValueError('Plan source manifest digest does not match audit')
    source = {r['path']: r for r in manifest['files'] if r['supported_image']}
    rows = plan['new_manifest']
    if len({r['path'] for r in rows}) != len(rows):
        raise ValueError('Duplicate plan paths')
    if {r['path'] for r in rows} != set(source):
        raise ValueError('Plan must map every registered image exactly once, without unknown paths')
    for row in rows:
        if row['image_split'] != source[row['path']]['image_split']:
            raise ValueError('Plan cannot change an original image split')
        if row['image_split'] == 'test' and not row['included']:
            raise ValueError('Original test images must remain included')
    included = {r['path'] for r in rows if r['included']}
    conflicts = known_conflicts(task, evidence, manifest)
    remaining = [c['evidence_ref'] for c in conflicts
                 if len({source[p]['image_split'] for p in c['files'] if p in included}) > 1]
    changes = [{'path': r['path'], 'image_split': r['image_split'], 'was_included': True,
                'included': False, 'reason': 'candidate manifest requests exclusion; requires review',
                'evidence_refs': [c['evidence_ref'] for c in conflicts if r['path'] in c['files']]}
               for r in rows if not r['included']]
    return {'structure': 'passed', 'test_preserved': True, 'protect_eval_split': True,
            'known_conflicts_remaining': remaining,
            'known_conflicts_resolved': [c['evidence_ref'] for c in conflicts if c['evidence_ref'] not in remaining],
            'scope': 'structure and known evidence only', 'image_reaudit': 'not_run',
            'changes': changes, 'affected_splits': sorted({r['image_split'] for r in changes}),
            'retained_images_by_split': {s: sum(r['included'] and r['image_split'] == s for r in rows)
                                         for s in ('train', 'validation', 'test')}}


def _output_path(out: Path, run: Path, registry: Registry, plan_path: Path) -> Path:
    out = no_symlink(out)
    if out.exists():
        raise ValueError('Plan-check output must be a new file')
    # A revision belongs to the immutable audit tree, including its ancestors.
    audit_roots = [run, *(p for p in run.parents if (p/'manifest.json').is_file() and (p/'report.json').is_file())]
    protected = [*audit_roots, plan_path,
                 *(registry.dataset(ref) for ref in registry.value['datasets']),
                 *(registry.document(ref) for ref in registry.value.get('documents', {}))]
    if any(out.is_relative_to(p) or p.is_relative_to(out) for p in protected):
        raise ValueError('Plan-check output overlaps audit, input, or registered source')
    return out


def check_plan(run: Path, plan_path: Path, *, out: Path | None = None) -> dict:
    from .integrity import verify_run
    from .workflow import code_digest

    start = time.monotonic()
    run = no_symlink(run)
    plan_path = no_symlink(plan_path)
    plan = read_json(plan_path)
    report = verify_run(run)
    if report['coverage'].get('source_unchanged') is not True:
        raise ValueError('Audit input was unstable; new audit required')
    manifest = read_json(run/'manifest.json')
    source = read_json(run/'input-manifest.json')
    if source['digest'] != digest(source['files']) or source['digest'] != manifest['dataset_manifest_digest']:
        raise ValueError('Saved input manifest changed')
    task = read_json(run/'task.json')
    registry = Registry(read_json(run/'registry.private.json'))
    if input_manifest(registry.dataset(task['dataset_ref']), task['limits']) != source:
        raise ValueError('Saved input manifest differs from current source')
    destination = _output_path(out, run, registry, plan_path) if out is not None else None
    accepted = {c['audit_id'] for c in report['coverage']['profiles'].values()}
    evidence = [json.loads(line) for line in (run/'evidence.jsonl').read_text().splitlines()]
    evidence = [e for e in evidence if not e['kind'].startswith('core.') or e['core_audit_id'] in accepted]
    result = check_manifest(task, evidence, source, plan)
    result.update(schema_version=1, created_at=now(),
                  status='known_conflicts_remaining' if result['known_conflicts_remaining'] else 'no_known_conflicts_remaining',
                  source_manifest_digest=source['digest'], audit_manifest_digest=digest(manifest),
                  audit_report_digest=digest(report), candidate_manifest_digest=digest(plan),
                  evidence_sha256=file_hash(run/'evidence.jsonl'), processor_code_digest=code_digest(),
                  audit_state=report['state'], audit_coverage=report['coverage'],
                  requires_approval=True, source_files_modified=False,
                  limitations=['No new image audit, detection accuracy or universal absence claim.',
                               'Incomplete audit coverage remains incomplete after this check.',
                               'Review class/sample balance before applying any exclusions.',
                               'Previously trained models may require retraining and independent evaluation.'])
    # Detect ordinary concurrent edits; this is a before/after check, not an atomic snapshot.
    if read_json(plan_path) != plan or verify_run(run) != report:
        raise ValueError('Plan or audit changed during plan-check')
    result['execution'] = {'wall_seconds': time.monotonic()-start, 'core_audit_runs': 0,
                           'model_calls': 0, 'accounting': 'standalone check; original audit ledger unchanged'}
    if destination is not None:
        write_json(destination, result, exclusive=True)
    return result
