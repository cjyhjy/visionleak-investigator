"""Evaluator-only truth contract and isolated scoring; never a Planner tool.

Scores usable, validated claims. Exhaustive labels use a closed-world negative
set; partial labels leave unknown pairs unknown. Failed attempts have no usable
predictions and retain every annotated positive in the end-to-end denominator.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from .common import digest, file_hash, read_json, write_json
from .domain import Registry, TaskSpec, input_manifest, validate
from .integrity import verify_run

METRIC_VERSION = 'catalog-pairs-v1'
AXES = ('exact', 'related_excluding_exact', 'entity_goal_conflict')
Pair = tuple[str, str]


def _pair_set(rows: list) -> set[Pair]:
    if not isinstance(rows, list):
        raise ValueError('Truth pairs must be lists')
    result = set()
    for pair in rows:
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(p, str) for p in pair):
            raise ValueError('Truth pair must contain two image paths')
        key = tuple(sorted(pair))
        if key in result:
            raise ValueError('Duplicate unordered truth pair')
        result.add(key)
    return result


def validate_truth(truth: dict, task: dict, manifest: dict) -> dict:
    validate(truth, 'evaluation-truth')
    required = {'schema_version', 'task_id', 'dataset_manifest_digest', 'goal', 'basis', *AXES}
    if not isinstance(truth, dict) or set(truth) != required or truth['schema_version'] != 1:
        raise ValueError('Executable truth schema mismatch')
    if (truth['task_id'] != task['task_id'] or truth['goal'] != task['goal'] or
            truth['dataset_manifest_digest'] != manifest['digest']):
        raise ValueError('Truth task/goal/input identity mismatch')
    if (not isinstance(truth['basis'], dict) or set(truth['basis']) != {'kind', 'description'} or
            truth['basis']['kind'] not in ('synthetic_generation', 'source_annotation') or
            not isinstance(truth['basis']['description'], str) or not truth['basis']['description'].strip()):
        raise ValueError('Truth annotation basis required')
    images = {f['path']: f['image_split'] for f in manifest['files'] if f['supported_image']}
    counts = {s: sum(v == s for v in images.values()) for s in set(images.values())}
    universe = sum(a*b for a, b in itertools.combinations(counts.values(), 2))
    labels = {}
    for axis in AXES:
        spec = truth[axis]
        if (not isinstance(spec, dict) or set(spec) != {'coverage', 'positive_pairs', 'negative_pairs'} or
                spec['coverage'] not in ('exhaustive', 'partial')):
            raise ValueError('Truth label coverage must be exhaustive or partial')
        positive, negative = _pair_set(spec['positive_pairs']), _pair_set(spec['negative_pairs'])
        if positive & negative:
            raise ValueError('Conflicting truth labels')
        for a, b in positive | negative:
            if a not in images or b not in images or images[a] == images[b]:
                raise ValueError('Truth requires registered cross-split image pairs')
        if spec['coverage'] == 'exhaustive' and negative:
            raise ValueError('Exhaustive labels imply all other eligible pairs negative; omit explicit negatives')
        labels[axis] = (positive, negative)
    if truth['exact']['coverage'] != 'exhaustive':
        raise ValueError('Exact labels must be exhaustive to define the approximate-pair denominator')
    if set.union(*labels['related_excluding_exact']) & labels['exact'][0]:
        raise ValueError('Approximate labels must exclude exact pairs')
    if task['goal'] != 'new_entity_generalization' and labels['entity_goal_conflict'][0]:
        raise ValueError('This goal does not prohibit entity overlap')
    return {'image_count': len(images), 'eligible_cross_split_pairs': universe,
            'eligible_approximate_pairs': universe-len(labels['exact'][0]),
            'truth_denominators': {a: len(labels[a][0]) for a in AXES}}


def score_labels(predicted: set[Pair], labels: dict, eligible: int) -> dict:
    positive, negative = _pair_set(labels['positive_pairs']), _pair_set(labels['negative_pairs'])
    complete = labels['coverage'] == 'exhaustive'
    tp = len(predicted & positive)
    fp = len(predicted-positive) if complete else len(predicted & negative)
    fn = len(positive-predicted)
    unknown = 0 if complete else len(predicted-positive-negative)
    precision = tp/(tp+fp) if tp+fp else None
    recall = tp/len(positive) if positive else None
    f1 = 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
    return {'tp': tp, 'fp': fp, 'fn': fn, 'predicted_pairs': len(predicted),
            'unknown_predicted_pairs': unknown, 'eligible_pairs': eligible,
            'truth_denominator': len(positive), 'truth_denominator_complete': complete,
            'precision': precision if complete else None, 'recall': recall if complete else None,
            'f1': f1 if complete else None,
            'labeled_subset': {'precision': precision, 'recall': recall, 'f1': f1},
            'meaning': 'Full eligible population' if complete else 'Partial annotation; full precision/recall/F1 unknown'}


def score_run(task: dict, registry_data: dict, truth: dict, run: Path, *, failure: str | None = None) -> dict:
    TaskSpec.parse(task)
    registry = Registry(registry_data)
    registry.check_confirmations(task)
    manifest = input_manifest(registry.dataset(task['dataset_ref']), task['limits'])
    truth_info = validate_truth(truth, task, manifest)
    predicted = {axis: set() for axis in AXES}
    candidate_pairs = set()
    report = None
    if failure is None:
        report = verify_run(run, recompute_identity=True)
        if report['task'] != task or read_json(run/'registry.private.json') != registry_data:
            raise ValueError('Worker task/registry differs from frozen inputs')
        if report['mode'] != 'rules' or report['model_execution'] != 'not_run':
            raise ValueError('A/B/C scorer only accepts real deterministic runs')
        if report['coverage'].get('source_unchanged') is not True:
            raise ValueError('Changed input cannot supply usable predictions')
        evidence = {e['evidence_id']: e for e in
                    (json.loads(line) for line in (run/'evidence.jsonl').read_text().splitlines())}
        images = {f['path']: f['image_split'] for f in manifest['files'] if f['supported_image']}
        for claim in report['claims']:
            records = [evidence[ref] for ref in claim['evidence_refs']]
            if claim['status'] == 'confirmed' and claim['claim_type'] in ('byte_identity', 'pixel_identity'):
                predicted['exact'].update(tuple(sorted(e['files'])) for e in records)
            elif claim['status'] == 'candidate' and claim['claim_type'] == 'perceptual_relation':
                candidate_pairs.update(tuple(sorted(e['files'])) for e in records)
            elif claim['status'] == 'confirmed' and claim['claim_type'] == 'goal_conflict':
                for record in records:
                    if record['kind'] == 'metadata.entity_overlap':
                        predicted['entity_goal_conflict'].update(tuple(sorted((a, b))) for a, b in
                            itertools.combinations(record['files'], 2) if images[a] != images[b])
        for pairs in [*predicted.values(), candidate_pairs]:
            if any(len(pair) != 2 or pair[0] not in images or pair[1] not in images or
                   images[pair[0]] == images[pair[1]] for pair in pairs):
                raise ValueError('Prediction outside eligible cross-split population')
    predicted['related_excluding_exact'] = candidate_pairs-_pair_set(truth['exact']['positive_pairs'])
    scores = {a: score_labels(predicted[a], truth[a], truth_info[
        'eligible_approximate_pairs' if a == 'related_excluding_exact' else 'eligible_cross_split_pairs']) for a in AXES}
    return {'metric_definition': METRIC_VERSION, 'task_id': task['task_id'],
            'truth_digest': digest(truth), 'dataset_manifest_digest': manifest['digest'],
            'usable_output': report is not None, 'failure': failure,
            'source_unchanged': report['coverage']['source_unchanged'] if report else None,
            'state': report['state'] if report else 'FAILED', **scores,
            'candidate_burden': len(candidate_pairs),
            'candidate_pairs_per_1000_images': len(candidate_pairs)*1000/truth_info['image_count'],
            'pending_review_pairs': len({r['pair_key'] for r in report['reviews'] if r['status'] == 'pending'}) if report else 0,
            'invalid_approximate_candidates': scores['related_excluding_exact']['fp'],
            'unknown_approximate_candidates': scores['related_excluding_exact']['unknown_predicted_pairs'],
            'claim_validation': 'passed' if report else 'no_usable_output',
            'unsupported_confirmed_claims': 0 if report else None,
            'prediction_policy': 'Only validated published claims; failed attempts have no usable predictions and retain full positive denominators',
            'coverage': report['coverage'] if report else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('task', 'registry', 'truth', 'run', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--failure')
    args = parser.parse_args()
    result = score_run(read_json(args.task), read_json(args.registry), read_json(args.truth), args.run, failure=args.failure)
    result['truth_sha256'] = file_hash(args.truth)
    write_json(args.out, result, exclusive=True)
    print(json.dumps({'status': 'scored', 'state': result['state'], 'usable_output': result['usable_output']}))


if __name__ == '__main__':
    main()
