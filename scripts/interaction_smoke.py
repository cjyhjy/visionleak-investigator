"""Run a separate frozen synthetic interaction benchmark with real Core and scripted answers."""
import argparse
import copy
import json
from pathlib import Path
import sys

from visionleak_investigator.common import PROJECT, digest, read_json, write_json
from visionleak_investigator.core import execute
from visionleak_investigator.evaluation_data import freeze_catalog
from visionleak_investigator.interaction_fixture import make_interaction_suite
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.domain import Registry, input_manifest
from visionleak_investigator.interaction_scoring import score_interaction
from visionleak_investigator.workflow import code_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=False)
    catalog,protocol=make_interaction_suite(out/'suite')
    frozen=out/'frozen.json';freeze_catalog(catalog,out/'suite',protocol,frozen)
    commands=[];rows=[]
    for partition in ('development','validation','test'):
        args=[sys.executable,'-m','visionleak_investigator.cli','eval-interaction','--catalog',str(out/'suite/catalog.json'),
              '--root',str(out/'suite'),'--protocol',str(out/'suite/protocol.json'),'--frozen',str(frozen),
              '--partition',partition,'--out',str(out/'results'/partition)]
        result=execute(args,PROJECT,out/'commands'/partition,300)
        assert result['exit_code']==0 and result['error'] is None
        metrics=read_json(out/'results'/partition/'metrics.json')
        assert metrics['status']=='completed' and metrics['model_calls']==0 and metrics['quality']['D']['status']=='unavailable'
        current=list(map(json.loads,(out/'results'/partition/'per_run.jsonl').read_text().splitlines()))
        for row in current:
            if row['condition']=='C':
                report=verify_run(out/'results'/partition/row['run'],recompute_identity=True)
                assert row['score']['accepted_output']['report_digest']==digest(report)
                fields=report['coverage']['metadata']['field_coverage']
                assert fields['capture_session_id']['state']==fields['provenance_ref']['state']=='missing_column'
                assert row['score']['human_time_saved_seconds'] is None
                assert row['costs']['questions']<=2 and row['costs']['audit_runs']==1
                assert all('--truth' not in p['result']['argv'] for p in row['processes'])
        rows+=current;commands.append({'partition':partition,'record':f'commands/{partition}/result.json','exit_code':result['exit_code']})
    # The first frozen test attempt cannot silently become a second independent test.
    duplicate=list(args);duplicate[-1]=str(out/'duplicate-test')
    result=execute(duplicate,PROJECT,out/'commands/duplicate-test',30)
    assert result['exit_code']==1 and not (out/'duplicate-test').exists()
    commands.append({'case':'duplicate-test-rejected','record':'commands/duplicate-test/result.json','exit_code':1})
    scores=[r['score'] for r in rows if r['condition']=='C']
    assert len(scores)==12 and sum(r['condition']=='D' and r['state']=='blocked' for r in rows)==12
    assert sum(s['goal_correct'] for s in scores)==10
    assert sum(s['excessive_questions'] for s in scores)>=1
    assert any(s['necessary_questions_missed'] for s in scores)
    assert any(s['state']=='WAITING_USER' for s in scores)
    assert any(s['risk']['fn']>0 for s in scores)
    # Direct scorer boundary checks use real saved reports, not replacement Core results.
    initial=read_json(out/'suite/tasks/t000/task.json');registry=read_json(out/'suite/tasks/t000/registry.json')
    truth=read_json(out/'suite/evaluator-truth/t000.json')
    run=out/'results/development/runs/t000/r01/C/run'
    original_transcript=list(map(json.loads,(run.parent/'transcript.jsonl').read_text().splitlines()))
    negative=[]
    for change in ('task_id','limits','registry','input','initial_goal'):
        task=copy.deepcopy(initial);reg=copy.deepcopy(registry);labels=copy.deepcopy(truth)
        if change=='task_id':task['task_id']=labels['task_id']='controlled-other-task'
        if change=='limits':task['limits']['max_questions']-=1
        if change=='registry':reg['documents']['additional']=copy.deepcopy(reg['documents']['metadata'])
        if change=='input':
            reg['datasets']=read_json(out/'suite/tasks/t001/registry.json')['datasets']
            labels['dataset_manifest_digest']=input_manifest(Registry(reg).dataset(task['dataset_ref']),task['limits'])['digest']
        if change=='initial_goal':
            task.update(goal='unspecified',goal_confirmed=False,goal_evidence_refs=[])
            reg['confirmations'].pop('user.local-task');labels['necessary_questions']=['clarify_goal']
        score=score_interaction(task,reg,labels,run,original_transcript)
        assert not score['usable_output'] and score['risk']['fn']==8 and score['unsupported_confirmed_claims'] is None
        negative.append({'case':change,'scope':'controlled direct API negative check, not a benchmark outcome',
                         'task':task,'registry':reg,'truth':labels,'supplied_run':str(run.relative_to(out)),
                         'supplied_transcript':str((run.parent/'transcript.jsonl').relative_to(out)),'score':score})
    foreign=out/'results/development/runs/t003/r01/C/transcript.jsonl'
    rejected=score_interaction(initial,registry,truth,run,list(map(json.loads,foreign.read_text().splitlines())))
    assert not rejected['usable_output'] and not rejected['question_history_usable']
    assert rejected['risk']['fn']==8 and rejected['questions_asked']==0
    negative.append({'case':'foreign_transcript','scope':'controlled direct API negative check, not a benchmark outcome',
                     'task':initial,'registry':registry,'truth':truth,'supplied_run':str(run.relative_to(out)),
                     'supplied_transcript':str(foreign.relative_to(out)),'score':rejected})
    write_json(out/'binding-negative-cases.json',negative,exclusive=True)
    receipt={'status':'passed','code_digest':code_digest(),'commands':commands,'real_C_runs':12,'D_blocked':12,
             'model_calls':0,'real_agent_experiment':'not_run','human_participants':0,'human_time_saved_seconds':None,
             'binding_negative_cases':len(negative),'metadata_missing_columns_recorded':True,
             'data_kind':'controlled synthetic, scripted answers, separate interaction benchmark',
             'observed':{'goal_correct':sum(s['goal_correct'] for s in scores),'questions_asked':sum(s['questions_asked'] for s in scores),
                         'excessive_questions':sum(s['excessive_questions'] for s in scores),
                         'missed_necessary_questions':sum(len(s['necessary_questions_missed']) for s in scores),
                         'risk_false_negatives':sum(s['risk']['fn'] for s in scores)}}
    write_json(out/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
