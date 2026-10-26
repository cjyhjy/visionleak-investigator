"""Measure controlled second-render latency omitted from the finalization ledger."""
from pathlib import Path
import time
from visionleak_investigator import workflow
from visionleak_investigator.common import write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run

base=Path(__file__).resolve().parent;task,registry=make_task(base/'fixture',seed=83320)
original=workflow.render_report;observations=[]
def render(report,*args,**kwargs):
    started=time.monotonic()
    delay=.3 if observations else 0
    if delay:time.sleep(delay)
    result=original(report,*args,**kwargs)
    observations.append({'render_number':len(observations)+1,'wall_seconds':time.monotonic()-started,'injected_latency_seconds':delay,'real_renderer':True})
    return result
workflow.render_report=render
try:report=workflow.run_task(task,registry,base/'run',profiles=['base'])
finally:workflow.render_report=original
assert verify_run(base/'run',recompute_identity=True)==report
final=next(e for e in report['budget']['entries'] if e['kind']=='finalize')
measured=sum(o['wall_seconds'] for o in observations)
assert len(observations)==2 and measured-final['actual']['wall_seconds']>.2
write_json(base/'receipt.json',{'status':'gap_reproduced','code_digest':workflow.code_digest(),
    'render_calls':observations,'finalization_entry':final,'measured_render_wall_seconds':measured,
    'unaccounted_render_lower_bound_seconds':measured-final['actual']['wall_seconds'],
    'source_unchanged':report['coverage']['source_unchanged'],'model_calls':0,
    'scope':'Real Core and renderer on generated data. Controlled 0.3-second latency in the second render demonstrates accounting scope, not production latency or a model experiment.'},exclusive=True)
print({'status':'gap_reproduced','unaccounted_render_lower_bound_seconds':measured-final['actual']['wall_seconds']})
