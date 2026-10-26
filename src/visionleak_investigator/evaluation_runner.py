"""Execute a frozen catalog with isolated real A/B/C workers and a truth-only scorer."""
from __future__ import annotations

import json
import resource
import time
from pathlib import Path
import sys

from .common import PROJECT, append_json, digest, file_hash, no_symlink, now, read_json, safe_child, write_json
from .core import execute
from .domain import Registry, input_manifest
from .evaluation import comparable, resource_totals
from .evaluation_data import verify_frozen
from .evaluation_scoring import AXES, METRIC_VERSION, validate_truth

STATES = ('COMPLETED', 'PARTIAL', 'WAITING_USER', 'FAILED', 'blocked', 'not_run')


def summarize_quality(rows: list[dict]) -> dict:
    """Descriptive counts; repeated runs/pairs are never independent sample units."""
    quality = {}
    for condition in ('A', 'B', 'C', 'D'):
        selected = [r for r in rows if r['condition'] == condition]
        scored = [r for r in selected if r.get('score')]
        if not selected or len(scored) != len(selected):
            quality[condition] = {'status': 'unavailable', 'scheduled_runs': len(selected),
                                  'scored_runs': len(scored),
                                  'scheduled_known_positive_counts': {a: sum(r['expected_truth_denominators'][a] for r in selected) for a in AXES}, 'reason': 'Missing/unrun scores; no successful-only aggregate'}
            continue
        axes = {}
        for axis in AXES:
            values = [r['score'][axis] for r in scored]
            totals = {key: sum(v[key] for v in values) for key in
                      ('tp', 'fp', 'fn', 'predicted_pairs', 'unknown_predicted_pairs', 'truth_denominator', 'eligible_pairs')}
            complete = all(v['truth_denominator_complete'] for v in values)
            tp, fp, fn = (totals[k] for k in ('tp', 'fp', 'fn'))
            axes[axis] = {**totals, 'truth_denominator_complete': complete,
                'precision': tp/(tp+fp) if complete and tp+fp else None,
                'recall': tp/(tp+fn) if complete and tp+fn else None,
                'f1': 2*tp/(2*tp+fp+fn) if complete and 2*tp+fp+fn else None}
            # Each task gets equal weight after averaging its repetitions. No CI/significance claim.
            task_means = {}
            for task in sorted({r['task_id'] for r in scored}):
                numbers = [r['score'][axis]['recall'] for r in scored if r['task_id'] == task]
                task_means[task] = sum(numbers)/len(numbers) if all(n is not None for n in numbers) else None
            defined = [v for v in task_means.values() if v is not None]
            axes[axis]['task_macro_recall'] = sum(defined)/len(defined) if defined else None
            axes[axis]['task_macro_defined_count'] = len(defined)
            axes[axis]['task_macro_undefined_count'] = len(task_means)-len(defined)
        quality[condition] = {'status': 'scored', 'scheduled_runs': len(selected), 'scored_runs': len(scored),
                              'failed_runs_in_denominator': sum(not r['score']['usable_output'] for r in scored), **axes}
    return quality


