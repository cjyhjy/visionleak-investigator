"""SCRIPTED_TEST_ONLY: real host/Core/optional SDK; no model or Agent experiment."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from visionleak_investigator.common import write_json
from visionleak_investigator.controller import PlannerReply
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.workflow import run_scripted_task


def blocked(*args, **kwargs):
    raise RuntimeError('Network disabled in scripted controller smoke')


socket.socket.connect = blocked
socket.create_connection = blocked
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--sdk', action='store_true')
args = parser.parse_args()
root = args.out.resolve()
root.mkdir(parents=True, exist_ok=False)


def response(kind, **parameters):
    return PlannerReply(json.dumps({'action_type': kind, 'reason': 'SCRIPTED_TEST_ONLY',
                                   'evidence_refs': [], 'parameters': parameters}))


def additional(payload):
    if 'all' not in payload['observation']['profiles']:
        return response('run_audit', profile='all')
    return response('finalize', reason_code='supported_scope_exhausted')


rows = []
for scenario in ('additional_evidence', 'clarification'):
    task, registry = make_task(root/scenario/'fixture')
    if scenario == 'clarification':
        task.update(goal='unspecified', goal_confirmed=False, goal_evidence_refs=[])
        request = lambda _: response('request_clarification', question_code='clarify_goal', question='请确认实验目标。')
    else:
        request = additional
    out = root/scenario/'run'
    result = run_scripted_task(task, registry, out, request=request, use_sdk=args.sdk)
    expected = 'COMPLETED' if scenario == 'additional_evidence' else 'WAITING_USER'
    if result['state'] != expected:
        raise RuntimeError(f'Scripted scenario failed: {scenario}: {result["issues"]}')
    verify_run(out, recompute_identity=True)
    rows.append({'scenario': scenario, 'state': result['state'], 'run': str(out.relative_to(root)),
                 'audit_runs': result['budget']['spent']['audit_runs'],
                 'planner_requests': result['planning']['accounting']['requests_reserved']})
receipt = {'status': 'passed', 'execution_label': 'scripted_test_only', 'real_agent_experiment': 'not_run',
           'model_calls': 0, 'network': 'in-process connect blocked; no provider configured',
           'sdk': version('openjiuwen') if args.sdk else 'not_used',
           'real_core': True, 'cases': rows}
write_json(root/'receipt.json', receipt, exclusive=True)
print(json.dumps(receipt, ensure_ascii=False))
