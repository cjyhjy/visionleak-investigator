from __future__ import annotations
import csv,io,time
from collections import defaultdict
from .common import now,digest,file_hash,safe_child
from .domain import Registry,SPLITS
from .budget import BudgetExceeded
from .reporting import ClaimValidator

def interpret(task: dict,registry: Registry,manifest: dict,ledger) -> dict:
    """Deterministic interpretation. Context text is data, never instructions."""
    tick=time.monotonic();entry=ledger.reserve('interpret_context')
    result={'evidence':[],'claims':[],'questions':[],'issues':[],'context':[],'metadata':{'state':'not_applicable','issues':[]}}
    try:
        for ref in task['context_refs']:
            path=registry.document(ref);text=path.read_text(encoding='utf-8')
            result['context'].append({'context_ref':ref,'sha256':file_hash(path),'excerpt':text[:8000],'truncated':len(text)>8000,'trust':'untrusted-data; never executed'})
        confirmations=registry.value.get('confirmations',{})
        goal=None
        if task['goal_confirmed']:
            ref=next(r for r in task['goal_evidence_refs'] if confirmations.get(r,{}).get('goal')==task['goal'])
            goal={'evidence_id':'goal:'+digest([ref,task['goal']]),'kind':'user.goal_confirmation','produced_by':'host.registry','core_audit_id':None,'dataset_manifest_digest':manifest['digest'],'files':[],'source_positions':['registry.confirmations/'+ref],'tool_version':'vli-0.1.0','params_digest':digest(task['goal']),'created_at':now(),'verification_state':{'host_confirmation':'valid'},'facts':confirmations[ref]}
            result['evidence'].append(goal)
        else:result['questions'].append({'question_code':'clarify_goal','question':'请选择实验目标：内容审计、新实体泛化或同实体新视角。'})
        entity_goal=task['goal'] in ('new_entity_generalization','same_entity_new_view','unspecified')
        if entity_goal and not task['entity_key_confirmed']:
            if task['metadata_ref']:result['questions'].append({'question_code':'clarify_entity_key','question':'哪个已登记的 CSV 列代表真实实体（而非类别）？请确认其含义。'})
            else:result['issues'].append('No registered entity metadata; entity scope is unknown')
        if task['metadata_ref']:
            ref=task['metadata_ref'];path=registry.document(ref);content=path.read_text(encoding='utf-8-sig')
            reader=csv.DictReader(io.StringIO(content));fields=reader.fieldnames or []
            if not {'file_id','relative_path'}<=set(fields) or len(fields)!=len(set(fields)):raise ValueError('CSV requires unique columns file_id and relative_path')
            rows=list(reader)
            if len(rows)>10000:raise ValueError('Metadata row limit')
            bypath={r['path']:r for r in manifest['files'] if r['supported_image']};seen_ids={};seen_paths={};valid=[];problems=[];missing_entity=0
            for index,row in enumerate(rows,2):
                rel=row.get('relative_path');file_id=row.get('file_id')
                try:safe_child(registry.dataset(task['dataset_ref']),rel)
                except ValueError:problems.append({'row':index,'code':'unsafe_path'});continue
                if not file_id or rel not in bypath:problems.append({'row':index,'code':'unmapped_row'});continue
                if file_id in seen_ids or rel in seen_paths:problems.append({'row':index,'code':'duplicate_or_conflicting_mapping'});continue
                seen_ids[file_id]=rel;seen_paths[rel]=row
                declared=row.get('image_split','')
                actual=bypath[rel]['image_split']
                if declared and declared!=actual:problems.append({'row':index,'code':'split_conflict'});continue
                entity=(row.get(task['entity_key'] or '', '') or '').strip()
                if not entity:missing_entity+=1
                valid.append({'file_id':file_id,'path':rel,'image_split':actual,'entity_id':entity,'csv_line':index,'provenance_ref':row.get('provenance_ref') or 'registered-user-csv'})
            unmapped=set(bypath)-set(seen_paths)
            cov={'state':'partial' if problems or unmapped or missing_entity else 'complete','sha256':file_hash(path),'rows':len(rows),'mapped_rows':len(valid),'unmapped_image_count':len(unmapped),'unmapped_images':sorted(unmapped),'missing_entity_rows':missing_entity,'issues':problems,'entity_key':task['entity_key'],'entity_key_confirmed':task['entity_key_confirmed'],'trust':'user-declared metadata, not independently verified physical identity'}
            result['metadata']=cov
            if problems:result['issues'].append('Metadata has path/split/identity conflicts; entity claims withheld')
            if entity_goal and (unmapped or missing_entity):result['issues'].append('Entity metadata does not cover all images')
            if task['entity_key_confirmed'] and task['entity_key'] not in fields:result['issues'].append('Confirmed entity column missing');problems.append({'code':'missing_entity_column'})
            if task['goal_confirmed'] and task['entity_key_confirmed'] and not problems:
                groups=defaultdict(list)
                for row in valid:
                    if row['entity_id']:groups[row['entity_id']].append(row)
                for entity,members in groups.items():
                    if len({r['image_split'] for r in members})<2:continue
                    ev={'evidence_id':'metadata:'+digest([cov['sha256'],entity]),'kind':'metadata.entity_overlap','produced_by':'deterministic.group-check','core_audit_id':None,'dataset_manifest_digest':manifest['digest'],'files':[m['path'] for m in members],'source_positions':[f'{ref}#line={m["csv_line"]}' for m in members],'tool_version':'vli-0.1.0','params_digest':digest(task['entity_key']),'created_at':now(),'verification_state':{'metadata_integrity':'valid'},'facts':{'entity_key_confirmed':True,'entity_id':entity,'members':members,'metadata_sha256':cov['sha256'],'provenance':'registered-user-csv'}}
                    result['evidence'].append(ev)
                    result['claims'].append(ClaimValidator().build('declared_entity_overlap',[ev,goal],'metadata',goal['evidence_id']))
                    if task['goal']=='new_entity_generalization':result['claims'].append(ClaimValidator().build('goal_conflict',[ev,goal],'metadata',goal['evidence_id']))
        # Only actual question requests consume the question budget; backlog remains visible.
        available=int(ledger.remaining('questions'))
        if len(result['questions'])>available:
            result['issues'].append('Clarification budget exhausted');result['questions']=result['questions'][:available]
        actual={'wall_seconds':time.monotonic()-tick,'questions':len(result['questions'])}
        # Questions are finite independently of the time reservation.
        entry['reservation']['questions']=len(result['questions']);ledger.settle(entry,actual)
    except Exception as e:
        ledger.settle(entry,{'wall_seconds':time.monotonic()-tick},error=str(e));result['issues'].append(str(e));result['metadata']['state']='partial'
    return result

