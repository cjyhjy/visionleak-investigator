"""Real Core evidence survives host revisions without mislabelling code or recovery."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from visionleak_investigator.common import digest, file_hash, read_json, write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.interaction import resume_run
from visionleak_investigator.recovery import recover_interrupted
from visionleak_investigator.workflow import run_task


def audit(tmp_path):
    task,registry=make_task(tmp_path/'fixture')
    run=tmp_path/'run';report=run_task(task,registry,run,profiles=['base','all'])
    return run,report


def test_revision_tracks_current_host_and_original_image_evidence(tmp_path,monkeypatch):
    import visionleak_investigator.interaction as interaction
    run,first=audit(tmp_path);original=read_json(run/'manifest.json')
    before={str(p.relative_to(run)):file_hash(p) for p in (run/'tools').rglob('*') if p.is_file()}
    # Only the host-version metadata function is controlled here; all witnesses
    # are produced by real Core. This does not assert a real release upgrade.
    new_code=digest('test-only-host-version-two')
    monkeypatch.setattr(interaction,'code_digest',lambda:new_code)
    second=resume_run(run,{'actor':'scripted fixture','goal':'same_entity_new_view'})
    target=Path(second['revision']['path']);manifest=read_json(target/'manifest.json')
    assert manifest['code_digest']==new_code
    assert manifest['image_evidence_origin']['investigator_code_digest']==original['code_digest']
    assert manifest['image_evidence_origin']['manifest_digest']==digest(original)
    assert second['revision']['processor_code_digest']==new_code
    assert second['revision']['image_evidence_reused'] is True
    assert second['budget']['spent']['audit_runs']==first['budget']['spent']['audit_runs']
    assert all(file_hash(target/path)==sha for path,sha in before.items())
    monkeypatch.setattr(interaction,'code_digest',lambda:digest('test-only-host-version-three'))
    third=resume_run(run,{'actor':'scripted fixture','goal':'content_audit'})
    third_manifest=read_json(Path(third['revision']['path'])/'manifest.json')
    assert third_manifest['image_evidence_origin']==manifest['image_evidence_origin']
    assert third_manifest['parent_manifest_digest']==digest(manifest)
    assert resume_run(run,{'actor':'scripted fixture','goal':'same_entity_new_view'})==second
    assert read_json(run/'manifest.json')==original
    verify_run(Path(third['revision']['path']),recompute_identity=True)


@pytest.mark.parametrize('artifact',['manifest','ledger'])
def test_published_checkpoint_and_budget_bind_their_artifacts(tmp_path,artifact):
    run,_=audit(tmp_path)
    path=run/f'{artifact}.json';value=read_json(path)
    if artifact=='manifest':value['code_digest']='0'*64
    else:value['spent']['comparisons']+=1
    write_json(path,value)
    with pytest.raises(ValueError,match='Manifest changed|Ledger changed'):verify_run(run)


def test_recovery_quarantines_precrash_evidence_and_proposal(tmp_path):
    run,_=audit(tmp_path)
    original=read_json(run/'manifest.json')
    assert read_json(run/'proposal.json')['proposed_exclusions']
    old_evidence=file_hash(run/'evidence.jsonl');old_proposal=file_hash(run/'proposal.json')
    # Explicit interruption fixture, not an observed production crash.
    (run/'report.json').unlink()
    recovered=recover_interrupted(run)
    receipt=read_json(run/'recovery-receipt.json')
    assert receipt['original_manifest_digest']==digest(original)
    assert receipt['original_code_digest']==original['code_digest']
    assert recovered['recovery']==receipt and receipt['core_reexecuted'] is False
    assert (run/'evidence.jsonl').read_bytes()==b''
    assert not read_json(run/'proposal.json')['proposed_exclusions']
    saved={p['sha256'] for p in receipt['preserved_files']}
    assert {old_evidence,old_proposal}<=saved
    verify_run(run)
    revised=resume_run(run,{'actor':'scripted fixture','goal':'content_audit'})
    target=Path(revised['revision']['path'])
    assert not any(e['kind'].startswith('core.') for e in map(json.loads,(target/'evidence.jsonl').read_text().splitlines()))
    assert not read_json(target/'proposal.json')['proposed_exclusions']
    assert revised['revision']['image_evidence_reused'] is False
    assert '此前没有已接纳的图像证据' in (target/'report.html').read_text()
    assert revised['state']=='PARTIAL'


def test_recovery_is_serialized_and_receipt_tampering_is_rejected(tmp_path):
    run,_=audit(tmp_path);(run/'report.json').unlink()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first,second=list(pool.map(recover_interrupted,[run,run]))
    assert first==second
    assert len([e for e in first['budget']['entries'] if e['kind']=='recovery_finalize'])==1
    receipt=read_json(run/'recovery-receipt.json');receipt['processor_code_digest']='0'*64
    write_json(run/'recovery-receipt.json',receipt)
    with pytest.raises(ValueError,match='Recovery receipt changed'):verify_run(run)


def test_legacy_recovery_raw_evidence_cannot_be_reintroduced_by_revision(tmp_path):
    run,_=audit(tmp_path);old_evidence=(run/'evidence.jsonl').read_bytes()
    (run/'report.json').unlink();recovered=recover_interrupted(run)
    # Compatibility fixture for older recoveries that retained unaccepted raw
    # records in the active evidence file. No false claim is added.
    (run/'evidence.jsonl').write_bytes(old_evidence)
    validation=read_json(run/'validation.json');validation['evidence_sha256']=file_hash(run/'evidence.jsonl');write_json(run/'validation.json',validation)
    revised=resume_run(run,{'actor':'scripted compatibility fixture','goal':'content_audit'})
    target=Path(revised['revision']['path'])
    assert revised['revision']['reused_core_evidence_count']==0
    assert not revised['reviews'] and not read_json(target/'proposal.json')['proposed_exclusions']
    verify_run(target)
