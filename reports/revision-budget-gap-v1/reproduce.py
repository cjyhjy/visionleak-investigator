"""Observe real Core inspection during a budget-denied host revision; no model."""
from pathlib import Path
import time
from visionleak_investigator.common import read_json,write_json,file_hash,digest
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task,code_digest
from visionleak_investigator.interaction import resume_run
from visionleak_investigator.core import CoreAdapter
from visionleak_investigator.domain import Registry,input_manifest
from visionleak_investigator.budget import BudgetExceeded

base=Path(__file__).resolve().parent
task,registry=make_task(base/'fixture',seed=83301)
task['limits']['max_tool_calls']=6
run=base/'run';report=run_task(task,registry,run,profiles=['base'])
before=file_hash(run/'ledger.json');source=input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
calls=[];original=CoreAdapter.inspect_report
def observe(self,*args,**kwargs):
    started=time.monotonic()
    try:return original(self,*args,**kwargs)
    finally:calls.append({'report':str(args[0]),'wall_seconds':time.monotonic()-started,'real_core':True})
CoreAdapter.inspect_report=observe
error=None
try:resume_run(run,{'actor':'scripted budget-boundary acceptance; no human participant','goal':'same_entity_new_view'})
except BudgetExceeded as exc:error=str(exc)
finally:CoreAdapter.inspect_report=original
assert error and calls and before==file_hash(run/'ledger.json')
assert source==input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
receipt={'status':'gap_reproduced','code_digest':code_digest(),'model_calls':0,'initial_tool_calls':report['budget']['spent']['tool_calls'],
         'max_tool_calls':task['limits']['max_tool_calls'],'error':error,'unbudgeted_core_identity_calls':calls,
         'original_ledger_unchanged':True,'source_unchanged':True,
         'scope':'Real Core on generated images. Wrapper only observes and forwards the original inspection. Host revision denied after real identity work; not a model or human experiment.'}
write_json(base/'receipt.json',receipt,exclusive=True)
print({'status':receipt['status'],'unbudgeted_core_identity_calls':len(calls)})
