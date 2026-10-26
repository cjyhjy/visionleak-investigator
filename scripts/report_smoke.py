"""Fresh real-Core reports for visual acceptance; scripted user inputs are labelled."""
import argparse
from pathlib import Path
import json
from visionleak_investigator.common import write_json,file_hash
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task
from visionleak_investigator.interaction import resume_run,import_review
from visionleak_investigator.integrity import verify_run

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args();root=args.out.resolve();root.mkdir(parents=True,exist_ok=False)
rows=[]
for case in ('complete','partial','clarification'):
    task,registry=make_task(root/case/'fixture',72000)
    task['request_text']='受控合成演示；用户回答和复核均为脚本输入，无真人参与。请检查图像内容，不修改原始图片。'
    if case=='partial':task['limits']['max_comparisons_total']=1
    if case=='clarification':task.update(goal='unspecified',goal_confirmed=False,goal_evidence_refs=[])
    write_json(root/case/'fixture/task.json',task)
    run=root/case/'run';result=run_task(task,registry,run,profiles=['base','all'] if case=='complete' else ['base'])
    assert result['state']=={'complete':'COMPLETED','partial':'PARTIAL','clarification':'WAITING_USER'}[case]
    verify_run(run,recompute_identity=True)
    rows.append({'case':case,'state':result['state'],'report':str((run/'report.html').relative_to(root)),
                 'sha256':file_hash(run/'report.html'),'audit_runs':result['budget']['spent']['audit_runs']})
    if case=='clarification':
        answers={'actor':'controlled scripted user fixture, not a real participant','goal':'content_audit'}
        write_json(root/'answers.json',answers,exclusive=True)
        revised=resume_run(run,answers);target=Path(revised['revision']['path'])
        verify_run(target,recompute_identity=True)
        assert revised['budget']['spent']['audit_runs']==result['budget']['spent']['audit_runs']
        rows.append({'case':'goal_revision','state':revised['state'],'report':str((target/'report.html').relative_to(root)),
                     'sha256':file_hash(target/'report.html'),'core_reexecuted':False})
    if case=='complete':
        candidate=result['reviews'][0]
        review={'reviewer':'controlled scripted reviewer fixture, not a real participant',
                'created_at':'2026-10-26T20:00:00+00:00','dataset_manifest_digest':result['coverage']['input_manifest_digest'],
                'audit_id':candidate['audit_id'],'pair_ref':candidate['pair_ref'],'decision':'unsure',
                'reason':'Presentation acceptance only; no human time-saving or source confirmation claim'}
        write_json(root/'review.json',review,exclusive=True)
        revised=import_review(run,review);target=Path(revised['revision']['path'])
        verify_run(target,recompute_identity=True)
        rows.append({'case':'review_revision','state':revised['state'],'report':str((target/'report.html').relative_to(root)),
                     'sha256':file_hash(target/'report.html'),'core_reexecuted':False})
receipt={'status':'passed','model_calls':0,'real_agent_experiment':'not_run',
         'data_kind':'self-generated controlled fixtures','human_inputs':'scripted fixtures, not real participants',
         'cases':rows,'visual_acceptance':'pending separate browser inspection'}
write_json(root/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt))