def proposal(task: dict,evidence: list[dict],manifest: dict) -> dict:
    excluded={};by_path={r['path']:r for r in manifest['files']}
    for e in evidence:
        if e['kind'] in ('core.byte_identical','core.pixel_identical') and e['verification_state']['exact_recomputed']=='valid':
            files=e['files']
            if any(by_path[f]['image_split']=='test' for f in files):
                for f in files:
                    if by_path[f]['image_split']=='train':excluded.setdefault(f,[]).append(e['evidence_id'])
        if e['kind']=='metadata.entity_overlap' and task['goal']=='new_entity_generalization' and task['goal_confirmed']:
            members=e['facts']['members']
            if any(m['image_split']=='test' for m in members):
                for m in members:
                    if m['image_split']=='train':excluded.setdefault(m['path'],[]).append(e['evidence_id'])
    new_manifest=[{'path':r['path'],'image_split':r['image_split'],'included':r['path'] not in excluded} for r in manifest['files'] if r['supported_image']]
    included={r['path'] for r in new_manifest if r['included']}
    assert len({r['path'] for r in new_manifest})==len(new_manifest)
    assert all(r['included'] for r in new_manifest if r['image_split']=='test')
    remaining=[]
    for e in evidence:
        if e['kind'] in ('core.byte_identical','core.pixel_identical') and e['verification_state']['exact_recomputed']=='valid' and set(e['files'])<=included:remaining.append(e['evidence_id'])
        elif e['kind']=='metadata.entity_overlap' and task['goal']=='new_entity_generalization':
            if len({m['image_split'] for m in e['facts']['members'] if m['path'] in included})>1:remaining.append(e['evidence_id'])
    check={'structure':'passed','test_preserved':True,'known_conflicts_remaining':remaining,'scope':'structure and known evidence only','image_reaudit':'not_run'}
    return {'status':'suggestion_only','requires_approval':True,'protect_eval_split':True,'source_manifest_digest':manifest['digest'],'proposed_exclusions':[{'path':p,'evidence_refs':refs} for p,refs in excluded.items()], 'new_manifest':new_manifest, 'plan_check':check, 'limitations':['Requires class/sample-balance review before applying.','Existing trained models may require retraining and independent evaluation.','No source files were modified.']}
