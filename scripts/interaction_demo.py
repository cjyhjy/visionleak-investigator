"""A scripted USER-answer fixture, never a simulated model Agent experiment."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from visionleak_investigator.common import PROJECT,write_json,file_hash
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task
from visionleak_investigator.interaction import resume_run
base=PROJECT/'reports/interaction-demo';base.mkdir(exist_ok=False)
task,registry=make_task(base/'fixture')
task.update(goal='unspecified',goal_confirmed=False,goal_evidence_refs=[],metadata_ref='samples',entity_key='entity_id',entity_key_confirmed=False,entity_key_evidence_refs=[])
p=base/'fixture/samples.csv';p.write_text('file_id,relative_path,image_split,entity_id,provenance_ref\na,train/001.png,train,e1,controlled-generator\nb,test/002.png,test,e1,controlled-generator\n')
registry['documents']['samples']={'path':str(p.resolve()),'sha256':file_hash(p)}
write_json(base/'fixture/task.json',task);write_json(base/'fixture/registry.json',registry)
first=run_task(task,registry,base/'run');assert first['state']=='WAITING_USER'
answers={'actor':'controlled demo scripted user (not a real participant)','goal':'new_entity_generalization','entity_key':'entity_id'}
write_json(base/'answers.json',answers,exclusive=True)
next=resume_run(base/'run',answers);assert any(c['claim_type']=='goal_conflict' for c in next['claims'])
receipt={'status':'passed','before':first['state'],'after':next['state'],'answer_kind':'scripted user fixture','model_execution':'not_run','audit_runs_before':first['budget']['spent']['audit_runs'],'audit_runs_after':next['budget']['spent']['audit_runs'],'revision':next['revision']['path'],'remaining_issue':'metadata covers 2 of 6 images, so PARTIAL is expected'}
write_json(base/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt,ensure_ascii=False))
