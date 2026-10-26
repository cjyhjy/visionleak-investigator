from pathlib import Path
import json
from .common import read_json,file_hash,digest,safe_child
from .workflow import code_digest
from .core import CoreAdapter
from .domain import Registry,input_manifest
from .reporting import ClaimValidator
from .review_state import review_coverage

def verify_run(run: Path, *,check_input: bool=True,recompute_identity: bool=False) -> dict:
    report=read_json(run/'report.json');validation=read_json(run/'validation.json');manifest=read_json(run/'manifest.json')
    if file_hash(run/'evidence.jsonl')!=validation['evidence_sha256']:raise ValueError('Evidence store tampered')
    if 'model_ledger_sha256' in validation and file_hash(run/'model-ledger.json')!=validation['model_ledger_sha256']:raise ValueError('Model ledger tampered')
    if digest(read_json(run/'task.json'))!=manifest['task_digest']:raise ValueError('Task changed')
    registry=read_json(run/'registry.private.json')
    if digest(registry)!=manifest['registry_digest']:raise ValueError('Registry changed')
    root=Registry(registry).dataset(report['task']['dataset_ref'])
    if check_input and input_manifest(root,report['task']['limits'])['digest']!=manifest['dataset_manifest_digest']:raise ValueError('Input changed since audit')
    checkpoint=read_json(run/'checkpoint.json')
    if checkpoint.get('report_digest')!=digest(report):raise ValueError('Report changed')
    if checkpoint.get('manifest_digest')!=digest(manifest):raise ValueError('Manifest changed')
    if read_json(run/'ledger.json')!=report['budget']:raise ValueError('Ledger changed')
    if 'rules_decision_sha256' in validation or 'rules_policy_sha256' in validation or 'rules' in report:
        if file_hash(run/'rules-decision.json')!=validation['rules_decision_sha256'] or file_hash(run/'rules-policy.json')!=validation['rules_policy_sha256']:
            raise ValueError('Rules routing record changed')
        rules=read_json(run/'rules-decision.json');policy=read_json(run/'rules-policy.json')
        if (rules!=report['rules'] or digest(policy)!=rules['policy_digest'] or digest(policy)!=manifest['policy']['config_digest']
                or rules['initial_task_digest']!=manifest['policy']['initial_task_digest'] or rules['dataset_manifest_digest']!=manifest['dataset_manifest_digest']):
            raise ValueError('Rules routing identity changed')
    if report.get('recovery'):
        receipt=read_json(run/'recovery-receipt.json')
        if receipt!=report['recovery'] or checkpoint.get('recovery_receipt_digest')!=digest(receipt):raise ValueError('Recovery receipt changed')
        if not report.get('revision') and receipt['original_manifest_digest']!=digest(manifest):raise ValueError('Recovery origin changed')
        for saved in receipt['preserved_files']:
            if file_hash(safe_child(run,saved['path']))!=saved['sha256']:raise ValueError('Recovery archive changed')
    adapter=CoreAdapter()
    if recompute_identity:adapter.verify_artifacts()
    for profile,cov in report['coverage']['profiles'].items():
        path=run/cov['report_ref']
        if file_hash(path)!=validation['core_reports'][profile]:raise ValueError('Core report changed')
        if recompute_identity:adapter.inspect_report(path,root)
    evidence={e['evidence_id']:e for e in [json.loads(line) for line in (run/'evidence.jsonl').read_text().splitlines()]}
    if 'human_review_coverage_digest' in validation:
        if report['coverage']['human_review']!=review_coverage(report['reviews']) or digest(report['coverage']['human_review'])!=validation['human_review_coverage_digest']:
            raise ValueError('Human review coverage changed')
        expected={p for e in evidence.values() if e['kind'].startswith('human.') for p in e['source_positions']}
        if expected!=set(validation['review_inputs']):raise ValueError('Human review input inventory changed')
        for item in evidence.values():
            if not item['kind'].startswith('human.'):continue
            if digest(item['facts'])!=item['params_digest']:raise ValueError('Human review payload changed')
            for ref in item['source_positions']:
                path=safe_child(run,ref)
                if file_hash(path)!=validation['review_inputs'][ref] or read_json(path)!=item['facts']:raise ValueError('Human review input changed')
        for row in report['reviews']:
            if row['status']=='pending':continue
            matches=[e for e in evidence.values() if e['kind'].startswith('human.') and e['facts']['pair_ref']==row['pair_ref']
                     and e['facts']['decision']==row['status'] and e['facts']['reviewer']==row.get('reviewer') and e['facts']['created_at']==row.get('created_at')]
            if not matches or evidence[row['pair_ref']]['verification_state']['human_review']!=row['status']:
                raise ValueError('Review summary is not bound to current review evidence')
    for ref in [*report['task']['context_refs'],*([report['task']['metadata_ref']] if report['task']['metadata_ref'] else [])]:Registry(registry).document(ref)
    for claim in report['claims']:ClaimValidator().validate_claim(claim,evidence,{**report['coverage']['profiles'],'metadata':report['coverage']['metadata'],'human_review':report['coverage']['human_review']})
    return report
