"""Export verified, read-only suggestions; text cells use a literal, reversible prefix."""
from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path

from .common import digest, file_hash, no_symlink, now, write_json
from .integrity import verify_run
from .metadata import proposal
from .plan_check import _output_path, verified_plan_context
from .workflow import code_digest

TEXT_ENCODING = 'text: followed by a JSON string; decode only as data, never as a formula'


def text_cell(value: str) -> str:
    # A fixed non-formula prefix survives CSV quote removal and spreadsheet re-saving.
    # JSON escaping keeps controls and Unicode direction/width tricks literal.
    return 'text:' + json.dumps(value, ensure_ascii=True)


def suggestion_csv(value: dict, report: dict, report_digest: str) -> str:
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writerow(['path', 'image_split', 'old_included', 'proposed_included', 'reason',
                     'evidence_refs_json', 'source_manifest_digest', 'audit_report_digest',
                     'audit_state', 'image_reaudit', 'requires_approval', 'text_encoding'])
    exclusions = {r['path']: r['evidence_refs'] for r in value['proposed_exclusions']}
    for row in value['new_manifest']:
        refs = exclusions.get(row['path'], [])
        reason = ('Suggested exclusion based on known exact or declared entity evidence; review balance before applying.'
                  if refs else 'Retain original file in its original split.')
        writer.writerow([text_cell(row['path']), text_cell(row['image_split']), 'true',
                         'true' if row['included'] else 'false', text_cell(reason),
                         text_cell(json.dumps(refs, ensure_ascii=True)),
                         text_cell(value['source_manifest_digest']), text_cell(report_digest),
                         text_cell(report['state']), 'not_run', 'true', 'text-json-v1'])
    return stream.getvalue()


def export_proposal(run: Path, out: Path, *, format: str = 'json') -> dict:
    if format not in ('json', 'csv'):
        raise ValueError('Proposal export format must be json or csv')
    started = time.monotonic(); run = no_symlink(run)
    report, manifest, source, task, registry, evidence = verified_plan_context(run)
    if not report['coverage']['profiles']:
        raise ValueError('No accepted image audit; no actionable proposal export')
    destination = _output_path(out, run, registry, run/'proposal.json')
    # Recompute from accepted witnesses, never trust an editable old proposal.json.
    suggestion = proposal(task, evidence, source)
    binding = {'source_manifest_digest': source['digest'], 'audit_manifest_digest': digest(manifest),
               'audit_report_digest': digest(report), 'evidence_sha256': file_hash(run/'evidence.jsonl'),
               'processor_code_digest': code_digest()}
    value = {**suggestion, 'schema_version': 1, 'created_at': now(), 'provenance': binding,
             'audit_state': report['state'], 'audit_coverage': report['coverage'],
             'image_reaudit': 'not_run', 'source_files_modified': False}
    text = suggestion_csv(value, report, binding['audit_report_digest']) if format == 'csv' else None
    if verify_run(run) != report:
        raise ValueError('Audit changed during proposal export')
    if format == 'csv':
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8', newline='') as output:
            output.write(text)
    else:
        write_json(destination, value, exclusive=True)
    return {'status': 'exported_suggestion_only', 'format': format, 'output': str(destination),
            'sha256': file_hash(destination), 'rows': len(suggestion['new_manifest']), **binding,
            'requires_approval': True, 'image_reaudit': 'not_run', 'source_files_modified': False,
            'text_encoding': TEXT_ENCODING if format == 'csv' else None,
            'audit_state': report['state'], 'known_conflicts_remaining': suggestion['plan_check']['known_conflicts_remaining'],
            'limitations': suggestion['limitations'] + ['CSV is a presentation export, not a Core or training manifest.',
                'Partial audit coverage remains partial; exporting is not approval or a new image audit.'],
            'execution': {'wall_seconds': time.monotonic()-started, 'core_audit_runs': 0, 'model_calls': 0,
                          'accounting': 'standalone export; original audit ledger unchanged'}}
