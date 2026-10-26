"""Reverify downloaded CI artifacts without modifying historical absolute-path registries."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from visionleak_investigator.common import read_json,file_hash,digest,write_json,now
from visionleak_investigator.core import CoreAdapter
from visionleak_investigator.domain import input_manifest
from visionleak_investigator.evaluation import comparable,resource_totals
from visionleak_investigator.reporting import ClaimValidator
from visionleak_investigator.workflow import code_digest

base=Path(__file__).resolve().parent;run=read_json(base/'github-run.json')
assert run['conclusion']=='success' and run['headSha']=='54df5312b2ce9754eab0f560e43f4fae951eac4d'
download=read_json(base/'download.json');results=[]
adapter=CoreAdapter();adapter.verify_artifacts()
for artifact in download['artifacts']:
    directory=base/artifact['platform']
    for entry in artifact['files']:assert file_hash(directory/entry['path'])==entry['sha256']
    suite=ET.parse(directory/'reports/ci/junit.xml').find('testsuite')
    assert {k:suite.attrib[k] for k in ('tests','failures','errors','skipped')}==dict(tests='102',failures='0',errors='0',skipped='0')
    commands=read_json(directory/'commands.json')
    assert len(commands)==7 and all(c['exit_code']==0 for c in commands)
    original=Path(commands[0]['cwd'])
    def relocate(value):return directory/Path(value).relative_to(original)
    checked=[]
    for path in sorted((directory/'runs').rglob('report.json')):
        audit=path.parent
        if not (audit/'validation.json').exists():continue
        report=read_json(path);validation=read_json(audit/'validation.json');manifest=read_json(audit/'manifest.json')
        assert read_json(audit/'checkpoint.json')['report_digest']==digest(report)
        assert validation['evidence_sha256']==file_hash(audit/'evidence.jsonl')
        assert digest(read_json(audit/'task.json'))==manifest['task_digest']
        registry=read_json(audit/'registry.private.json');assert digest(registry)==manifest['registry_digest']
        dataset=relocate(registry['datasets'][report['task']['dataset_ref']])
        assert input_manifest(dataset,report['task']['limits'])['digest']==manifest['dataset_manifest_digest']
        if 'model_ledger_sha256' in validation:assert validation['model_ledger_sha256']==file_hash(audit/'model-ledger.json')
        assert report['model_execution']=='not_run' and report['coverage']['source_unchanged']
        evidence={r['evidence_id']:r for r in map(json.loads,(audit/'evidence.jsonl').read_text().splitlines())}
        coverage={**report['coverage']['profiles'],'metadata':report['coverage']['metadata'],'human_review':report['coverage']['human_review']}
        for claim in report['claims']:ClaimValidator().validate_claim(claim,evidence,coverage)
        for profile,cov in report['coverage']['profiles'].items():
            raw=audit/cov['report_ref'];assert file_hash(raw)==cov['report_sha256']==validation['core_reports'][profile]
            adapter.inspect_report(raw,dataset)
        checked.append({'report':str(path.relative_to(directory)),'mode':report['mode'],'state':report['state']})
    assert len(checked)==12 and sum(r['mode']=='scripted_test_only' for r in checked)==2
    gate=directory/'runs/ci-evaluation-gates';receipt=read_json(gate/'receipt.json')
    assert receipt['status']=='passed' and receipt['model_calls']==0 and len(receipt['commands'])==9
    frozen=read_json(gate/'frozen.json');assert digest({k:v for k,v in frozen.items() if k!='freeze_digest'})==frozen['freeze_digest']==receipt['freeze_digest']
    assert frozen['code_digest']==code_digest()
    for c in receipt['commands']:
        result=read_json(gate/c['record']);assert result['exit_code']==c['exit_code'] and result['error'] is None
    assert sum(c['exit_code']==1 for c in receipt['commands'])==3
    for part in ('development','validation','test'):
        check=read_json(gate/f'checked-{part}.json')
        assert check['freeze_digest']==frozen['freeze_digest'] and check['independent_components']==1
    resources=directory/'runs/ci-resources';frozen=read_json(resources/'frozen_config.json')
    assert frozen['runtime_lock_digest']==file_hash(directory/'core.runtime.lock.json')
    assert frozen['code_digest']==code_digest()
    rows=list(map(json.loads,(resources/'per_run.jsonl').read_text().splitlines()))
    assert len(rows)==12
    assert resource_totals(rows)==read_json(resources/'metrics.json')['resources_by_condition']
    manifests={}
    for row in rows:
        if row['condition']=='D':assert row['state']=='blocked';continue
        assert row['state'] in ('COMPLETED','PARTIAL')
        record=read_json(resources/row['process_record']/'result.json')
        assert record['resources']==row['full_task_resources']
        assert record['resources']['cpu_seconds']>0 and record['resources']['tree_rss_status']=='sampled'
        assert record['resources']['tree_rss_peak_bytes']>0
        m=read_json(resources/row['run']/'manifest.json');t=read_json(resources/row['run']/'task.json')
        assert all(m[k]==frozen[k] for k in ('core_lock_digest','runtime_lock_digest','code_digest'))
        manifests.setdefault(row['task_id'],[]).append((m,t))
    for entries in manifests.values():comparable(entries)
    results.append({'platform':artifact['platform'],'tests':102,'skipped':0,'reports_reverified':checked,
                    'gate_cli_commands':9,'expected_rejections':3,'resource_measured_runs':9,
                    'runtime_lock_sha256':file_hash(directory/'core.runtime.lock.json')})
write_json(base/'verification.json',{'verified_at':now(),'status':'passed','tested_commit':run['headSha'],
    'ci_url':run['url'],'results':results,'model_calls':0,'method':__doc__},exclusive=True)
print(json.dumps({'status':'passed','platforms':2,'tests_per_platform':102,'reports_reverified':24,
                  'resource_measured_runs':18,'real_agent_experiment':'not_run'}))
