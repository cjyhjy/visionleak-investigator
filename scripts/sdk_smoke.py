import sys,socket,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
# This test forbids network connects in-process. The SDK receives only a logical action.
def blocked(*args,**kwargs):raise RuntimeError('Network disabled in SDK smoke')
socket.socket.connect=blocked;socket.create_connection=blocked
from visionleak_investigator.common import PROJECT,write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import ActionGuard,action,run_task
from visionleak_investigator.openjiuwen_runtime import run_guarded_workflow
from importlib.metadata import version
base=PROJECT/'reports/sdk-smoke';base.mkdir(exist_ok=False)
task,registry=make_task(base/'fixture')
def dispatch(a):
 ActionGuard(set(),[]).check(a)
 if a['action_type']!='run_audit' or a['parameters']['profile']!='base':raise ValueError('Only registered smoke task allowed')
 result=run_task(task,registry,base/'run')
 return {'state':result['state'],'model_execution':result['model_execution']}
value=run_guarded_workflow(action('base'),dispatch)
assert value['state']=='COMPLETED',value
receipt={'status':'passed','sdk':version('openjiuwen'),'python':sys.version,'workflow':value,'model_execution':'not_run','network':'in-process connect blocked','real_core':True}
write_json(base/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt))
