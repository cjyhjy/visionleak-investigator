"""Fresh-fixture acceptance with real Core, no model/provider/replayed results."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from visionleak_investigator.common import write_json, file_hash, PROJECT
from visionleak_investigator.core import CoreAdapter
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task
from visionleak_investigator.integrity import verify_run

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
environment = CoreAdapter().doctor()
task, registry = make_task(out / 'fixture')
report = run_task(task, registry, out / 'audit', profiles=['base', 'all'])
if report['state'] != 'COMPLETED' or report['model_execution'] != 'not_run':
    raise SystemExit('Fresh real-Core audit did not complete as a no-model run')
verify_run(out / 'audit', recompute_identity=True)
write_json(out / 'receipt.json', {
    'status': 'passed', 'environment': environment, 'model_calls': 0,
    'data_kind': 'self-generated controlled fixtures', 'core_profiles': ['base', 'all'],
    'runtime_lock_sha256': file_hash(PROJECT / 'core.runtime.lock.json'),
    'source_unchanged': report['coverage']['source_unchanged'],
    'claim_count': len(report['claims']), 'report': 'audit/report.html',
}, exclusive=True)
print(out / 'receipt.json')
