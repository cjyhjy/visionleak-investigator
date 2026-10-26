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
from .workflow import code_digest
from .review_state import review_coverage,preserve_review_inputs


def revise(run: Path, payload: dict,kind: str) -> dict:
    run=no_symlink(run);anchor=run;tick=time.monotonic();old=verify_run(run,recompute_identity=True)
    target=anchor/'revisions'/digest([kind,payload])
    if target.exists():return verify_run(target)
    if (anchor/'latest-revision.json').exists():
        latest=no_symlink(Path(read_json(anchor/'latest-revision.json')['path']))
        if not latest.is_relative_to(anchor/'revisions'):raise ValueError('Revision pointer escaped run')
        old=verify_run(latest,recompute_identity=True);run=latest
    if old['coverage'].get('source_unchanged') is not True:raise ValueError('Source changed in parent audit; start a new run')
    parent_manifest=read_json(run/'manifest.json')
    if parent_manifest['core_lock_digest']!=file_hash(PROJECT/'core.lock.json') or parent_manifest['runtime_lock_digest']!=file_hash(PROJECT/'core.runtime.lock.json'):raise ValueError('Core lock changed; cannot reuse evidence')
    task=copy.deepcopy(old['task']);registry=read_json(run/'registry.private.json')
    existing=[json.loads(s) for s in (run/'evidence.jsonl').read_text().splitlines()]
    accepted_audits={c['audit_id'] for c in old['coverage']['profiles'].values()}
    existing=[e for e in existing if not e.get('core_audit_id') or e['core_audit_id'] in accepted_audits]
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
    # A pending explicitly requested review was already charged by the host.
    review_charge=0 if kind=='review' and any(r['pair_ref']==payload['pair_ref'] and r.get('requested') and r['status']=='pending' for r in old['reviews']) else 1
    entry=ledger.reserve('resume_identity_check',{'review_pairs':review_charge} if kind=='review' else {},final=False)
    ledger.settle(entry,{'wall_seconds':time.monotonic()-tick,**({'review_pairs':review_charge} if kind=='review' else {})})
    # Reuse only immutable witnesses. Copying their bytes performs no image recomputation.
    shutil.copytree(run/'tools',target/'tools')
    for name in ('model-ledger.json','planner-trace.json','planner-tools.json','planner-requests.jsonl','planner-actions.jsonl','recovery-receipt.json'):
        if (run/name).exists():shutil.copy2(run/name,target/name)
    if (run/'recovery-receipt.json').exists() and (run/'pre-recovery').exists():shutil.copytree(run/'pre-recovery',target/'pre-recovery')
    before=read_json(run/'input-manifest.json');write_json(target/'input-manifest.json',before,exclusive=True)
    coverage=copy.deepcopy(old['coverage']);issues=[x for x in old['issues'] if not x.startswith(('Goal/','Entity metadata','No registered entity','Metadata has','Clarification budget'))]
    current_reviews={r['pair_ref']:r for r in old['reviews']}
    superseded=set()
    for item in existing:
        if not item['kind'].startswith('human.'):continue
        facts=item['facts'];current=current_reviews.get(facts['pair_ref'],{})
        stale=any(current.get(k)!=facts[v] for k,v in [('status','decision'),('reviewer','reviewer'),('created_at','created_at')])
        if stale or (human and facts['pair_ref']==payload['pair_ref']):superseded.add(item['evidence_id'])
    evidence=[e for e in existing if not e['kind'].startswith(('metadata.','user.goal'))]
    evidence=[e for e in evidence if e['evidence_id'] not in superseded]
    claims=[c for c in old['claims'] if c['claim_type'] not in ('goal_conflict','declared_entity_overlap') and not (set(c['evidence_refs'])&superseded)]
    info=interpret(task,Registry(registry),before,ledger);evidence.extend(info['evidence']);claims.extend(info['claims']);issues.extend(info['issues']);coverage['metadata']=info['metadata']
    if not info['questions']:issues=[x for x in issues if x!='Required clarification remains unrequested']
    accepted_refs={e['evidence_id'] for e in evidence}
    reviews=[copy.deepcopy(r) for r in old['reviews'] if r['pair_ref'] in accepted_refs]
    if human:
        evidence.append(human)
        for item in evidence:
            if item['evidence_id']==payload['pair_ref']:item['verification_state']['human_review']=payload['decision']
        for row in reviews:
            if row['pair_ref']==payload['pair_ref']:row.update(status=payload['decision'],reviewer=payload['reviewer'],created_at=payload['created_at'])
        if human['kind']=='human.same_source_confirmation':claims.append(ClaimValidator().build('same_source_review',[human],'human_review'))
    coverage['human_review']=review_coverage(reviews)
    for row in reviews:
        if row['status']!='pending':
            for item in evidence:
                if item['evidence_id']==row['pair_ref']:item['verification_state']['human_review']=row['status']
    review_inputs=preserve_review_inputs(evidence,target)
    waiting_reviews=any(r.get('requested') and r['status'] in ('pending','unsure') for r in reviews)
    state='WAITING_USER' if info['questions'] or waiting_reviews else 'PARTIAL' if issues else 'COMPLETED'
    origin=parent_manifest.get('image_evidence_origin',{'manifest_digest':digest(parent_manifest),'investigator_code_digest':parent_manifest['code_digest'],'core_lock_digest':parent_manifest['core_lock_digest'],'runtime_lock_digest':parent_manifest['runtime_lock_digest']})
    reused_core_evidence_count=sum(e['kind'].startswith('core.') for e in evidence)
    record={**parent_manifest,'code_digest':code_digest(),'image_evidence_origin':origin,'parent_report_digest':digest(old),'created_at':now(),'task_digest':digest(task),'registry_digest':digest(registry),'evidence_reused_from':str(run),'parent_manifest_digest':digest(parent_manifest),'revision_kind':kind,'supersedes_risk_interpretation':str(run),'core_reexecuted':False}
    for name,value in [('task.json',task),('registry.private.json',registry),('manifest.json',record),('coverage.json',coverage),('claims.json',claims),('context.json',info['context']),('questions.json',info['questions']),('reviews.json',reviews),('proposal.json',proposal(task,evidence,before))]:write_json(target/name,value,exclusive=True)
    for ev in evidence:append_json(target/'evidence.jsonl',ev)
    if not evidence:(target/'evidence.jsonl').touch(exist_ok=False)
    evmap={e['evidence_id']:e for e in evidence}
    for c in claims:ClaimValidator().validate_claim(c,evmap,{**coverage['profiles'],'metadata':coverage['metadata'],'human_review':coverage['human_review']})
    validation={**read_json(run/'validation.json'),'evidence_sha256':file_hash(target/'evidence.jsonl'),'claim_count':len(claims)}
    validation.update(human_review_coverage_digest=digest(coverage['human_review']),review_inputs=review_inputs)
    write_json(target/'validation.json',validation,exclusive=True)
    entry=ledger.reserve('finalize',final=True);tick=time.monotonic()
    result={**old,'state':state,'task':task,'claims':claims,'coverage':coverage,'budget':ledger.data,'questions':info['questions'],'reviews':reviews,'issues':issues,'revision':{'kind':kind,'path':str(target),'reused_from':str(run),'core_reexecuted':False,'processor_code_digest':record['code_digest'],'image_evidence_code_digest':origin['investigator_code_digest'],'image_evidence_reused':bool(reused_core_evidence_count),'reused_core_evidence_count':reused_core_evidence_count}}
    result['revision']['superseded_review_evidence_refs']=sorted(superseded)
    if old.get('planning'):
        result['planning']={**old['planning'],'continuation':'host_revision_only_no_new_planning'}
        result['question_backlog']=[]
    render_report(result,evidence);ledger.settle(entry,{'wall_seconds':time.monotonic()-tick})
    write_json(target/'report.json',result,exclusive=True);(target/'report.html').write_text(render_report(result,evidence))
    checkpoint={'state':state,'report_digest':digest(result),'manifest_digest':digest(record)}
    if result.get('recovery'):checkpoint['recovery_receipt_digest']=digest(result['recovery'])
    write_json(target/'checkpoint.json',checkpoint,exclusive=True)
    append_json(target/'events.jsonl',{'state':state,'revision_kind':kind,'time':now(),'image_evidence_reused':bool(reused_core_evidence_count),'processor_code_digest':record['code_digest']})
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
