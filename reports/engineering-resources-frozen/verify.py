"""Recheck actual saved runs and raw resource receipts; does not rerun the experiments."""
import json
from pathlib import Path
from visionleak_investigator.common import read_json,write_json,now
from visionleak_investigator.evaluation import resource_totals,check_execution,comparable
from visionleak_investigator.integrity import verify_run

base=Path(__file__).resolve().parent
frozen=read_json(base/'frozen_config.json');check_execution(frozen,base)
rows=[json.loads(line) for line in (base/'per_run.jsonl').read_text().splitlines()]
metrics=read_json(base/'metrics.json');assert len(rows)==48
assert resource_totals(rows)==metrics['resources_by_condition']
manifests={};checked=[]
for row in rows:
    if row['condition']=='D':
        assert row['state']=='blocked';continue
    run=base/row['run'];report=verify_run(run,recompute_identity=True)
    manifest=read_json(run/'manifest.json');check_execution(frozen,base,manifest)
    manifests.setdefault(row['task_id'],[]).append((manifest,report['task']))
    result=read_json(base/row['process_record']/'result.json')
    assert row['full_task_resources']==result['resources']
    assert row['full_task_wall_seconds']==result['wall_seconds']
    assert result['resources']['cpu_seconds']>0
    assert result['resources']['tree_rss_status']=='sampled'
    assert result['resources']['tree_rss_peak_bytes']>0
    assert report['state']==row['state'] and report['model_execution']=='not_run'
    checked.append({'task':row['task_id'],'condition':row['condition'],'state':row['state']})
for entries in manifests.values():comparable(entries)
write_json(base/'verification.json',{'verified_at':now(),'status':'passed',
    'source_code_digest':frozen['code_digest'],'runs':checked,'model_calls':0,
    'method':__doc__},exclusive=True)
print(json.dumps({'status':'passed','runs_reverified':len(checked),'blocked_D':12,'real_agent_experiment':'not_run'}))
