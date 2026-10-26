from __future__ import annotations
import json,copy,shutil,time,fcntl
from pathlib import Path
from datetime import datetime
from .common import PROJECT,read_json,write_json,append_json,digest,file_hash,now,no_symlink
from .domain import Registry,TaskSpec
from .budget import BudgetLedger
from .reporting import ClaimValidator,render_report
from .metadata import interpret,proposal
from .integrity import verify_run


def revise(run: Path, payload: dict,kind: str) -> dict:
    run=no_symlink(run);anchor=run;tick=time.monotonic();old=verify_run(run,recompute_identity=True)
    target=anchor/'revisions'/digest([kind,payload])
    if target.exists():return verify_run(target)
    if (anchor/'latest-revision.json').exists():
        latest=no_symlink(Path(read_json(anchor/'latest-revision.json')['path']))
        if not latest.is_relative_to(anchor/'revisions'):raise ValueError('Revision pointer escaped run')
        old=verify_run(latest,recompute_identity=True);run=latest
    parent_manifest=read_json(run/'manifest.json')
    if parent_manifest['core_lock_digest']!=file_hash(PROJECT/'core.lock.json') or parent_manifest['runtime_lock_digest']!=file_hash(PROJECT/'core.runtime.lock.json'):raise ValueError('Core lock changed; cannot reuse evidence')
    task=copy.deepcopy(old['task']);registry=read_json(run/'registry.private.json')
    existing=[json.loads(s) for s in (run/'evidence.jsonl').read_text().splitlines()]
    human=None
    if kind=='answers':
        if set(payload)-{'actor','goal','entity_key'} or not payload.get('actor') or not (set(payload)&{'goal','entity_key'}):raise ValueError('Answers must contain an actor and goal/entity_key only')
        for field in ['goal','entity_key']:
            if field not in payload:continue
            value=payload[field]
            if not isinstance(value,str) or not value:raise ValueError('Empty answer')
            ref='user.answer:'+digest([field,payload])
            task[field]=value;task[field+'_confirmed']=True;task[field+'_evidence_refs']=[ref]
            registry['confirmations'][ref]={'kind':'user.'+field+'_confirmation',field:value,'actor':payload['actor'],'confirmed_at':now()}
        TaskSpec.parse(task);Registry(registry).check_confirmations(task)
    elif kind=='review':
        keys={'reviewer','created_at','dataset_manifest_digest','audit_id','pair_ref','decision','reason'}
        if set(payload)!=keys or not all(isinstance(payload[k],str) and 0<len(payload[k])<=2000 for k in keys):raise ValueError('Review schema mismatch')
        if payload['decision'] not in ('confirmed','rejected','unsure'):raise ValueError('Invalid review decision')
        stamp=datetime.fromisoformat(payload['created_at'])
        if stamp.tzinfo is None:raise ValueError('Review timestamp needs timezone')
        matches=[e for e in existing if e['evidence_id']==payload['pair_ref'] and 'candidate' in e['kind']]
        if len(matches)!=1:raise ValueError('Unknown candidate review reference')
        source=matches[0]
        if payload['dataset_manifest_digest']!=parent_manifest['dataset_manifest_digest'] or payload['audit_id']!=source['core_audit_id']:raise ValueError('Review belongs to a different input or audit')
        human={'evidence_id':'review:'+digest(payload),'kind':'human.same_source_confirmation' if payload['decision']=='confirmed' else 'human.candidate_review','produced_by':'user.review_import','core_audit_id':source['core_audit_id'],'dataset_manifest_digest':parent_manifest['dataset_manifest_digest'],'files':source['files'],'pair_key':source['pair_key'],'source_positions':['review.input.json'],'tool_version':'vli-0.1.0','params_digest':digest(payload),'created_at':now(),'verification_state':{'human_review':payload['decision']},'facts':payload}
    else:raise ValueError('Unknown revision kind')
    target.mkdir(parents=True,exist_ok=False)
    write_json(target/(kind+'.input.json'),payload,exclusive=True)
    ledger=BudgetLedger(task['limits'],target/'ledger.json',copy.deepcopy(old['budget']))
    ledger.recover_pending()
    entry=ledger.reserve('resume_identity_check',{'review_pairs':1} if kind=='review' else {},final=False)
    ledger.settle(entry,{'wall_seconds':time.monotonic()-tick,**({'review_pairs':1} if kind=='review' else {})})
    # Reuse only immutable witnesses. Copying their bytes performs no image recomputation.
    shutil.copytree(run/'tools',target/'tools')
    before=read_json(run/'input-manifest.json');write_json(target/'input-manifest.json',before,exclusive=True)
    coverage=copy.deepcopy(old['coverage']);issues=[x for x in old['issues'] if not x.startswith(('Goal/','Entity metadata','No registered entity','Metadata has','Clarification budget'))]
    evidence=[e for e in existing if not e['kind'].startswith(('metadata.','user.goal'))]
    claims=[c for c in old['claims'] if c['claim_type'] not in ('goal_conflict','declared_entity_overlap')]
    info=interpret(task,Registry(registry),before,ledger);evidence.extend(info['evidence']);claims.extend(info['claims']);issues.extend(info['issues']);coverage['metadata']=info['metadata']
    reviews=copy.deepcopy(old['reviews'])
    if human:
        evidence.append(human)
        for row in reviews:
            if row['pair_ref']==payload['pair_ref']:row.update(status=payload['decision'],reviewer=payload['reviewer'],created_at=payload['created_at'])
        if human['kind']=='human.same_source_confirmation':claims.append(ClaimValidator().build('same_source_review',[human],'human_review'))
    state='WAITING_USER' if info['questions'] else 'PARTIAL' if issues else 'COMPLETED'
    record={**parent_manifest,'created_at':now(),'task_digest':digest(task),'registry_digest':digest(registry),'evidence_reused_from':str(run),'parent_manifest_digest':digest(parent_manifest),'revision_kind':kind,'supersedes_risk_interpretation':str(run),'core_reexecuted':False}
    for name,value in [('task.json',task),('registry.private.json',registry),('manifest.json',record),('coverage.json',coverage),('claims.json',claims),('context.json',info['context']),('questions.json',info['questions']),('reviews.json',reviews),('proposal.json',proposal(task,evidence,before))]:write_json(target/name,value,exclusive=True)
    for ev in evidence:append_json(target/'evidence.jsonl',ev)
    if not evidence:(target/'evidence.jsonl').touch(exist_ok=False)
    evmap={e['evidence_id']:e for e in evidence}
    for c in claims:ClaimValidator().validate_claim(c,evmap,{**coverage['profiles'],'metadata':coverage['metadata'],'human_review':coverage['human_review']})
    validation={**read_json(run/'validation.json'),'evidence_sha256':file_hash(target/'evidence.jsonl'),'claim_count':len(claims)}
    write_json(target/'validation.json',validation,exclusive=True)
    entry=ledger.reserve('finalize',final=True);tick=time.monotonic()
    result={**old,'state':state,'task':task,'claims':claims,'coverage':coverage,'budget':ledger.data,'questions':info['questions'],'reviews':reviews,'issues':issues,'revision':{'kind':kind,'path':str(target),'reused_from':str(run),'core_reexecuted':False}}
    render_report(result);ledger.settle(entry,{'wall_seconds':time.monotonic()-tick})
    write_json(target/'report.json',result,exclusive=True);(target/'report.html').write_text(render_report(result))
    write_json(target/'checkpoint.json',{'state':state,'report_digest':digest(result),'manifest_digest':digest(record)},exclusive=True)
    append_json(target/'events.jsonl',{'state':state,'revision_kind':kind,'time':now(),'image_evidence_reused':True})
    write_json(anchor/'latest-revision.json',{'path':str(target),'digest':digest(result)})
    return result

def _locked_revision(run: Path,payload: dict,kind: str) -> dict:
    lock=no_symlink(run/'.revision.lock')
    with lock.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        try:return revise(run,payload,kind)
        finally:fcntl.flock(f,fcntl.LOCK_UN)

def resume_run(run: Path,answers: dict) -> dict:return _locked_revision(run,answers,'answers')
def import_review(run: Path,review: dict) -> dict:return _locked_revision(run,review,'review')
