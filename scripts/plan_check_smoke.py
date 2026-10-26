"""Standalone plan-check CLI acceptance on a real, synthetic Core audit."""
import argparse
import copy
import json
from pathlib import Path
import sys

from visionleak_investigator.common import PROJECT, digest, file_hash, read_json, write_json
from visionleak_investigator.core import execute
from visionleak_investigator.demo import make_task
from visionleak_investigator.domain import Registry, input_manifest
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.workflow import code_digest, run_task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out.resolve(); out.mkdir(parents=True, exist_ok=False)
    task, registry = make_task(out/'fixture', 77001)
    run = out/'run'; report = run_task(task, registry, run, profiles=['base', 'all'])
    before = input_manifest(Registry(registry).dataset(task['dataset_ref']), task['limits'])
    audit_files = {str(p.relative_to(run)): file_hash(p) for p in run.rglob('*') if p.is_file()}
    proposal = read_json(run/'proposal.json')
    original = {k: proposal[k] for k in ('source_manifest_digest', 'new_manifest')}
    cases = []
    for name, expected in [('remaining', 2), ('cleared', 0), ('test-excluded', 1), ('unknown-path', 1)]:
        plan = copy.deepcopy(original)
        if name == 'cleared':
            for row in plan['new_manifest']:
                if row['image_split'] == 'validation': row['included'] = False
        if name == 'test-excluded': next(r for r in plan['new_manifest'] if r['image_split'] == 'test')['included'] = False
        if name == 'unknown-path': plan['new_manifest'][0]['path'] = '../escape.png'
        path = out/f'plans/{name}.json'; write_json(path, plan, exclusive=True)
        destination = out/f'checks/{name}.json'
        result = execute([sys.executable, '-m', 'visionleak_investigator.cli', 'plan-check',
                          '--run', str(run), '--manifest', str(path), '--out', str(destination)],
                         PROJECT, out/f'commands/{name}', 60)
        assert result['exit_code'] == expected and result['error'] is None
        if expected == 1:
            assert not destination.exists()
            assert read_json(out/f'commands/{name}/stderr.log')['status'] == 'failed'
        else:
            checked = read_json(destination)
            assert checked['image_reaudit'] == 'not_run' and checked['test_preserved']
            assert bool(checked['known_conflicts_remaining']) == (expected == 2)
        cases.append({'case': name, 'exit_code': expected, 'status': 'passed', 'command': f'commands/{name}/result.json',
                      'candidate_manifest': f'plans/{name}.json', 'result': str(destination.relative_to(out)) if expected != 1 else None})
    assert verify_run(run, recompute_identity=True) == report
    assert audit_files == {str(p.relative_to(run)): file_hash(p) for p in run.rglob('*') if p.is_file()}
    assert input_manifest(Registry(registry).dataset(task['dataset_ref']), task['limits']) == before
    receipt = {'status': 'passed', 'code_digest': code_digest(), 'model_calls': 0,
               'real_agent_experiment': 'not_run', 'data_kind': 'self-generated controlled synthetic fixtures',
               'audit_manifest_digest': digest(read_json(run/'manifest.json')), 'cases': cases,
               'source_unchanged': True, 'original_audit_files_unchanged': True, 'image_reaudit': 'not_run'}
    write_json(out/'receipt.json', receipt, exclusive=True)
    print(json.dumps({'status': 'passed', 'cases': len(cases), 'model_calls': 0}))


if __name__ == '__main__': main()
