"""Fail-closed recovery of stopped runs; quarantine unaccepted results, no tool replay."""
from pathlib import Path
import fcntl
import time
from .common import read_json,write_json,append_json,file_hash,digest,now,no_symlink
from .domain import Registry,input_manifest
from .budget import BudgetLedger,BudgetExceeded
from .reporting import LIMITATIONS,render_report
from .workflow import code_digest


def recover_interrupted(run: Path) -> dict:
    run=no_symlink(run)
    # Share the host-revision lock: concurrent recovery/answers cannot settle one
    # interrupted ledger twice. The caller must first stop the original worker.
    with no_symlink(run/'.revision.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:return _recover_interrupted(run)
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def _recover_interrupted(run: Path) -> dict:
    started=time.monotonic()
    if (run/'report.json').exists():
        from .integrity import verify_run
        try:return verify_run(run)
        except (ValueError,OSError):
            checkpoint=read_json(run/'checkpoint.json') if (run/'checkpoint.json').exists() else {}
            if checkpoint.get('report_digest'):raise
            # A partially published, never-accepted report is quarantined below.
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
    raw_reports=[str(p.relative_to(run)) for p in (run/'tools').glob('*/output/report.json')]
    coverage={'input_manifest_digest':current['digest'],'profiles':{},'metadata':{'state':'not_run'},'human_review':{'state':'not_run'},'verification':{},'source_unchanged':True,'unaccepted_raw_reports':raw_reports}
    stamp=now();backup=run/'pre-recovery'/digest([stamp,digest(manifest)])
    preserved=[]
    # Recovery accepts no pre-crash witness. Move evidence/proposals too, so a
    # later host revision cannot accidentally resurrect an unaccepted record.
    for name in ('evidence.jsonl','coverage.json','claims.json','validation.json','questions.json',
                 'reviews.json','proposal.json','report.html','checkpoint.json','recovery-receipt.json',
                 'rules-decision.json','rules-policy.json','report.json','report.pending.json','report.pending.html',
                 'report.before-overrun.html','publication-failure.json'):
        path=no_symlink(run/name)
        if path.exists():
            dest=no_symlink(backup/name);dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists():raise ValueError('Recovery archive already exists')
            sha=file_hash(path);path.rename(dest)
            preserved.append({'path':dest.relative_to(run).as_posix(),'sha256':sha})
    receipt={'schema_version':1,'kind':'conservative_recovery','created_at':stamp,
             'original_manifest_digest':digest(manifest),'original_code_digest':manifest['code_digest'],
             'processor_code_digest':code_digest(),'core_reexecuted':False,'accepted_image_evidence_count':0,
             'preserved_files':preserved}
    (run/'evidence.jsonl').touch(exist_ok=False)
    validation={'passed':True,'evidence_sha256':file_hash(run/'evidence.jsonl'),'claim_count':0,'core_reports':{},'source_unchanged':True,'recovery':'No raw report accepted or claim published; pending cost conservatively settled'}
    report={'state':'PARTIAL','mode':manifest['mode'],'model_execution':'not_run','task':task,'claims':[],'coverage':coverage,'budget':ledger.data,'questions':[],'reviews':[],'issues':['Process interrupted. Pending reservations conservatively charged; raw reports retained. Start a new run for additional image checks.'],'limitations':LIMITATIONS,'unique_candidate_pairs':0,'recovery':receipt}
    if manifest.get('revision_kind'):
        report['revision']={'kind':manifest['revision_kind'],'path':str(run),'reused_from':manifest['evidence_reused_from'],
                            'core_reexecuted':False,'image_evidence_reused':False,'reused_core_evidence_count':0,
                            'recovered_interruption':True,'attempt_code_digest':manifest['code_digest']}
    if (run/'model-ledger.json').exists():
        validation['model_ledger_sha256']=file_hash(run/'model-ledger.json')
        report['planning']={'execution_label':'scripted_test_only','recovery':'conservative_no_replay','accounting':model.summary()}
    proposal={'status':'unavailable_after_interruption','requires_approval':True,'protect_eval_split':True,
              'source_manifest_digest':current['digest'],'proposed_exclusions':[],
              'new_manifest':None,'plan_check':{'structure':'not_run','image_reaudit':'not_run'},
              'limitations':['No pre-crash evidence accepted. Original proposal, if any, is archived as unaccepted material.']}
    for name,value in [('coverage.json',coverage),('claims.json',[]),('validation.json',validation),
                       ('questions.json',[]),('reviews.json',[]),('proposal.json',proposal),('recovery-receipt.json',receipt)]:
        write_json(run/name,value,exclusive=True)
    if input_manifest(root,task['limits'])['digest']!=manifest['dataset_manifest_digest']:
        raise ValueError('Input changed during recovery; no recovered report published')
    write_json(run/'checkpoint.json',{'state':'FINALIZING','manifest_digest':digest(manifest),'pending_action':closing['call_id']})
    from .publication import publish_report
    publish_report(run,report,[],ledger,closing,started,render_report)
    write_json(run/'checkpoint.json',{'state':'PARTIAL','report_digest':digest(report),'manifest_digest':digest(manifest),
                                     'recovery':'conservative','recovery_receipt_digest':digest(receipt)})
    append_json(run/'events.jsonl',{'state':'PARTIAL','recovery':True,'time':now(),'reexecuted_tools':0,
                                  'processor_code_digest':receipt['processor_code_digest']})
    return report
