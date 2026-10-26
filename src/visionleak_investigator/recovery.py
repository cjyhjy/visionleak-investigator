"""Fail-closed crash recovery: preserve raw evidence, never blindly repeat a tool."""
from pathlib import Path
import json,time
from .common import read_json,write_json,append_json,file_hash,digest,now,no_symlink
from .domain import Registry,input_manifest
from .budget import BudgetLedger,BudgetExceeded
from .reporting import LIMITATIONS,render_report

def recover_interrupted(run: Path) -> dict:
    run=no_symlink(run);started=time.monotonic()
    if (run/'report.json').exists():
        from .integrity import verify_run
        return verify_run(run)
    task=read_json(run/'task.json');registry=read_json(run/'registry.private.json');manifest=read_json(run/'manifest.json')
    if digest(task)!=manifest['task_digest'] or digest(registry)!=manifest['registry_digest']:raise ValueError('Interrupted task/registry identity changed')
    root=Registry(registry).dataset(task['dataset_ref']);current=input_manifest(root,task['limits'])
    if current['digest']!=manifest['dataset_manifest_digest']:raise ValueError('Input changed; cannot recover evidence for this version')
    ledger=BudgetLedger(task['limits'],run/'ledger.json',read_json(run/'ledger.json'));ledger.recover_pending()
    if (run/'model-ledger.json').exists():
        from .model_budget import ModelBudgetLedger
        model=ModelBudgetLedger(run/'model-ledger.json',binding=manifest['task_digest'],limits=task['limits'],execution_label='scripted_test_only')
        model.recover_pending();ledger.data['planner_accounting']=model.summary();ledger.save()
    try:closing=ledger.reserve('recovery_finalize',final=True)
    except BudgetExceeded as e:
        write_json(run/'recovery-status.json',{'state':'FAILED','reason':'No finalization allowance remains','raw_outputs_preserved':True})
        raise ValueError('Recovery cannot finalize within remaining budget; raw outputs preserved') from e
    # No unaccepted raw tool output is promoted into a claim during recovery.
    raw_reports=[str(p.relative_to(run)) for p in (run/'tools').glob('*/output/report.json')]
    coverage={'input_manifest_digest':current['digest'],'profiles':{},'metadata':{'state':'not_run'},'human_review':{'state':'not_run'},'verification':{},'source_unchanged':True,'unaccepted_raw_reports':raw_reports}
    if not (run/'evidence.jsonl').exists():(run/'evidence.jsonl').touch(exist_ok=False)
    validation={'passed':True,'evidence_sha256':file_hash(run/'evidence.jsonl'),'claim_count':0,'core_reports':{},'source_unchanged':True,'recovery':'No raw report accepted or claim published; pending cost conservatively settled'}
    report={'state':'PARTIAL','mode':'rules','model_execution':'not_run','task':task,'claims':[],'coverage':coverage,'budget':ledger.data,'questions':[],'reviews':[],'issues':['Process interrupted. Pending reservations conservatively charged; raw reports retained. Start a new run for additional image checks.'],'limitations':LIMITATIONS,'unique_candidate_pairs':0}
    report['mode']=manifest['mode']
    if (run/'model-ledger.json').exists():
        validation['model_ledger_sha256']=file_hash(run/'model-ledger.json')
        report['planning']={'execution_label':'scripted_test_only','recovery':'conservative_no_replay','accounting':model.summary()}
    for name,value in [('coverage.json',coverage),('claims.json',[]),('validation.json',validation),('questions.json',[]),('reviews.json',[])]:
        if (run/name).exists():
            # Keep pre-crash artifacts as evidence rather than silently overwriting.
            backup=run/'pre-recovery'/name;backup.parent.mkdir(exist_ok=True)
            (run/name).rename(backup)
        write_json(run/name,value,exclusive=True)
    ledger.settle(closing,{'wall_seconds':time.monotonic()-started})
    write_json(run/'report.json',report,exclusive=True)
    if (run/'report.html').exists():(run/'report.html').rename(run/'pre-recovery/report.html')
    (run/'report.html').write_text(render_report(report))
    write_json(run/'checkpoint.json',{'state':'PARTIAL','report_digest':digest(report),'manifest_digest':digest(manifest),'recovery':'conservative'})
    append_json(run/'events.jsonl',{'state':'PARTIAL','recovery':True,'time':now(),'reexecuted_tools':0})
    return report
