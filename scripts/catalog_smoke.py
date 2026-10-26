"""Run a new synthetic frozen catalog through the public CLI and recheck its receipts."""
import argparse
import json
from pathlib import Path
import sys

from visionleak_investigator.common import PROJECT, file_hash, read_json, write_json
from visionleak_investigator.core import execute
from visionleak_investigator.evaluation_fixture import make_catalog_suite
from visionleak_investigator.integrity import verify_run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--tasks',type=int,default=12)
    args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    root=out/'suite'
    catalog,protocol=make_catalog_suite(root,count=args.tasks)
    receipts=[]
    def invoke(name,command,extra,expected=0):
        argv=[sys.executable,'-m','visionleak_investigator.cli',command,
            '--catalog',str(root/'catalog.json'),'--root',str(root),'--protocol',str(root/'protocol.json'),*map(str,extra)]
        result=execute(argv,PROJECT,out/'commands'/name,900)
        receipts.append({'name':name,'exit_code':result['exit_code'],'expected_exit':expected,'record':f'commands/{name}/result.json'})
        if result['error'] or result['exit_code']!=expected:
            write_json(out/'incomplete-receipt.json',{'status':'failed','commands':receipts})
            raise RuntimeError(f'{name} failed: inspect saved original stderr')
    invoke('freeze','eval-freeze',['--out',out/'frozen.json'])
    reports=0;score_records=[];states={};original_inputs={}
    for row in catalog['sources']:original_inputs[row['path']]=file_hash(root/row['path'])
    for partition in ('development','validation','test'):
        dest=out/'results'/partition
        invoke('run-'+partition,'eval-run',['--frozen',out/'frozen.json','--partition',partition,'--out',dest])
        summary=read_json(dest/'metrics.json')
        assert summary['status']=='completed_no_model' and summary['model_calls']==0
        rows=[json.loads(line) for line in (dest/'per_run.jsonl').read_text().splitlines()]
        states[partition]=summary['runs']
        assert len(rows)==summary['tasks']*4
        for row in rows:
            if row['condition']=='D':
                assert row['state']=='blocked' and 'score' not in row
                continue
            report=verify_run(dest/row['run'],recompute_identity=True)
            assert report['state']==row['state'] and row['score']['exact']['truth_denominator']==3
            assert row['comparison_status']=='accepted' and row['score']['usable_output']
            if row['condition']=='B':assert report['budget']['spent']['audit_runs']==1 and list(report['coverage']['profiles'])==['all']
            worker=read_json(dest/row['process_record']/'invocation.json')
            assert '--truth' not in worker['argv'] and '--frozen' not in worker['argv']
            assert row['full_task_resources']['cpu_seconds']>=0
            score_records.append({'partition':partition,'task_id':row['task_id'],'condition':row['condition'],
                'state':row['state'],'run':str((dest/row['run']).relative_to(out)),
                'score_sha256':file_hash(dest/'scores'/row['task_id']/'r01'/row['condition']/'score.json'),
                'cpu_seconds':row['full_task_resources']['cpu_seconds'],
                'tree_rss_peak_bytes':row['full_task_resources']['tree_rss_peak_bytes']})
            reports+=1
    invoke('reject-test-repeat','eval-run',['--frozen',out/'frozen.json','--partition','test','--out',out/'duplicate-test'],1)
    assert 'already attempted' in (out/'commands/reject-test-repeat/stderr.log').read_text()
    assert not (out/'duplicate-test').exists()
    assert all(file_hash(root/path)==sha for path,sha in original_inputs.items())
    receipt={'status':'passed','data_kind':'fresh self-generated synthetic engineering catalog',
        'tasks':args.tasks,'real_task_runs':reports,'models_called':0,'real_agent_experiment':'not_run',
        'source_unchanged':True,'commands':receipts,'states':states,'scores':score_records,
        'freeze_digest':read_json(out/'frozen.json')['freeze_digest'],
        'limitations':['Synthetic validation/test partition labels exercise execution gates only; no independent natural-scene experiment.',
                       'No actual human participant or measured human time savings.','D blocked; E not_run.']}
    write_json(out/'receipt.json',receipt,exclusive=True)
    print(json.dumps({'status':receipt['status'],'tasks':args.tasks,'real_task_runs':reports,'models_called':0}))


if __name__=='__main__':main()
