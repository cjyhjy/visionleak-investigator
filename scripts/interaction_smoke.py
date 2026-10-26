"""Run a separate frozen synthetic interaction benchmark with real Core and scripted answers."""
import argparse
import json
from pathlib import Path
import sys

from visionleak_investigator.common import PROJECT, read_json, write_json
from visionleak_investigator.core import execute
from visionleak_investigator.evaluation_data import freeze_catalog
from visionleak_investigator.interaction_fixture import make_interaction_suite
from visionleak_investigator.integrity import verify_run
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
                verify_run(out/'results'/partition/row['run'],recompute_identity=True)
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
    receipt={'status':'passed','code_digest':code_digest(),'commands':commands,'real_C_runs':12,'D_blocked':12,
             'model_calls':0,'real_agent_experiment':'not_run','human_participants':0,'human_time_saved_seconds':None,
             'data_kind':'controlled synthetic, scripted answers, separate interaction benchmark',
             'observed':{'goal_correct':sum(s['goal_correct'] for s in scores),'questions_asked':sum(s['questions_asked'] for s in scores),
                         'excessive_questions':sum(s['excessive_questions'] for s in scores),
                         'missed_necessary_questions':sum(len(s['necessary_questions_missed']) for s in scores),
                         'risk_false_negatives':sum(s['risk']['fn'] for s in scores)}}
    write_json(out/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
