"""Separate evaluator for a frozen question/answer contract, never a runtime tool."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from .common import digest, file_hash, no_symlink, read_json, safe_child, write_json
from .domain import Registry, TaskSpec, input_manifest, validate
from .evaluation import score_pairs
from .integrity import verify_run

METRIC_VERSION = 'interaction-v1'


def validate_interaction_truth(truth: dict, task: dict, manifest: dict) -> dict:
    validate(truth, 'interaction-truth')
    if truth['task_id'] != task['task_id'] or truth['dataset_manifest_digest'] != manifest['digest']:
        raise ValueError('Interaction truth task/input identity mismatch')
    if task['goal_confirmed'] and task['goal'] != truth['goal']:
        raise ValueError('Confirmed initial goal contradicts interaction contract')
    if task['entity_key_confirmed'] and task['entity_key'] != truth['entity_key']:
        raise ValueError('Confirmed initial field contradicts interaction contract')
    needed = set()
    if not task['goal_confirmed']: needed.add('clarify_goal')
    field_needed = truth['goal'] != 'content_audit' and truth['entity_key'] is not None
    if field_needed and not task['entity_key_confirmed'] and task['metadata_ref']:
        needed.add('clarify_entity_key')
    if set(truth['necessary_questions']) != needed:
        raise ValueError('Necessary questions disagree with initial missingness and target goal')
    for question, payload in truth['answerable_questions'].items():
        field = 'goal' if question == 'clarify_goal' else 'entity_key'
        if payload[field] != truth[field]: raise ValueError('Answer contract contradicts target interpretation')
        if field == 'entity_key' and not task['metadata_ref']: raise ValueError('Field answer requires registered metadata')
    images = {r['path']: r['image_split'] for r in manifest['files'] if r['supported_image']}
    pairs = {tuple(sorted(p)) for p in truth['risk_positive_pairs']}
    if len(pairs) != len(truth['risk_positive_pairs']): raise ValueError('Duplicate unordered interaction risk pair')
    if any(a not in images or b not in images or images[a] == images[b] for a,b in pairs):
        raise ValueError('Interaction risk labels must reference cross-split registered images')
    if truth['goal'] != 'new_entity_generalization' and pairs:
        raise ValueError('This target goal does not prohibit declared entity overlap')
    return {'necessary_questions': sorted(needed), 'risk_positive_count': len(pairs),
            'field_interpretation_required': field_needed, 'answerable_questions': sorted(truth['answerable_questions'])}


def bound_interaction_report(task: dict, registry: dict, manifest: dict, run: Path,
                             transcript: list[dict], truth: dict) -> tuple[dict, dict]:
    """Accept C output only from the expected initial task and its verified revisions."""
    current = no_symlink(run)
    anchor = current.parent.parent if current.parent.name == 'revisions' else current
    mutable = {'goal', 'goal_confirmed', 'goal_evidence_refs',
               'entity_key', 'entity_key_confirmed', 'entity_key_evidence_refs'}
    fixed_task = {k:v for k,v in task.items() if k not in mutable}
    fixed_registry = {k:v for k,v in registry.items() if k != 'confirmations'}
    final = None; bindings = {}; seen = set(); child_manifest = None; chain = []
    while True:
        if current in seen: raise ValueError('Interaction revision cycle')
        seen.add(current)
        report = verify_run(current, recompute_identity=True)
        chain.append((current, report))
        record = read_json(current/'manifest.json')
        saved_registry = read_json(current/'registry.private.json')
        if report['task'] != read_json(current/'task.json'):
            raise ValueError('Interaction report task differs from saved task')
        if {k:v for k,v in report['task'].items() if k not in mutable} != fixed_task:
            raise ValueError('Interaction task/limits differ from frozen inputs')
        if record['dataset_manifest_digest'] != manifest['digest']:
            raise ValueError('Interaction input differs from frozen inputs')
        if {k:v for k,v in saved_registry.items() if k != 'confirmations'} != fixed_registry:
            raise ValueError('Interaction registry differs from frozen inputs')
        if any(saved_registry.get('confirmations', {}).get(k) != v
               for k,v in registry.get('confirmations', {}).items()):
            raise ValueError('Interaction initial confirmations changed')
        Registry(saved_registry).check_confirmations(report['task'])
        if report['mode'] != 'rules' or report['model_execution'] != 'not_run':
            raise ValueError('Interaction C scorer requires deterministic runs')
        if report['coverage'].get('source_unchanged') is not True:
            raise ValueError('Changed input cannot supply interaction predictions')
        if child_manifest and (child_manifest['parent_manifest_digest'] != digest(record)
                               or child_manifest['parent_report_digest'] != digest(report)):
            raise ValueError('Interaction revision parent binding changed')
        if final is None:
            final = report
            bindings.update(report_digest=digest(report), run_manifest_digest=digest(record))
        if current == anchor:
            if report.get('revision') or report['task'] != task or saved_registry != registry:
                raise ValueError('Interaction initial task/registry differs from frozen inputs')
            history = list(reversed(chain))
            if len(transcript) != len(history): raise ValueError('Interaction transcript does not cover the accepted revision chain')
            for index, (row, (path, observed)) in enumerate(zip(transcript, history)):
                if (row['run'] != str(path.relative_to(anchor.parent)) or row['report_digest'] != digest(observed)
                        or row['questions'] != observed['questions']):
                    raise ValueError('Interaction transcript belongs to a different run or questions')
                if index == len(history)-1:
                    if row['answered_questions']: raise ValueError('Final transcript observation has an unbound answer')
                else:
                    if not row['answered_questions']: raise ValueError('Revision lacks a delivered answer')
                    next_path, next_report = history[index+1]
                    if next_report['revision']['kind'] != 'answers': raise ValueError('Unexpected interaction revision kind')
                    if read_json(next_path/'answers.input.json') != read_json(safe_child(anchor.parent,row['answer_path'])):
                        raise ValueError('Transcript answer differs from actual revision input')
            validate_transcript_rows(transcript, anchor.parent, truth)
            bindings.update(initial_report_digest=digest(report), verified_revision_count=len(seen)-1)
            return final, bindings
        parent = no_symlink(Path(record['evidence_reused_from']))
        if parent != anchor and parent.parent != anchor/'revisions':
            raise ValueError('Interaction revision parent escaped initial run')
        child_manifest = record; current = parent


def score_interaction(task: dict, registry: dict, truth: dict, run: Path, transcript: list[dict], *, failure: str | None = None) -> dict:
    TaskSpec.parse(task); registered = Registry(registry); registered.check_confirmations(task)
    manifest = input_manifest(registered.dataset(task['dataset_ref']), task['limits'])
    info = validate_interaction_truth(truth, task, manifest)
    report = None; bindings = None; history_usable = False
    if failure is None or transcript:
        try:
            accepted, accepted_bindings = bound_interaction_report(task, registry, manifest, run, transcript, truth)
            history_usable = True
            if failure is None: report, bindings = accepted, accepted_bindings
        except (ValueError, OSError, KeyError) as error:
            failure = str(error) if failure is None else failure+'; unverified transcript: '+str(error)
    if not history_usable: transcript = []
    asked = [q['question_code'] for row in transcript for q in row.get('questions', [])]
    needed = set(info['necessary_questions']); observed = set(asked)
    answered = [code for row in transcript for code in row.get('answered_questions', [])]
    predicted = set()
    if report:
        evidence = {e['evidence_id']: e for e in map(json.loads, (run/'evidence.jsonl').read_text().splitlines())}
        splits = {r['path']: r['image_split'] for r in manifest['files'] if r['supported_image']}
        for claim in report['claims']:
            if claim['claim_type'] == 'goal_conflict' and claim['status'] == 'confirmed':
                for ref in claim['evidence_refs']:
                    witness = evidence[ref]
                    if witness['kind'] == 'metadata.entity_overlap':
                        predicted.update(tuple(sorted((a,b))) for a,b in itertools.combinations(witness['files'],2) if splits[a]!=splits[b])
    positive = {tuple(sorted(p)) for p in truth['risk_positive_pairs']}
    final_task = report['task'] if report else {}
    spent = report['budget']['spent'] if report else None
    return {'metric_definition': METRIC_VERSION, 'task_id': task['task_id'], 'truth_digest': digest(truth),
            'initial_task_digest': digest(task), 'initial_registry_digest': digest(registry), 'accepted_output': bindings,
            'question_history_usable': history_usable,
            'dataset_manifest_digest': manifest['digest'], 'usable_output': report is not None, 'failure': failure,
            'state': report['state'] if report else 'FAILED', 'goal_correct': bool(final_task.get('goal_confirmed') and final_task.get('goal')==truth['goal']),
            'field_correct': bool(final_task.get('entity_key_confirmed') and final_task.get('entity_key')==truth['entity_key']) if info['field_interpretation_required'] else None,
            'necessary_questions': len(needed), 'necessary_questions_asked': len(needed & observed),
            'necessary_questions_missed': sorted(needed-observed), 'questions_asked': len(asked),
            'excessive_questions': len(asked)-len(needed & observed),
            'unanswerable_questions': sum(code not in truth['answerable_questions'] for code in asked),
            'answers_delivered': len(answered), 'risk': score_pairs(predicted, positive),
            'unsupported_confirmed_claims': 0 if report else None,
            'question_budget_spent': spent['questions'] if spent else None,
            'review_budget_spent': spent['review_pairs'] if spent else None,
            'pending_review_pairs': len({r['pair_key'] for r in report['reviews'] if r['status']=='pending'}) if report else None,
            'budget_respected': bool(spent and spent['questions'] <= task['limits']['max_questions'] and spent['review_pairs'] <= task['limits']['max_review_pairs']),
            'coverage': report['coverage'] if report else None,
            'human_participants': 0, 'human_time_saved_seconds': None, 'model_calls': 0,
            'interpretation': 'Fixed scripted answers and exhaustive declared entity-risk labels; not a human or live Agent experiment.'}


def validate_transcript(path: Path, truth: dict) -> list[dict]:
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    return validate_transcript_rows(rows,path.parent,truth)


def validate_transcript_rows(rows: list[dict], base: Path, truth: dict) -> list[dict]:
    seen=set()
    for row in rows:
        report=verify_run(safe_child(base,row['run']))
        if digest(report)!=row['report_digest'] or report['questions']!=row['questions']:
            raise ValueError('Transcript questions differ from saved report')
        asked={q['question_code'] for q in row['questions']}
        answered=row['answered_questions']
        if len(set(answered))!=len(answered) or set(answered)&seen or not set(answered)<=asked:
            raise ValueError('Answer transcript duplicates or exceeds requested questions')
        if answered:
            if not set(answered)<=set(truth['answerable_questions']):raise ValueError('Unanswerable response supplied')
            payload=read_json(safe_child(base,row['answer_path']))
            expected={'actor':'fixed scripted answer broker; no human participant'}
            for code in answered:expected.update(truth['answerable_questions'][code])
            if payload!=expected:raise ValueError('Delivered answer differs from frozen contract')
            result=read_json(safe_child(base,row['answer_result']))
            if result['error'] or result['exit_code'] not in (0,2,3):raise ValueError('Answer not accepted by worker')
        seen.update(answered)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('task','registry','truth','run','transcript','out'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--failure'); args=parser.parse_args()
    truth=read_json(args.truth);transcript=[json.loads(line) for line in args.transcript.read_text().splitlines()]
    score=score_interaction(read_json(args.task),read_json(args.registry),truth,args.run,transcript,failure=args.failure)
    score['truth_sha256']=file_hash(args.truth);write_json(args.out,score,exclusive=True)
    print(json.dumps({'status':'scored','state':score['state'],'usable_output':score['usable_output']}))


if __name__=='__main__': main()
