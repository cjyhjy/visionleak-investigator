"""T17: real Core followed by explicitly injected report truncation before acceptance."""
import argparse
import json
from pathlib import Path

from visionleak_investigator import workflow
from visionleak_investigator.common import digest, file_hash, read_json, write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.domain import Registry, input_manifest
from visionleak_investigator.integrity import verify_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    task, registry = make_task(out/'fixture', 77000)
    task['request_text'] = '受控合成故障注入：真实 Core 返回后截断输出报告，非生产事故、非模型实验。'
    write_json(out/'fixture/task.json', task)
    source = Registry(registry).dataset(task['dataset_ref'])
    before = input_manifest(source, task['limits'])
    real_execute = workflow.execute
    faults = []

    def execute_then_truncate(argv, cwd, directory, timeout):
        result = real_execute(argv, cwd, directory, timeout)
        if len(argv) > 2 and argv[2] == 'audit':
            assert result['exit_code'] == 0 and result['error'] is None
            raw_path = directory/'output/report.json'
            original = raw_path.read_bytes()
            # Preserve original bytes before corrupting only this newly generated fixture output.
            archive = directory/'controlled-fault/report-before-truncation.json'
            archive.parent.mkdir(exist_ok=False)
            archive.write_bytes(original)
            original_json = read_json(archive)
            assert original_json['complete'] and original_json['pairs']
            logs = {name: file_hash(directory/name) for name in ('invocation.json', 'stdout.log', 'stderr.log', 'result.json')}
            raw_path.write_bytes(original[:len(original)//2])
            fault = {'kind': 'controlled report truncation after real Core exit and before host acceptance',
                     'production_incident': False, 'original_report': str(archive.relative_to(out)),
                     'truncated_report': str(raw_path.relative_to(out)),
                     'original_sha256': file_hash(archive), 'truncated_sha256': file_hash(raw_path),
                     'original_bytes': len(original), 'truncated_bytes': raw_path.stat().st_size,
                     'original_audit_id': original_json['auditId'], 'original_exit_code': result['exit_code'],
                     'preserved_tool_logs': logs}
            write_json(directory/'controlled-fault/injection.json', fault, exclusive=True)
            faults.append(fault)
        return result

    workflow.execute = execute_then_truncate
    try:
        report = workflow.run_task(task, registry, out/'run', profiles=['base'])
    finally:
        workflow.execute = real_execute
    assert len(faults) == 1
    assert report['state'] == 'PARTIAL' and not report['coverage']['profiles']
    assert not report['claims'] and report['coverage']['source_unchanged']
    evidence = [json.loads(line) for line in (out/'run/evidence.jsonl').read_text().splitlines()]
    assert not any(e['kind'].startswith('core.') for e in evidence)
    ledger = read_json(out/'run/ledger.json')
    audits = [e for e in ledger['entries'] if e['kind'] == 'audit']
    assert len(audits) == 1 and audits[0]['status'] == 'unknown'
    assert audits[0]['actual'] == audits[0]['reservation']
    assert all(e['status'] != 'pending' for e in ledger['entries'])
    assert any(e['kind'] == 'finalize' and e['status'] == 'settled' for e in ledger['entries'])
    assert not read_json(out/'run/proposal.json')['proposed_exclusions']
    assert verify_run(out/'run', recompute_identity=True) == report
    assert input_manifest(source, task['limits']) == before
    fault = faults[0]
    directory = (out/fault['truncated_report']).parents[1]
    assert all(file_hash(directory/name) == sha for name, sha in fault['preserved_tool_logs'].items())
    assert file_hash(out/fault['original_report']) == fault['original_sha256']
    assert file_hash(out/fault['truncated_report']) == fault['truncated_sha256']
    receipt = {'status': 'passed', 'case': 'T17 half-written report acceptance',
               'faults': faults, 'host_state': report['state'], 'accepted_core_evidence': 0,
               'accepted_claims': 0, 'audit_charge': audits[0], 'finalization': 'settled',
               'input_manifest_digest': before['digest'], 'source_unchanged': True,
               'manifest_digest': digest(read_json(out/'run/manifest.json')),
               'code_digest': workflow.code_digest(), 'model_calls': 0,
               'real_agent_experiment': 'not_run',
               'scope': 'controlled synthetic fault injection around a real Core process; detector unchanged'}
    write_json(out/'receipt.json', receipt, exclusive=True)
    print(json.dumps({'status': 'passed', 'host_state': report['state'], 'model_calls': 0}))


if __name__ == '__main__': main()
