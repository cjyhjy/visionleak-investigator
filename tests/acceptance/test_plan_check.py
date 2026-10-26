import copy
import json
import subprocess
import sys

import pytest

from visionleak_investigator.common import file_hash, read_json, write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.interaction import import_review, resume_run
from visionleak_investigator.plan_check import check_plan
from visionleak_investigator.workflow import run_task


@pytest.fixture
def audited(tmp_path):
    task, registry = make_task(tmp_path/'fixture')
    doc = tmp_path/'fixture/context.md'; doc.write_text('Controlled synthetic plan-check fixture.')
    registry['documents']['context'] = {'path': str(doc), 'sha256': file_hash(doc)}
    task['context_refs'] = ['context']
    run = tmp_path/'run'
    run_task(task, registry, run, profiles=['base', 'all'])
    suggestion = read_json(run/'proposal.json')
    plan = {k: suggestion[k] for k in ('source_manifest_digest', 'new_manifest')}
    path = tmp_path/'candidate.json'
    write_json(path, plan)
    return run, path, plan


def tree_hash(root):
    return {str(p.relative_to(root)): file_hash(p) for p in root.rglob('*') if p.is_file()}


def test_plan_check_preserves_audit_and_inputs_with_finite_scope(audited, tmp_path):
    run, path, plan = audited
    before = tree_hash(run), tree_hash(tmp_path/'fixture')
    result = check_plan(run, path, out=tmp_path/'remaining.json')
    assert result['known_conflicts_remaining'] == read_json(run/'proposal.json')['plan_check']['known_conflicts_remaining']
    assert result['status'] == 'known_conflicts_remaining'
    assert result['test_preserved'] and result['image_reaudit'] == 'not_run'
    for row in plan['new_manifest']:
        if row['image_split'] == 'validation': row['included'] = False
    write_json(path, plan)
    result = check_plan(run, path, out=tmp_path/'cleared.json')
    assert result['status'] == 'no_known_conflicts_remaining'
    assert result['known_conflicts_resolved'] and result['audit_coverage']['profiles']
    assert result['execution']['core_audit_runs'] == result['execution']['model_calls'] == 0
    assert before == (tree_hash(run), tree_hash(tmp_path/'fixture'))


def test_plan_check_rejects_invalid_mapping_and_protects_test(audited):
    run, path, plan = audited
    variants = []
    bad = copy.deepcopy(plan); bad['source_manifest_digest'] = '0'*64; variants.append(bad)
    bad = copy.deepcopy(plan); bad['new_manifest'].append(bad['new_manifest'][0]); variants.append(bad)
    bad = copy.deepcopy(plan); bad['new_manifest'].pop(); variants.append(bad)
    for name in ('../escape.png', '/tmp/escape.png', 'test/unknown.png'):
        bad = copy.deepcopy(plan); bad['new_manifest'][0]['path'] = name; variants.append(bad)
    bad = copy.deepcopy(plan); bad['new_manifest'][0]['image_split'] = 'train'; variants.append(bad)
    bad = copy.deepcopy(plan); bad['new_manifest'][0]['included'] = 'false'; variants.append(bad)
    bad = copy.deepcopy(plan); bad['new_manifest'][0]['included'] = 1; variants.append(bad)
    bad = copy.deepcopy(plan); bad['extra'] = 'ignored?'; variants.append(bad)
    bad = copy.deepcopy(plan)
    next(r for r in bad['new_manifest'] if r['image_split'] == 'test')['included'] = False
    variants.append(bad)
    for bad in variants:
        write_json(path, bad)
        with pytest.raises(ValueError): check_plan(run, path)


