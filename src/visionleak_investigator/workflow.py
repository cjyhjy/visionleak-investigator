from __future__ import annotations
import json,time
from pathlib import Path
from typing import Any
from .common import PROJECT,read_json,write_json,append_json,digest,file_hash,no_symlink,now
from .domain import TaskSpec,AgentAction,Registry,input_manifest
from .core import CoreAdapter,PROFILES,KINDS,execute
from .budget import BudgetLedger,BudgetExceeded
from .reporting import ClaimValidator,LIMITATIONS,render_report
from .metadata import interpret,proposal

class ActionGuard:
    def __init__(self,known_evidence: set[str],profiles: list[str]):self.known_evidence=known_evidence;self.profiles=profiles
    def check(self,value: dict) -> dict:
        a=AgentAction.parse(value).value
        if not set(a['evidence_refs'])<=self.known_evidence:raise ValueError('Unknown evidence reference')
        if a['action_type']=='run_audit':
            profile=a['parameters']['profile']
            if profile in self.profiles:raise ValueError('Repeated audit profile')
            if not self.profiles and profile!='base':raise ValueError('Base audit is mandatory')
        return a

def action(profile: str) -> dict:return {'action_type':'run_audit','reason':'Explicit frozen rules profile','evidence_refs':[],'parameters':{'profile':profile}}

def run_task(task: dict, registry_data: dict, out: Path, *,mode: str='rules',profiles: list[str]|None=None,core_path: Path|None=None) -> dict:
    return _execute_task(task,registry_data,out,mode=mode,profiles=profiles,core_path=core_path)

def run_baseline(task: dict,registry_data: dict,out: Path,condition: str) -> dict:
    if condition not in ('A','B'):raise ValueError('Only fixed deterministic A/B baselines')
    return _execute_task(task,registry_data,out,profiles=['base' if condition=='A' else 'all'],baseline=condition)

def rules_profiles(task: dict) -> list[str]:
    text=task['request_text'].lower()
    transform=any(word in text for word in ('rotation','mirror','旋转','镜像'))
    local=any(word in text for word in ('crop','裁切','裁剪'))
    return ['base']+(['all'] if transform and local else ['transform'] if transform else ['local'] if local else [])

