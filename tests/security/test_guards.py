import copy,json,sys
from pathlib import Path
import pytest
from visionleak_investigator.common import read_json,PROJECT,safe_child
from visionleak_investigator.workflow import ActionGuard,action,run_task
from visionleak_investigator.domain import TaskSpec,AgentAction,Registry
from visionleak_investigator.budget import BudgetLedger,BudgetExceeded
from visionleak_investigator.core import execute,CoreAdapter
from visionleak_investigator.demo import make_task
from visionleak_investigator.reporting import ClaimValidator,render_report

def limits():return read_json(PROJECT/'examples/task.example.json')['limits']

def test_T13_T14_T16_action_schema_refs_repeat():
    a=action('base');a['parameters']['shell']='rm -rf /'
    with pytest.raises(ValueError):AgentAction.parse(a)
    a=action('base');a['evidence_refs']=['fake']
    with pytest.raises(ValueError):ActionGuard(set(),[]).check(a)
    with pytest.raises(ValueError):ActionGuard(set(),['base']).check(action('base'))
    with pytest.raises(ValueError):ActionGuard(set(),[]).check(action('all'))
    a=action('base');a['action_type']='shell'
    with pytest.raises(ValueError):AgentAction.parse(a)

def test_T17_T26_T31_unknown_failure_and_reserve(tmp_path):
    l=limits();l['max_tool_calls']=3
    b=BudgetLedger(l,tmp_path/'ledger.json');e=b.reserve('audit',{'comparisons':7,'decoded_pixels':123,'index_operations':112})
    b.settle(e,None,error='timeout')
    assert b.data['spent']['comparisons']==7 and b.data['spent']['decoded_pixels']==123
    with pytest.raises(BudgetExceeded):b.reserve('audit')
    with pytest.raises(ValueError):b.settle(e,{'comparisons':0})
    # Pending state is persisted before subprocess; recovery cannot issue free retries.
    b=BudgetLedger(l,tmp_path/'other.json');b.reserve('verify',{'decoded_pixels':40},final=True)
    restarted=BudgetLedger(l,tmp_path/'other.json',read_json(tmp_path/'other.json'));restarted.recover_pending()
    assert restarted.data['spent']['decoded_pixels']==40

def test_T17_actual_process_timeout(tmp_path):
    result=execute([sys.executable,'-c','import time;time.sleep(20)'],tmp_path,tmp_path/'tool',0.1)
    assert result['error']=='timeout' and result['wall_seconds']<3
    assert (tmp_path/'tool/invocation.json').exists() and (tmp_path/'tool/stderr.log').exists()

@pytest.mark.parametrize('path',['../secret','/tmp/key','test/../../a','test//a','test/./a','test\\a'])
def test_T18_path_rejection(tmp_path,path):
    with pytest.raises(ValueError):safe_child(tmp_path,path)

def test_T19_html_and_T33_claim_entailment(tmp_path):
    task,registry=make_task(tmp_path/'fixture');task['request_text']='<script>alert(1)</script>'
    r=run_task(task,registry,tmp_path/'run',profiles=['base','all'])
    assert r['state']=='COMPLETED',r['issues']
    html=(tmp_path/'run/report.html').read_text();assert '<script>' not in html and '&lt;script&gt;' in html
    evidence=[json.loads(s) for s in (tmp_path/'run/evidence.jsonl').read_text().splitlines()]
    candidate=next(e for e in evidence if 'candidate' in e['kind'])
    with pytest.raises(ValueError):ClaimValidator().build('pixel_identity',[candidate],'base')
    claim=copy.deepcopy(r['claims'][0]);claim['statement']='Model has trained on this image'
    with pytest.raises(ValueError):ClaimValidator().validate_claim(claim,{e['evidence_id']:e for e in evidence},r['coverage']['profiles'])

def test_confirmation_is_host_bound(tmp_path):
    t,reg=make_task(tmp_path/'fixture');reg['confirmations']={}
    with pytest.raises(ValueError):run_task(t,reg,tmp_path/'run')

def test_T34_artifact_mismatch(tmp_path):
    (tmp_path/'dist').mkdir();(tmp_path/'dist/visionleak.js').write_text('changed')
    with pytest.raises(ValueError,match='digest'):CoreAdapter(tmp_path).verify_artifacts()

def test_T12_evidence_and_input_tampering(tmp_path):
    from visionleak_investigator.integrity import verify_run
    t,reg=make_task(tmp_path/'fixture');run=tmp_path/'run';run_task(t,reg,run)
    assert verify_run(run)['state']=='COMPLETED'
    path=tmp_path/'fixture/images/train/001.png';path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='Input changed'):verify_run(run)
    with (run/'evidence.jsonl').open('a') as f:f.write('{}\n')
    with pytest.raises(ValueError,match='tampered'):verify_run(run,check_input=False)
