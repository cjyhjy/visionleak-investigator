"""Controlled synthetic review revisions to inspect contract gaps; no human/model experiment."""
from pathlib import Path
from visionleak_investigator.common import read_json,write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task,code_digest
from visionleak_investigator.interaction import import_review,resume_run
base=Path(__file__).resolve().parent
task,registry=make_task(base/'fixture',80000);task['limits']['max_tool_calls']=32
write_json(base/'fixture/task.json',task)
run=base/'run';initial=run_task(task,registry,run,profiles=['base','all']);candidate=initial['reviews'][0]
payload={'reviewer':'controlled scripted reviewer, not a human participant','created_at':'2026-10-26T21:00:00+00:00','dataset_manifest_digest':initial['coverage']['input_manifest_digest'],'audit_id':candidate['audit_id'],'pair_ref':candidate['pair_ref'],'decision':'confirmed','reason':'Controlled review lifecycle fixture, no real annotation claim'}
confirmed=import_review(run,payload)
rejected=import_review(run,{**payload,'decision':'rejected','created_at':'2026-10-26T21:01:00+00:00'})
revised=resume_run(run,{'actor':'controlled scripted goal answer','goal':'content_audit'})
root=Path(revised['revision']['path'])
import json
human=[e for e in map(json.loads,(root/'evidence.jsonl').read_text().splitlines()) if e['kind'].startswith('human.')]
gaps={'coverage_still_not_run_after_confirmation':confirmed['coverage']['human_review']['state']=='not_run',
      'rejected_review_retains_confirmed_same_source_claim':any(c['claim_type']=='same_source_review' and c['status']=='confirmed' for c in rejected['claims']),
      'goal_revision_has_missing_review_source_positions':[s for e in human for s in e['source_positions'] if not (root/s).is_file()]}
assert gaps['coverage_still_not_run_after_confirmation'] and gaps['rejected_review_retains_confirmed_same_source_claim'] and gaps['goal_revision_has_missing_review_source_positions']
receipt={'status':'gap_reproduced','code_digest':code_digest(),'gaps':gaps,'model_calls':0,'human_participants':0,'original_core_modified':False,'runs':{'initial':str(run),'confirmed':confirmed['revision']['path'],'rejected':rejected['revision']['path'],'goal_revision':revised['revision']['path']},'next_required_work':'Synchronize review coverage, supersede outdated human conclusions, preserve review payload provenance through revisions.'}
write_json(base/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt,ensure_ascii=False))
