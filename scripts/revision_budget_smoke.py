"""Persistent real-Core revision budget acceptance with explicitly controlled failures."""
import argparse
import json
from pathlib import Path
import sys
import time

from visionleak_investigator.common import PROJECT,digest,file_hash,read_json,write_json
from visionleak_investigator.core import CoreAdapter,execute
from visionleak_investigator.demo import make_task
from visionleak_investigator.domain import Registry,input_manifest
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.interaction import resume_run
from visionleak_investigator.workflow import code_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=False)
    cases=[];reports=[]
    for index,case in enumerate(('denied','accepted','failed','interrupted')):
        base=out/case;task,registry=make_task(base/'fixture',seed=83310+index)
        task['task_id']=f'rb{index:03d}'
        task['limits']['max_tool_calls']=6 if case=='denied' else 16
        taskpath=base/'fixture/task.json';regpath=base/'fixture/registry.json'
        write_json(taskpath,task);write_json(regpath,registry)
        run=base/'run';answer={'actor':'scripted acceptance; no human participant','goal':'same_entity_new_view'}
        answerpath=base/'answers.json';write_json(answerpath,answer)
        target=run/'revisions'/digest(['answers',answer])
        source=input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
        processes=[]
        def invoke(name,argv,expected):
            process=base/name;result=execute([sys.executable,'-m','visionleak_investigator.cli',*argv],PROJECT,process,90)
            processes.append({'record':str((process/'result.json').relative_to(out)),'expected_exit':expected})
            assert result['error'] is None and result['exit_code']==expected
            return process
        invoke('initial-process',['run','--task',str(taskpath),'--registry',str(regpath),'--profiles','base','--out',str(run)],0)
        initial=verify_run(run,recompute_identity=True);ledger_sha=file_hash(run/'ledger.json')
        reports.append({'case':case+'_initial','run':str(run.relative_to(out)),'report_sha256':file_hash(run/'report.json'),'manifest_sha256':file_hash(run/'manifest.json')})
        observations=[]
        if case in ('failed','interrupted'):
            original=CoreAdapter.inspect_report
            def fault(self,*args,**kwargs):
                entry=read_json(target/'ledger.json')['entries'][-1]
                assert entry['kind']=='resume_identity_check' and entry['status']=='pending'
                started=time.monotonic();inspected=original(self,*args,**kwargs)
                observations.append({'kind':'controlled failure after real Core inspection','real_core':True,'production_incident':False,
                                     'wall_seconds':time.monotonic()-started,'timeout_seconds':kwargs['timeout'],'pending_entry':entry,
                                     'report_sha256':file_hash(Path(args[0])),'inspection':inspected})
                if case=='interrupted':raise KeyboardInterrupt('controlled revision interruption')
                raise ValueError('controlled revision failure')
            CoreAdapter.inspect_report=fault
            try:
                try:resume_run(run,answer)
                except (ValueError,KeyboardInterrupt) as exc:
                    assert 'controlled revision' in str(exc)
                else:raise AssertionError('Expected controlled failure')
            finally:CoreAdapter.inspect_report=original
            pending=read_json(target/'ledger.json')
            assert pending['entries'][-1]['status']==('pending' if case=='interrupted' else 'unknown')
            write_json(base/'ledger-before-recovery.json',pending,exclusive=True)
            write_json(base/'controlled-fault.json',observations,exclusive=True)
        process=invoke('resume-process',['resume','--run',str(run),'--answers',str(answerpath)],1 if case=='denied' else 2)
        if case=='denied':
            assert 'Finalization budget reserved' in (process/'stderr.log').read_text()
            assert not target.exists() and not (run/'pending-revision.json').exists()
            final=None
        else:
            final=verify_run(target,recompute_identity=True)
            assert Path(read_json(process/'stdout.log')['report']).parent==target
            assert final['state']=='PARTIAL' and final['budget']['spent']['audit_runs']==initial['budget']['spent']['audit_runs']==1
            assert not (run/'pending-revision.json').exists()
            if case in ('failed','interrupted'):
                assert not final['claims'] and not final['coverage']['profiles']
                entry=next(e for e in final['budget']['entries'] if e['kind']=='resume_identity_check')
                assert entry['status']=='unknown' and entry['actual']==entry['reservation']
                assert sum(e['kind']=='recovery_finalize' for e in final['budget']['entries'])==1
            before_repeat=file_hash(target/'ledger.json')
            invoke('repeat-process',['resume','--run',str(run),'--answers',str(answerpath)],2)
            assert file_hash(target/'ledger.json')==before_repeat
            reports.append({'case':case+'_revision','run':str(target.relative_to(out)),'report_sha256':file_hash(target/'report.json'),'manifest_sha256':file_hash(target/'manifest.json')})
        assert file_hash(run/'ledger.json')==ledger_sha
        assert source==input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
        cases.append({'case':case,'initial_run':str(run.relative_to(out)),'revision_run':str(target.relative_to(out)) if final else None,
                      'source_unchanged':True,'original_ledger_unchanged':True,'processes':processes,
                      'controlled_real_inspections':len(observations),'final_state':final['state'] if final else 'rejected_before_revision'})
    receipt={'status':'passed','code_digest':code_digest(),'cases':cases,'reports':reports,'model_calls':0,'human_participants':0,
             'scope':'Real Core and CLI on generated images. Failure/interruption injected only after actual identity inspection. No Agent or natural-data experiment.'}
    write_json(out/'receipt.json',receipt,exclusive=True)
    print(json.dumps({'status':'passed','cases':len(cases),'reports':len(reports),'model_calls':0}))


if __name__=='__main__':main()
