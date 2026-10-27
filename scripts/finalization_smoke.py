"""Real-Core finalization acceptance; controlled latency/failures, no model or human."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import time

from visionleak_investigator import workflow,interaction,recovery,publication
from visionleak_investigator.budget import BudgetLedger
from visionleak_investigator.common import PROJECT,file_hash,read_json,write_json
from visionleak_investigator.core import execute
from visionleak_investigator.demo import make_task
from visionleak_investigator.domain import Registry,input_manifest
from visionleak_investigator.integrity import verify_run

CASES=('initial','revision','recovery','overrun','publication_failure','renderer_failure')


def worker(case,out):
    out.mkdir(parents=True,exist_ok=False)
    task,registry=make_task(out/'fixture',seed=83410+CASES.index(case));task['task_id']=f'fp{CASES.index(case):03d}'
    write_json(out/'fixture/task.json',task)
    before=input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
    run=out/'run';initial=None;reports=[]
    if case in ('revision','recovery'):
        initial=workflow.run_task(task,registry,run,profiles=['base'])
        if case=='recovery':
            write_json(out/'report-before-controlled-interruption.json',initial,exclusive=True)
            (run/'report.json').unlink()
    module=interaction if case=='revision' else recovery if case=='recovery' else workflow
    original_render=module.render_report;original_open=Path.open;original_reserve=BudgetLedger.reserve
    original_publish=publication._publish_file;original_proposal=interaction.proposal
    renders=[];writes=[];assemblies=[]
    def render(*args,**kwargs):
        started=time.monotonic();time.sleep(.12)
        value=original_render(*args,**kwargs);renders.append(time.monotonic()-started)
        if case=='renderer_failure':raise OSError('controlled finalization renderer failure')
        return value
    @contextmanager
    def delayed_write(path,*args,**kwargs):
        started=time.monotonic()
        with original_open(path,*args,**kwargs) as stream:yield stream
        time.sleep(.12);writes.append(time.monotonic()-started)
    def opening(path,*args,**kwargs):
        if path.name=='report.pending.html' and args and args[0]=='x' and case not in ('overrun','publication_failure'):
            return delayed_write(path,*args,**kwargs)
        return original_open(path,*args,**kwargs)
    def reserve(self,kind,allocation=None,**kwargs):
        if case=='overrun' and kind=='finalize':allocation={**(allocation or {}),'wall_seconds':.05}
        return original_reserve(self,kind,allocation,**kwargs)
    def publish(staged,destination):
        original_publish(staged,destination)
        if case=='publication_failure' and destination.name=='report.json':raise OSError('controlled interruption after JSON publication')
    def proposal(*args,**kwargs):
        target=Path(read_json(run/'pending-revision.json')['path']);entry=read_json(target/'ledger.json')['entries'][-1]
        assert entry['kind']=='finalize' and entry['status']=='pending'
        started=time.monotonic();time.sleep(.12);value=original_proposal(*args,**kwargs)
        assemblies.append(time.monotonic()-started);return value
    module.render_report=render;Path.open=opening;BudgetLedger.reserve=reserve;publication._publish_file=publish
    if case=='revision':interaction.proposal=proposal
    error=None;report=None;target=run
    try:
        if case=='revision':
            report=interaction.resume_run(run,{'actor':'scripted finalization acceptance; no human participant','goal':'content_audit'})
            target=Path(report['revision']['path'])
        elif case=='recovery':report=recovery.recover_interrupted(run)
        else:report=workflow.run_task(task,registry,run,profiles=['base'])
    except ValueError as exc:
        assert case in ('publication_failure','renderer_failure') and 'publication failed' in str(exc)
        error=str(exc);write_json(out/'ledger-before-failure-recovery.json',read_json(run/'ledger.json'),exclusive=True)
        write_json(out/'publication-failure-copy.json',read_json(run/'publication-failure.json'),exclusive=True)
    finally:
        module.render_report=original_render;Path.open=original_open;BudgetLedger.reserve=original_reserve
        publication._publish_file=original_publish;interaction.proposal=original_proposal
    assert len(renders)==1
    if case=='publication_failure':
        report=recovery.recover_interrupted(run)
        assert report['state']=='PARTIAL' and not report['claims'] and not report['coverage']['profiles']
        assert any(row['path'].endswith('/report.json') for row in report['recovery']['preserved_files'])
    if report is not None:
        assert verify_run(target,recompute_identity=True)==report
        if case in ('initial','revision','recovery'):
            assert len(writes)==1
            assert report['budget']['entries'][-1]['actual']['wall_seconds']>=sum(renders)+sum(writes)+sum(assemblies)
        if case=='overrun':
            assert report['state']=='PARTIAL' and report['publication']['html_kind']=='overrun_status_receipt'
            assert report['budget']['entries'][-1]['overrun']['wall_seconds']>0
        for location in ([run,target] if case=='revision' else [target]):
            reports.append({'run':str(location.relative_to(out)),'report_sha256':file_hash(location/'report.json'),'manifest_sha256':file_hash(location/'manifest.json')})
    else:
        assert case=='renderer_failure' and not (run/'report.json').exists()
        entry=read_json(run/'ledger.json')['entries'][-1]
        assert entry['status']=='unknown' and entry['actual']==entry['reservation']
        assert list((run/'tools').glob('*/output/report.json'))
    assert before==input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
    value={'status':'passed','case':case,'reports':reports,'render_durations':renders,'staged_html_write_durations':writes,
           'assembly_durations':assemblies,'controlled_error':error,'source_unchanged':True,'model_calls':0,
           'scope':'Actual Core/renderer. 0.12-second delays and publication failures are controlled fixtures, not production incidents.'}
    write_json(out/'case.json',value,exclusive=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--worker-case',choices=CASES);args=parser.parse_args();out=args.out.resolve()
    if args.worker_case:worker(args.worker_case,out);return
    out.mkdir(parents=True,exist_ok=False);cases=[];reports=[]
    for case in CASES:
        result=execute([sys.executable,str(Path(__file__).resolve()),'--worker-case',case,'--out',str(out/case)],PROJECT,out/'processes'/case,90)
        assert result['error'] is None and result['exit_code']==0
        record=read_json(out/case/'case.json');cases.append({'case':case,'receipt':case+'/case.json','process':'processes/'+case+'/result.json'})
        for report in record['reports']:reports.append({**report,'run':case+'/'+report['run']})
    write_json(out/'receipt.json',{'status':'passed','code_digest':workflow.code_digest(),'cases':cases,'reports':reports,
        'model_calls':0,'human_participants':0,'scope':'Real Core in six measured worker processes; controlled engineering acceptance only.'},exclusive=True)
    print(json.dumps({'status':'passed','cases':len(cases),'reports':len(reports),'model_calls':0}))


if __name__=='__main__':main()