def _execute_task(task: dict, registry_data: dict, out: Path, *,mode: str='rules',profiles: list[str]|None=None,core_path: Path|None=None,baseline: str|None=None) -> dict:
    start=time.monotonic();TaskSpec.parse(task);registry=Registry(registry_data);registry.check_confirmations(task)
    if mode!='rules':raise ValueError('Agent mode requires explicit model authorization and a validated provider adapter; no rules fallback')
    profiles=profiles or rules_profiles(task)
    if not profiles or (not baseline and profiles[0]!='base') or len(set(profiles))!=len(profiles) or any(p not in PROFILES for p in profiles) or len(profiles)>min(3,task['limits']['max_core_audit_runs']):raise ValueError('Unique profiles must start with base and fit audit count budget')
    root=registry.dataset(task['dataset_ref']);out=no_symlink(out)
    if out.is_relative_to(root) or root.is_relative_to(out):raise ValueError('Output and dataset paths must be disjoint')
    for ref in [*task['context_refs'],*([task['metadata_ref']] if task['metadata_ref'] else [])]:
        doc=registry.document(ref)
        if doc.is_relative_to(out):raise ValueError('Output contains registered source')
    before=input_manifest(root,task['limits'])
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/'task.json',task,exclusive=True);write_json(out/'registry.private.json',registry_data,exclusive=True)
    write_json(out/'input-manifest.json',before,exclusive=True)
    ledger=BudgetLedger(task['limits'],out/'ledger.json');issues=[];evidence=[];claims=[];completed=[]
    coverage={'input_manifest_digest':before['digest'],'input_preflight':{k:v for k,v in before.items() if k!='files'},'profiles':{},'metadata':{'state':'not_run'},'human_review':{'state':'not_run'},'verification':{}}
    env={};adapter=CoreAdapter(core_path)
    manifest={'schema_version':1,'created_at':now(),'task_digest':digest(task),'registry_digest':digest(registry_data),'dataset_manifest_digest':before['digest'],'core_lock_digest':file_hash(PROJECT/'core.lock.json'),'runtime_lock_digest':file_hash(PROJECT/'core.runtime.lock.json'),'policy':{'name':'baseline-'+baseline if baseline else 'rules-v1','profiles':profiles},'mode':mode,'model_execution':'not_run','code_digest':code_digest()}
    write_json(out/'manifest.json',manifest,exclusive=True)
    def event(state,**data):
        record={'state':state,'time':now(),**data};append_json(out/'events.jsonl',record);write_json(out/'checkpoint.json',{**record,'manifest_digest':digest(manifest)})
    event('VALIDATING_INPUT')
    entry=ledger.reserve('preflight')
    try:env=adapter.doctor();ledger.settle(entry,{'wall_seconds':time.monotonic()-start})
    except Exception as e:
        ledger.settle(entry,None,error=str(e));issues.append('Preflight failed: '+str(e))
    write_json(out/'environment.json',env,exclusive=True)
    stable=True
    for profile in profiles if env else []:
        pending=None
        try:
            if baseline:AgentAction.parse(action(profile))  # Independent fixed baseline driver, never an Agent action route.
            else:ActionGuard({e['evidence_id'] for e in evidence},completed).check(action(profile))
            if input_manifest(root,task['limits'])['digest']!=before['digest']:raise ValueError('Input changed before audit')
            remaining=int(ledger.remaining('decoded_pixels'))
            # Hold source decoding allowance for exact verification and finalization.
            hold=min(before['estimated_source_pixels'],remaining//2)
            allocation={'comparisons':min(10000000,int(ledger.remaining('comparisons')),int(ledger.remaining('index_operations')//16)), 'decoded_pixels':min(100000000,remaining-hold)}
            if min(allocation.values())<=0:raise BudgetExceeded('No audit comparison/index/pixel allocation remains')
            allocation['index_operations']=allocation['comparisons']*16
            pending=ledger.reserve('audit',allocation);call=pending['call_id'];tool=out/'tools'/call
            event('BASE_AUDIT' if profile=='base' else 'EXECUTING',pending_action=call,profile=profile)
            tick=time.monotonic();argv=adapter.audit_argv(root,tool/'output',profile,task['limits'],allocation)
            result=execute(argv,PROJECT,tool,pending['reservation']['wall_seconds'])
            if result['exit_code'] not in (0,2,3):raise ValueError('Core audit failure: '+str(result))
            raw_path=tool/'output/report.json';raw=read_json(raw_path)
            inspected=adapter.inspect_report(raw_path,root,max(0.001,pending['reservation']['wall_seconds']-(time.monotonic()-tick)))
            stats=raw['stats'];pixel_unknown=bool(raw.get('errors'))
            actual={'comparisons':stats.get('comparisons',0),'index_operations':stats.get('indexOperations',0),'decoded_pixels':allocation['decoded_pixels'] if pixel_unknown else raw['scope']['totalDecodedPixels'],'wall_seconds':time.monotonic()-tick}
            if any(actual[k]>allocation[k] for k in allocation):raise ValueError('Core resource usage exceeds allocation')
            ledger.settle(pending,actual,error='Unknown failed-decode cost; full pixel reservation charged' if pixel_unknown else None);pending=None
            completed.append(profile)
            cov={'audit_id':raw['auditId'],'report_ref':str(raw_path.relative_to(out)),'report_sha256':file_hash(raw_path),'complete':raw['complete'],'discovered_at_least':raw['scope']['discoveredAtLeast'],'fingerprinted_images':len(raw['images']),'processed_images':stats['processedImages'],'unprocessed_fingerprints':[i['path'] for i in raw['images'][stats['processedImages']:]],'errors':raw['errors'],'reason':stats.get('reason'),'core_coverage':raw['coverage'],'scope':raw['scope'],'cost':actual,'pixel_cost_measurement':'conservative-reservation' if pixel_unknown else 'core-successful-decode-count'}
            coverage['profiles'][profile]=cov
            if not raw['complete']:issues.append(f'{profile}: incomplete Core scope')
            current=input_manifest(root,task['limits'])
            if current['digest']!=before['digest']:stable=False;raise ValueError('Input changed during audit; evidence unusable')
            verified={};verify_status='not_run';verification=None
            try:
                ids=set(inspected['verification_ids']);images={i['id']:i for i in raw['images']}
                pixels=sum(images[i]['width']*images[i]['height'] for i in ids)
                bypath={f['path']:f for f in before['files']}
                for i in ids:
                    img=images[i];f=bypath[img['path']]
                    if img['width']*img['height']>task['limits']['max_decode_pixels_per_image'] or f['bytes']>task['limits']['max_file_bytes']:raise BudgetExceeded('Verification image limit')
                    if f['sha256']!=img['byteDigest']:raise ValueError('Core image differs from input manifest')
                pending=ledger.reserve('verify',{'decoded_pixels':pixels},final=True);vcall=pending['call_id'];event('VERIFYING',pending_action=vcall,audit_id=raw['auditId']);tick=time.monotonic()
                vr=execute(['node',str(adapter.cli),'verify','--report',str(raw_path),'--root',str(root)],PROJECT,out/'tools'/vcall,pending['reservation']['wall_seconds'])
                if vr['exit_code'] not in (0,4):raise ValueError('Core verification did not return a valid result')
                verification=read_json(out/'tools'/vcall/'stdout.log')
                if verification['auditId']!=raw['auditId']:raise ValueError('Verification audit ID mismatch')
                verified={(p['left'],p['right']):p['status'] for p in verification['pairs']}
                ledger.settle(pending,{'decoded_pixels':pixels,'wall_seconds':time.monotonic()-tick});pending=None
                verify_status='passed' if vr['exit_code']==0 else 'failed'
                if vr['exit_code']==4:issues.append('Invalid or missing exact evidence')
            except (ValueError,OSError) as e:
                if pending is not None and pending['status']=='pending':ledger.settle(pending,None,error=str(e));pending=None
                issues.append('Verification incomplete: '+str(e))
            if input_manifest(root,task['limits'])['digest']!=before['digest']:stable=False;issues.append('Input changed during verification')
            coverage['verification'][raw['auditId']]={'state':verify_status,'result':verification,'candidates_recomputed':False}
            image_map={i['id']:i for i in raw['images']}
            for index,pair in enumerate(raw['pairs']):
                imgs=[image_map[pair[k]] for k in ['left','right']]
                kind=KINDS[pair['evidence']];key=digest(sorted(i['path'] for i in imgs))
                ev={'evidence_id':f'{call}:pair:{index}','kind':kind,'produced_by':call,'core_audit_id':raw['auditId'],'dataset_manifest_digest':before['digest'],'files':[i['path'] for i in imgs],'pair_key':key,'source_positions':[f'{cov["report_ref"]}#/pairs/{index}'],'tool_version':adapter.lock['commit'],'params_digest':digest(raw['options']),'created_at':now(),'verification_state':{'report_identity':'valid','exact_recomputed':verified.get((pair['left'],pair['right']),'not_applicable' if 'candidate' in kind else 'not_run'),'human_review':'not_run'},'images':imgs,'pair':pair}
                evidence.append(ev)
                if stable:
                    claim_kind={'core.byte_identical':'byte_identity','core.pixel_identical':'pixel_identity'}.get(kind,'perceptual_relation')
                    claims.append(ClaimValidator().build(claim_kind,[ev],profile))
            event('PLANNING',profile=profile)
        except (ValueError,OSError) as e:
            if pending is not None and pending['status']=='pending':ledger.settle(pending,None,error=str(e))
            issues.append(str(e));event('PLANNING',error=str(e));break
    if not stable:claims=[]
    questions=[]
    if env and stable:
        try:
            info=interpret(task,registry,before,ledger)
            evidence.extend(info['evidence']);claims.extend(info['claims']);questions=info['questions'];issues.extend(info['issues'])
            coverage['metadata']=info['metadata'];write_json(out/'context.json',info['context'],exclusive=True)
        except BudgetExceeded as e:issues.append(str(e))
    reviews=[{'pair_ref':e['evidence_id'],'pair_key':e['pair_key'],'audit_id':e['core_audit_id'],'status':'pending','requested':False} for e in evidence if 'candidate' in e['kind']]
    state='COMPLETED' if env and not issues and len(completed)==len(profiles) and stable else 'PARTIAL'
    if not env:state='FAILED'
    if questions and state!='FAILED':state='WAITING_USER'
    event('FINALIZING')
    entry=None;tick=time.monotonic()
    try:entry=ledger.reserve('finalize',final=True)
    except BudgetExceeded as e:issues.append(str(e));state='PARTIAL'
    for e in evidence:append_json(out/'evidence.jsonl',e)
    if not evidence:(out/'evidence.jsonl').touch(exist_ok=False)
    coverage['source_unchanged']=stable
    registry_evidence={e['evidence_id']:e for e in evidence}
    for claim in claims:ClaimValidator().validate_claim(claim,registry_evidence,{**coverage['profiles'],'metadata':coverage['metadata']})
    validation={'passed':stable,'claim_count':len(claims),'evidence_sha256':file_hash(out/'evidence.jsonl'),'source_unchanged':stable,'core_reports':{p:c['report_sha256'] for p,c in coverage['profiles'].items()},'meaning':'structural/identity/entailment validation; not evidence of model training or universal absence'}
    write_json(out/'coverage.json',coverage,exclusive=True);write_json(out/'claims.json',claims,exclusive=True)
    write_json(out/'questions.json',questions,exclusive=True);write_json(out/'reviews.json',reviews,exclusive=True)
    write_json(out/'proposal.json',proposal(task,evidence,before),exclusive=True)
    write_json(out/'validation.json',validation,exclusive=True)
    report={'state':state,'mode':mode,'model_execution':'not_run','task':task,'claims':claims,'coverage':coverage,'budget':ledger.data,'questions':questions,'reviews':reviews,'issues':issues,'limitations':LIMITATIONS,'unique_candidate_pairs':len({e['pair_key'] for e in evidence if 'candidate' in e['kind']})}
    # Render is included in the finalization reservation; report is committed only once.
    html=render_report(report)
    if entry is not None:
        elapsed=time.monotonic()-tick
        ledger.settle(entry,{'wall_seconds':elapsed})
        if elapsed>entry['reservation']['wall_seconds']:report['state']='PARTIAL';report['issues'].append('Finalization time exceeded reservation')
    write_json(out/'report.json',report,exclusive=True)
    with (out/'report.html').open('x') as f:f.write(render_report(report))
    event(report['state'],report_digest=digest(report));return report

def code_digest() -> str:
    return digest({str(p.relative_to(PROJECT)):file_hash(p) for base in ['src','scripts','contracts'] for p in sorted((PROJECT/base).rglob('*')) if p.is_file() and '__pycache__' not in str(p)})