def test_plan_check_output_cannot_mutate_audit_data_or_registered_docs(audited, tmp_path):
    run, path, plan = audited
    before = tree_hash(run), tree_hash(tmp_path/'fixture')
    for out in (path, run/'new.json', run/'tools/new.json', tmp_path/'fixture/images/test/new.json', tmp_path/'fixture/context.md'):
        with pytest.raises(ValueError): check_plan(run, path, out=out)
    link = tmp_path/'symlink'; link.symlink_to(tmp_path/'fixture/images', target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink'): check_plan(run, path, out=link/'new.json')
    # Parent audit protection also applies when checking a revision.
    revised = resume_run(run, {'actor': 'scripted test user', 'goal': 'content_audit'})
    from pathlib import Path
    with pytest.raises(ValueError, match='overlaps'):
        check_plan(Path(revised['revision']['path']), path, out=run/'new-result.json')
    assert tree_hash(tmp_path/'fixture') == before[1]
    assert all(file_hash(run/p) == h for p, h in before[0].items())


def test_plan_check_binds_source_and_saved_evidence(audited, tmp_path):
    run, path, plan = audited
    source = tmp_path/'fixture/images/test/002.png'
    original = source.read_bytes(); source.write_bytes(original+b'changed')
    with pytest.raises(ValueError, match='Input changed'): check_plan(run, path)
    source.write_bytes(original)
    saved = read_json(run/'input-manifest.json')
    saved['files'][0]['image_split'] = 'train'
    write_json(run/'input-manifest.json', saved)
    with pytest.raises(ValueError, match='Saved input manifest'): check_plan(run, path)


def test_review_confirmation_does_not_become_exact_plan_constraint(audited, tmp_path):
    run, path, plan = audited
    initial = check_plan(run, path)
    report = read_json(run/'report.json'); candidate = report['reviews'][0]
    revised = import_review(run, {'reviewer': 'scripted fixture, no human participant',
        'created_at': '2026-10-26T21:00:00+00:00', 'dataset_manifest_digest': plan['source_manifest_digest'],
        'audit_id': candidate['audit_id'], 'pair_ref': candidate['pair_ref'],
        'decision': 'confirmed', 'reason': 'controlled fixture annotation'})
    from pathlib import Path
    checked = check_plan(Path(revised['revision']['path']), path)
    assert checked['known_conflicts_remaining'] == initial['known_conflicts_remaining']
    assert checked['known_conflicts_resolved'] == initial['known_conflicts_resolved']


def test_plan_check_entity_constraints_follow_confirmed_goal(tmp_path):
    from test_interaction import entity_task
    task, registry = entity_task(tmp_path/'fixture')
    run = tmp_path/'run'; run_task(task, registry, run)
    suggestion = read_json(run/'proposal.json')
    plan = {k: suggestion[k] for k in ('source_manifest_digest', 'new_manifest')}
    for row in plan['new_manifest']: row['included'] = True
    path = tmp_path/'candidate.json'; write_json(path, plan)
    first = check_plan(run, path)
    assert any(ref.startswith('metadata:') for ref in first['known_conflicts_remaining'])
    revised = resume_run(run, {'actor': 'scripted fixture', 'goal': 'same_entity_new_view'})
    from pathlib import Path
    second = check_plan(Path(revised['revision']['path']), path)
    assert not any(ref.startswith('metadata:') for ref in second['known_conflicts_remaining'])


def test_plan_check_cli_distinguishes_remaining_clear_and_invalid(audited, tmp_path):
    run, path, plan = audited
    argv = [sys.executable, '-m', 'visionleak_investigator.cli', 'plan-check', '--run', str(run), '--manifest', str(path)]
    first = subprocess.run(argv, capture_output=True, text=True)
    assert first.returncode == 2 and json.loads(first.stdout)['known_conflicts_remaining']
    for row in plan['new_manifest']:
        if row['image_split'] != 'test': row['included'] = False
    write_json(path, plan)
    clear = subprocess.run(argv, capture_output=True, text=True)
    assert clear.returncode == 0 and json.loads(clear.stdout)['image_reaudit'] == 'not_run'
    plan['new_manifest'][0]['included'] = False  # First sorted path is test.
    write_json(path, plan)
    invalid = subprocess.run(argv, capture_output=True, text=True)
    assert invalid.returncode == 1 and json.loads(invalid.stderr)['status'] == 'failed'


def test_partial_audit_is_not_promoted_by_empty_known_conflict_set(tmp_path):
    task, registry = make_task(tmp_path/'fixture')
    task['limits']['max_comparisons_total'] = 1
    run = tmp_path/'run'; report = run_task(task, registry, run)
    assert report['state'] == 'PARTIAL'
    proposal = read_json(run/'proposal.json')
    plan = {k: proposal[k] for k in ('source_manifest_digest', 'new_manifest')}
    for row in plan['new_manifest']: row['included'] = row['image_split'] == 'test'
    path = tmp_path/'candidate.json'; write_json(path, plan)
    result = check_plan(run, path)
    assert not result['known_conflicts_remaining']
    assert result['audit_state'] == 'PARTIAL' and not result['audit_coverage']['profiles']['base']['complete']
    assert result['image_reaudit'] == 'not_run'
    assert read_json(run/'report.json') == report
