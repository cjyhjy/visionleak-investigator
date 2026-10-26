"""Verify downloaded real CI evidence; this is not a new audit experiment."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root/'src'))
from visionleak_investigator.common import read_json,file_hash,digest,write_json,now
from visionleak_investigator.core import CoreAdapter

base=Path(__file__).resolve().parent
run=read_json(base/'github-run.json');assert run['conclusion']=='success'
rows=[]
for platform in ('ubuntu-24.04','macos-14'):
    directory=base/platform
    suite=ET.parse(directory/'checks/junit.xml').find('testsuite')
    assert suite.attrib['tests']=='77' and suite.attrib['failures']=='0' and suite.attrib['errors']=='0'
    commands=[json.loads(line) for line in (directory/'commands.jsonl').read_text().splitlines()]
    assert all(c['exit_code']==0 for c in commands)
    checked=[]
    for path in sorted(directory.rglob('report.json')):
        audit=path.parent
        if not (audit/'validation.json').exists():continue
        report=read_json(path);validation=read_json(audit/'validation.json')
        assert read_json(audit/'checkpoint.json')['report_digest']==digest(report)
        assert validation['evidence_sha256']==file_hash(audit/'evidence.jsonl')
        if 'model_ledger_sha256' in validation:
            assert validation['model_ledger_sha256']==file_hash(audit/'model-ledger.json')
        assert report['model_execution']=='not_run' and report['coverage']['source_unchanged']
        for cov in report['coverage']['profiles'].values():
            raw=audit/cov['report_ref'];assert file_hash(raw)==cov['report_sha256']
            CoreAdapter().inspect_report(raw,(audit.parent/'fixture/images').resolve())
        checked.append({'report':str(path.relative_to(directory)),'mode':report['mode'],'state':report['state']})
    assert len(checked)==3
    assert sum(r['mode']=='scripted_test_only' for r in checked)==2
    rows.append({'platform':platform,'tests':77,'reports_reverified':checked,
                 'runtime_lock_sha256':file_hash(directory/'core.runtime.lock.json')})
receipt={'verified_at':now(),'tested_commit':run['headSha'],'ci_url':run['url'],
         'results':rows,'real_agent_experiment':'not_run','method':__doc__}
write_json(base/'verification.json',receipt)
print(json.dumps(receipt,ensure_ascii=False))
