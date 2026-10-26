"""Reproducible synthetic catalog for executor acceptance, not independent natural data."""
from __future__ import annotations

import itertools
from pathlib import Path

from .common import PROJECT, file_hash, now, write_json
from .demo import make_task
from .domain import Registry, input_manifest
from .evaluation_scoring import METRIC_VERSION


def make_catalog_suite(root: Path, *, count: int = 12, seed_start: int = 75000) -> tuple[dict, dict]:
    if not 3 <= count <= 30:
        raise ValueError('Synthetic catalog requires 3–30 tasks')
    root.mkdir(parents=True, exist_ok=False)
    catalog = {'schema_version': 1, 'sources': [], 'tasks': []}
    for i in range(count):
        partition = 'development' if i < count-2 else 'validation' if i == count-2 else 'test'
        task_id = f't{i:03d}'
        base = root/'tasks'/task_id
        task, reg = make_task(base, seed_start+i)
        task['task_id'] = task_id
        task['request_text'] = '受控合成工程验收；检查内容与旋转、镜像、裁切。'
        if i == count-1:
            task['limits']['max_comparisons_total'] = 1
        if count > 3 and i == count-3:
            (base/'images/test/007.png').write_text('deliberately malformed synthetic engineering image')
        write_json(base/'task.json', task)
        manifest = input_manifest(Registry(reg).dataset(task['dataset_ref']), task['limits'])
        files = [f for f in manifest['files'] if f['supported_image']]
        mapping = {}
        for f in files:
            stem = Path(f['path']).stem
            sid = f'{task_id}-{stem}'
            derived = stem in ('002', '003', '004', '005')
            mapping[f['path']] = sid
            catalog['sources'].append({'source_id': sid, 'source_group': f'procedural-{seed_start+i}',
                'entity_group': None, 'session_group': None, 'kind': 'derived_image' if derived else 'synthetic',
                'path': (base/'images'/f['path']).relative_to(root).as_posix(), 'sha256': f['sha256'],
                'uri': f'generator://catalog-acceptance/{seed_start+i}/{stem}',
                'license_identifier': 'self-generated', 'license_evidence_url': f'generator://catalog-acceptance/{seed_start+i}',
                'redistribution': 'allowed', 'acquired_at': now(), 'parents': [f'{task_id}-001'] if derived else [],
                'known_core_data': False})
        pairs = {tuple(sorted((a['path'], b['path']))) for a, b in itertools.combinations(files, 2) if a['image_split'] != b['image_split']}
        exact_names = {'train/001.png', 'test/002.png', 'validation/003.png'}
        origin_names = {*exact_names, 'test/004.png', 'validation/005.png'}
        exact = {p for p in pairs if set(p) <= exact_names}
        related = {p for p in pairs if set(p) <= origin_names}-exact
        def exhaustive(positive):
            return {'coverage': 'exhaustive', 'positive_pairs': [list(p) for p in sorted(positive)], 'negative_pairs': []}
        truth = {'schema_version': 1, 'task_id': task_id, 'dataset_manifest_digest': manifest['digest'],
            'goal': task['goal'], 'basis': {'kind': 'synthetic_generation',
                'description': f'Controlled procedural seed {seed_start+i}; exact copies/re-encoding, rotation/crop and independent random negative. No natural scene or human annotation.'},
            'exact': exhaustive(exact), 'related_excluding_exact': exhaustive(related),
            'entity_goal_conflict': exhaustive(set())}
        truth_path = root/'evaluator-truth'/f'{task_id}.json'
        write_json(truth_path, truth, exclusive=True)
        catalog['tasks'].append({'task_id': task_id, 'benchmark_partition': partition,
            'task_path': (base/'task.json').relative_to(root).as_posix(),
            'registry_path': (base/'registry.json').relative_to(root).as_posix(),
            'truth_path': truth_path.relative_to(root).as_posix(), 'image_sources': mapping})
    protocol = {'conditions': ['A', 'B', 'C', 'D'], 'repetitions': 1,
        'policy_digest': file_hash(PROJECT/'configs/policy.json'),
        'model_configuration': {'status': 'not_configured', 'provider': None, 'model_id': None, 'endpoint': None, 'prompt_digest': None},
        'metric_definition': METRIC_VERSION}
    write_json(root/'catalog.json', catalog, exclusive=True)
    write_json(root/'protocol.json', protocol, exclusive=True)
    write_json(root/'fixture-source.json', {'kind': 'synthetic controlled engineering only', 'seed_start': seed_start,
        'task_count': count, 'natural_independent_test': False, 'partition_meaning': 'Gate/executor exercise only; synthetic validation/test names are not a natural generalization experiment'}, exclusive=True)
    return catalog, protocol
