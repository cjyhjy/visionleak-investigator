from pathlib import Path
import json
from .common import read_json,file_hash,digest,safe_child
from .workflow import code_digest
from .core import CoreAdapter
from .domain import Registry,input_manifest
from .reporting import ClaimValidator

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
    for ref in [*report['task']['context_refs'],*([report['task']['metadata_ref']] if report['task']['metadata_ref'] else [])]:Registry(registry).document(ref)
    for claim in report['claims']:ClaimValidator().validate_claim(claim,evidence,{**report['coverage']['profiles'],'metadata':report['coverage']['metadata'],'human_review':report['coverage']['human_review']})
    return report
