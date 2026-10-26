import subprocess
import sys

from visionleak_investigator.common import PROJECT, file_hash, read_json
from visionleak_investigator.integrity import verify_run


def test_T17_half_written_real_report_is_preserved_but_not_accepted(tmp_path):
    out = tmp_path/'partial-report'
    result = subprocess.run([sys.executable, str(PROJECT/'scripts/partial_report_smoke.py'),
                             '--out', str(out)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    receipt = read_json(out/'receipt.json')
    assert receipt['status'] == 'passed' and receipt['model_calls'] == 0
    report = verify_run(out/'run')
    assert report['state'] == 'PARTIAL' and not report['claims']
    assert not report['coverage']['profiles']
    assert receipt['audit_charge']['status'] == 'unknown'
    assert receipt['audit_charge']['actual'] == receipt['audit_charge']['reservation']
    fault = receipt['faults'][0]
    assert fault['original_exit_code'] == 0 and not fault['production_incident']
    assert read_json(out/fault['original_report'])['complete']
    assert file_hash(out/fault['truncated_report']) == fault['truncated_sha256']
    assert fault['truncated_bytes'] == fault['original_bytes']//2