def run_catalog(catalog: dict, root: Path, protocol: dict, frozen_path: Path, out: Path, *,
                partition: str, replay_of: Path | None = None) -> dict:
    started = time.monotonic()
    self_start, child_start = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    root, out, frozen_path = (no_symlink(p) for p in (root, out, frozen_path))
    if out.is_relative_to(root) or root.is_relative_to(out) or frozen_path.is_relative_to(out):
        raise ValueError('Evaluation output and suite/freeze must be disjoint')
    if out.exists():
        raise FileExistsError('Evaluation output must be new')
    frozen = read_json(frozen_path)
    frozen_sha = file_hash(frozen_path)
    check = verify_frozen(frozen, catalog, root, protocol, partition=partition)
    if protocol['metric_definition'] != METRIC_VERSION:
        raise ValueError('Executable evaluation requires metric_definition='+METRIC_VERSION)
    tasks = [r for r in frozen['catalog']['tasks'] if r['benchmark_partition'] == partition]
    if not tasks:
        raise ValueError('Selected partition contains no tasks')
    denominators = {}
    for row in tasks:
        task = read_json(safe_child(root, row['task_path']))
        registry = Registry(read_json(safe_child(root, row['registry_path'])))
        if not task['goal_confirmed'] or task['goal'] == 'unspecified':
            raise ValueError('Detection benchmark requires a confirmed goal; interaction evaluation is separate')
        if task['privacy']['remote_model_allowed']:
            raise ValueError('Catalog A/B/C execution requires local-only TaskSpec; model declarations are not authorization')
        # All registered documents, including unused ones, stay outside the writable output tree.
        if any(registry.document(ref).is_relative_to(out) for ref in registry.value.get('documents', {})):
            raise ValueError('Output and registered documents must be disjoint')
        info = validate_truth(read_json(safe_child(root, row['truth_path'])), task,
                              input_manifest(registry.dataset(task['dataset_ref']), task['limits']))
        denominators[row['task_id']] = info['truth_denominators']
    role = 'replay' if replay_of is not None else 'evaluation'
    claim = frozen_path.with_name(frozen_path.name+'.executions')/'test.json'
    if replay_of is not None:
        replay_of = no_symlink(replay_of)
        prior = read_json(replay_of/'evaluation_manifest.json')
        if prior['freeze_digest'] != frozen['freeze_digest'] or prior['benchmark_partition'] != partition:
            raise ValueError('Replay must reference an attempt of the same frozen partition')
    if partition == 'test':
        if replay_of is None:
            if claim.exists():
                raise ValueError('Frozen test already attempted; use an explicit replay reference')
            write_json(claim, {'freeze_digest': frozen['freeze_digest'], 'output': str(out), 'started_at': now()}, exclusive=True)
        else:
            claimed = read_json(claim)
            if claimed['freeze_digest'] != frozen['freeze_digest']:
                raise ValueError('Test execution claim changed')
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'frozen_config.json', frozen, exclusive=True)
    write_json(out/'source_split_manifest.json', {'sources': catalog['sources'], 'components': frozen['catalog']['components']}, exclusive=True)
    schedule = [{'task_id': t['task_id'], 'condition': c, 'repetition': repetition}
                for t in tasks for repetition in range(1, protocol['repetitions']+1) for c in ('A', 'B', 'C', 'D')]
    manifest = {'schema_version': 1, 'created_at': now(), 'freeze_digest': frozen['freeze_digest'],
        'benchmark_partition': partition, 'evaluation_role': role, 'replay_of': str(replay_of) if replay_of else None,
        'metric_definition': METRIC_VERSION, 'schedule': schedule, 'model_execution': 'not_run',
        'truth_isolation': 'Only scorer subprocess receives truth paths; worker receives task/registry/output/condition only. Application boundary, not an OS read sandbox.',
        'cache': 'Fresh task and Core processes; no shared fingerprint cache; OS caches are not flushed.',
        'status': 'running'}
    write_json(out/'evaluation_manifest.json', manifest, exclusive=True)
    for filename in ('per_run.jsonl', 'failures.jsonl', 'comparison_checks.jsonl', 'gate_checks.jsonl'):
        (out/filename).touch(exist_ok=False)
    rows = []
    by_id = {t['task_id']: t for t in tasks}
    comparison_manifests = {}
    rejection = None

    def gate(phase: str, item: dict | None = None) -> None:
        try:
            if file_hash(frozen_path) != frozen_sha:
                raise ValueError('Frozen file changed during execution')
            value = verify_frozen(frozen, catalog, root, protocol, partition=partition)
        except Exception as exc:
            append_json(out/'gate_checks.jsonl', {'phase': phase, 'item': item, 'status': 'rejected', 'error': str(exc)})
            raise
        append_json(out/'gate_checks.jsonl', {'phase': phase, 'item': item, 'status': 'passed', 'freeze_digest': value['freeze_digest']})

    def save(row: dict) -> None:
        row['expected_truth_denominators'] = denominators[row['task_id']]
        rows.append(row)
        append_json(out/'per_run.jsonl', row)
        if row['state'] in ('FAILED', 'not_run'):
            append_json(out/'failures.jsonl', row)

    try:
        gate('before_schedule')
        for item in schedule:
            if item['condition'] == 'D':
                save({**item, 'state': 'blocked', 'reason': 'Provider adapter/live model authorization unavailable; no scripted substitution', 'model_execution': 'not_run'})
                continue
            taskrow = by_id[item['task_id']]
            taskpath, regpath, truthpath = (safe_child(root, taskrow[k]) for k in ('task_path', 'registry_path', 'truth_path'))
            task = read_json(taskpath)
            suffix = Path(item['task_id'])/f'r{item["repetition"]:02d}'/item['condition']
            dest, process, scorer = out/'runs'/suffix, out/'processes'/suffix, out/'scorers'/suffix
            row = {**item, 'state': 'FAILED', 'model_execution': 'not_run', 'run': dest.relative_to(out).as_posix(),
                   'process_record': process.relative_to(out).as_posix(), 'scorer_record': scorer.relative_to(out).as_posix()}
            result, report, worker_manifest = None, None, None
            gate('before_worker', item)
            try:
                result = execute([sys.executable, '-m', 'visionleak_investigator.evaluation_worker',
                    '--task', str(taskpath), '--registry', str(regpath), '--out', str(dest), '--condition', item['condition']],
                    PROJECT, process, task['limits']['max_tool_wall_seconds']+30)
                if result['error']:
                    raise ValueError('Worker process failed: '+result['error'])
                report = read_json(dest/'report.json')
                if result['exit_code'] != {'COMPLETED': 0, 'PARTIAL': 2, 'WAITING_USER': 3, 'FAILED': 1}[report['state']]:
                    raise ValueError('Worker exit/report status mismatch')
                worker_manifest = read_json(dest/'manifest.json')
                if (worker_manifest['task_digest'] != digest(task) or worker_manifest['dataset_manifest_digest'] != taskrow['input_digest'] or
                        any(worker_manifest[k] != frozen[k] for k in ('core_lock_digest', 'runtime_lock_digest', 'code_digest'))):
                    raise ValueError('Worker manifest differs from frozen execution')
                if digest(report['task']['limits']) != taskrow['limits_digest']:
                    raise ValueError('Worker total limits changed')
                row.update(state=report['state'], costs=report['budget']['spent'])
            except Exception as exc:
                row['error'] = str(exc)
            row['full_task_resources'] = result.get('resources') if result else None
            row['full_task_wall_seconds'] = result.get('wall_seconds') if result else None
            try:
                gate('after_worker', item)
                argv = [sys.executable, '-m', 'visionleak_investigator.evaluation_scoring',
                        '--task', str(taskpath), '--registry', str(regpath), '--truth', str(truthpath),
                        '--run', str(dest), '--out', str(out/'scores'/suffix/'score.json')]
                if row['state'] == 'FAILED':
                    argv += ['--failure', row.get('error', 'Worker reported FAILED')]
                scored = execute(argv, PROJECT, scorer, max(60, task['limits']['max_tool_wall_seconds']+30))
                row['scoring_resources'] = scored.get('resources')
                if scored['error'] or scored['exit_code'] != 0:
                    row.update(state='FAILED', scoring_error='Scorer rejected or failed; see original process logs')
                else:
                    row['score'] = read_json(out/'scores'/suffix/'score.json')
                    if row['score']['truth_sha256'] != taskrow['truth_sha256'] or row['score']['dataset_manifest_digest'] != taskrow['input_digest']:
                        raise ValueError('Scorer identity differs from frozen input/truth')
                gate('after_scorer', item)
            except Exception:
                row['comparison_status'] = 'rejected'
                save(row)
                raise
            if worker_manifest and row.get('score', {}).get('usable_output'):
                key = (item['task_id'], item['repetition'])
                comparison_manifests.setdefault(key, []).append((worker_manifest, task))
                try:
                    comparable(comparison_manifests[key])
                except Exception:
                    row['comparison_status'] = 'rejected'
                    save(row)
                    raise
            row['comparison_status'] = 'accepted'
            save(row)
        gate('before_aggregation')
    except Exception as exc:
        rejection = str(exc)
        finished = {(r['task_id'], r['condition'], r['repetition']) for r in rows}
        for item in schedule:
            if (item['task_id'], item['condition'], item['repetition']) not in finished:
                save({**item, 'state': 'blocked' if item['condition'] == 'D' else 'not_run',
                      'reason': 'Evaluation stopped after rejection: '+rejection, 'model_execution': 'not_run'})
    for taskrow in tasks:
        for repetition in range(1, protocol['repetitions']+1):
            entries = comparison_manifests.get((taskrow['task_id'], repetition), [])
            append_json(out/'comparison_checks.jsonl', {'task_id': taskrow['task_id'], 'repetition': repetition,
                'accepted_manifests': len(entries), 'status': 'rejected' if rejection else 'passed' if len(entries) == 3 else 'partial'})
    status = 'rejected' if rejection else 'completed_with_failures' if any(r['state'] == 'FAILED' for r in rows) else 'completed_no_model'
    self_end, child_end = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = lambda value: value.ru_utime+value.ru_stime
    pipeline_resources = {'wall_seconds': time.monotonic()-started,
        'orchestrator_cpu_seconds': cpu(self_end)-cpu(self_start),
        'waited_child_cpu_seconds': cpu(child_end)-cpu(child_start),
        'peak_tree_rss_bytes': None,
        'scope': 'Current process and waited descendants since runner entry, through pre-summary; CLI runs in an isolated process. Whole-pipeline peak RSS not measured; task/scorer tree RSS recorded separately.'}
    summary = {'status': status, 'rejection': rejection, 'benchmark_partition': partition, 'evaluation_role': role,
        'tasks': len(tasks), 'repetitions': protocol['repetitions'],
        'declared_independent_components': check['independent_components'],
        'runs': {c: {s: sum(r['condition'] == c and r['state'] == s for r in rows) for s in STATES} for c in ('A', 'B', 'C', 'D')},
        'quality': summarize_quality(rows) if not rejection else None,
        'quality_by_repetition': {str(n): summarize_quality([r for r in rows if r['repetition'] == n]) for n in range(1, protocol['repetitions']+1)} if not rejection else None,
        'pipeline_resources': pipeline_resources, 'resources_by_condition': resource_totals(rows), 'model_calls': 0, 'real_agent_experiment': 'not_run',
        'research_gain': 'not_established', 'E': 'not_run; second phase',
        'limitations': ['Source and license identities are declarations, not independently authenticated.',
            'Pair/repetition counts are descriptive, not independent sample sizes. No statistical intervals or significance claim.',
            'Partial annotation yields unknown full precision/recall/F1; labeled subsets remain explicit.',
            'Failed workers with a valid truth score retain positives as missed usable predictions; missing scorer output suppresses condition aggregates.',
            'Task resources exclude scorer overhead; pipeline CPU/wall includes orchestration and waited children. Whole-pipeline peak RSS is not measured.',
            'This detection benchmark requires confirmed goals; interactive usability and human time savings are not measured.',
            'D/E not executed; no Agent-versus-rule benefit established.']}
    write_json(out/'metrics.json', summary, exclusive=True)
    write_json(out/'costs.json', [{k: r[k] for k in ('task_id', 'condition', 'repetition', 'state', 'costs', 'full_task_resources', 'full_task_wall_seconds', 'scoring_resources', 'process_record', 'scorer_record') if k in r} for r in rows], exclusive=True)
    write_json(out/'evaluation_manifest.json', {**manifest, 'status': status, 'finished_at': now(), 'rejection': rejection})
    (out/'summary.md').write_text('# Frozen catalog evaluation\n\n'+json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return summary
