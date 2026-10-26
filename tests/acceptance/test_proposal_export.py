import csv
import io
import json
import subprocess
import sys

import pytest

from visionleak_investigator.common import read_json, write_json, file_hash
from visionleak_investigator.demo import make_task
from visionleak_investigator.proposal_export import export_proposal, text_cell
from visionleak_investigator.workflow import run_task


def decode(value):
    assert value.startswith('text:')
    return json.loads(value[5:])


def test_T19_text_encoding_preserves_data_without_formula_or_row_injection():
    examples = ['=1+2', '+SUM(1,2)', '-2+3', '@SUM(1,2)', '\t=1+2', '\r=1+2', '\n=1+2',
                '＝1+2', '＋1', '－1', '＠SUM(1)', '\ufeff =1+2', '  =1+2',
                '";=1+2,\n=1+2', '训练/图像.png', 'text:"already prefixed"', "'a"]
    stream = io.StringIO(newline=''); csv.writer(stream, quoting=csv.QUOTE_ALL).writerow(map(text_cell, examples))
    parsed = list(csv.reader(io.StringIO(stream.getvalue())))
    assert len(parsed) == 1 and len(parsed[0]) == len(examples)
    assert [decode(cell) for cell in parsed[0]] == examples
    assert all(cell.startswith('text:') and '\n' not in cell and '\r' not in cell for cell in parsed[0])
    # A standard CSV parse/save cycle preserves the literal prefix, unlike relying only on quotes.
    again = io.StringIO(newline=''); csv.writer(again).writerows(parsed)
    assert list(csv.reader(io.StringIO(again.getvalue()))) == parsed


def test_real_suggestion_exports_bind_evidence_and_preserve_input(tmp_path):
    task, registry = make_task(tmp_path/'fixture'); run = tmp_path/'run'; run_task(task, registry, run)
    hashes = {str(p): file_hash(p) for base in (run, tmp_path/'fixture') for p in base.rglob('*') if p.is_file()}
    jr = export_proposal(run, tmp_path/'suggestion.json')
    cr = export_proposal(run, tmp_path/'suggestion.csv', format='csv')
    value = read_json(tmp_path/'suggestion.json')
    rows = list(csv.DictReader((tmp_path/'suggestion.csv').open(newline='')))
    assert len(rows) == cr['rows'] == jr['rows'] == 6
    assert [{'path': decode(r['path']), 'image_split': decode(r['image_split']), 'included': r['proposed_included']=='true'} for r in rows] == value['new_manifest']
    assert all(r['proposed_included']=='true' for r in rows if decode(r['image_split'])=='test')
    assert any(json.loads(decode(r['evidence_refs_json'])) for r in rows)
    assert all(decode(r['audit_report_digest'])==cr['audit_report_digest'] for r in rows)
    assert value['plan_check']['known_conflicts_remaining']
    assert cr['execution']['core_audit_runs'] == 0 and cr['requires_approval']
    assert all(file_hash(__import__('pathlib').Path(p))==sha for p,sha in hashes.items())


def test_export_recomputes_suggestions_and_refuses_protected_or_existing_output(tmp_path):
    task, registry = make_task(tmp_path/'fixture'); run = tmp_path/'run'; run_task(task, registry, run)
    # proposal.json is a convenience artifact; a modified copy cannot control regenerated exports.
    old = read_json(run/'proposal.json'); modified = {**old, 'new_manifest': []}
    write_json(run/'proposal.json', modified)
    out = tmp_path/'fresh.json'; export_proposal(run, out)
    assert read_json(out)['new_manifest'] == old['new_manifest']
    for path in (out, run/'new.csv', tmp_path/'fixture/images/new.csv'):
        with pytest.raises(ValueError): export_proposal(run, path, format='csv')
    (tmp_path/'link').symlink_to(tmp_path/'fixture/images', target_is_directory=True)
    with pytest.raises(ValueError): export_proposal(run, tmp_path/'link/new.csv', format='csv')
    (tmp_path/'fixture/images/test/002.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Input changed'): export_proposal(run, tmp_path/'changed.csv', format='csv')


def test_proposal_export_cli_and_partial_scope(tmp_path):
    task, registry = make_task(tmp_path/'fixture'); task['limits']['max_comparisons_total'] = 1
    run = tmp_path/'run'; report = run_task(task, registry, run)
    assert report['state'] == 'PARTIAL'
    result = subprocess.run([sys.executable, '-m', 'visionleak_investigator.cli', 'proposal-export',
        '--run', str(run), '--out', str(tmp_path/'partial.csv'), '--format', 'csv'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['audit_state'] == 'PARTIAL' and receipt['image_reaudit'] == 'not_run'
    assert receipt['status'] == 'exported_suggestion_only'


def test_recovered_unaccepted_outputs_cannot_be_exported_as_suggestions(tmp_path):
    from visionleak_investigator.recovery import recover_interrupted
    task, registry = make_task(tmp_path/'fixture'); run = tmp_path/'run'; run_task(task, registry, run)
    (run/'report.json').unlink()  # Controlled newly generated interruption fixture only.
    recover_interrupted(run)
    with pytest.raises(ValueError, match='No accepted image audit'):
        export_proposal(run, tmp_path/'unaccepted.csv', format='csv')
    assert not (tmp_path/'unaccepted.csv').exists()
