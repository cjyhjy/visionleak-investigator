"""Separate evaluator for a frozen question/answer contract, never a runtime tool."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from .common import digest, file_hash, read_json, safe_child, write_json
from .domain import Registry, input_manifest, validate
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


def score_interaction(task: dict, registry: dict, truth: dict, run: Path, transcript: list[dict], *, failure: str | None = None) -> dict:
    manifest = input_manifest(Registry(registry).dataset(task['dataset_ref']), task['limits'])
    info = validate_interaction_truth(truth, task, manifest)
    report = None
    if not failure:
        try: report = verify_run(run)
        except (ValueError, OSError, KeyError) as error: failure = str(error)
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
    seen=set()
    for row in rows:
        report=verify_run(safe_child(path.parent,row['run']))
        if digest(report)!=row['report_digest'] or report['questions']!=row['questions']:
            raise ValueError('Transcript questions differ from saved report')
        asked={q['question_code'] for q in row['questions']}
        answered=row['answered_questions']
        if len(set(answered))!=len(answered) or set(answered)&seen or not set(answered)<=asked:
            raise ValueError('Answer transcript duplicates or exceeds requested questions')
        if answered:
            if not set(answered)<=set(truth['answerable_questions']):raise ValueError('Unanswerable response supplied')
            payload=read_json(safe_child(path.parent,row['answer_path']))
            expected={'actor':'fixed scripted answer broker; no human participant'}
            for code in answered:expected.update(truth['answerable_questions'][code])
            if payload!=expected:raise ValueError('Delivered answer differs from frozen contract')
            result=read_json(safe_child(path.parent,row['answer_result']))
            if result['error'] or result['exit_code'] not in (0,2,3):raise ValueError('Answer not accepted by worker')
        seen.update(answered)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('task','registry','truth','run','transcript','out'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--failure'); args=parser.parse_args()
    truth=read_json(args.truth);transcript=validate_transcript(args.transcript,truth)
    score=score_interaction(read_json(args.task),read_json(args.registry),truth,args.run,transcript,failure=args.failure)
    score['truth_sha256']=file_hash(args.truth);write_json(args.out,score,exclusive=True)
    print(json.dumps({'status':'scored','state':score['state'],'usable_output':score['usable_output']}))


if __name__=='__main__': main()
