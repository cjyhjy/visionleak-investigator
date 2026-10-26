import json
from pathlib import Path
import pytest
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task
from visionleak_investigator.common import read_json, file_hash

def test_real_rules_loop_and_source_unchanged(tmp_path):
    task,registry=make_task(tmp_path/'fixture')
    data=tmp_path/'fixture/images'; before={str(p):file_hash(p) for p in data.rglob('*') if p.is_file()}
    run=tmp_path/'run'; result=run_task(task,registry,run)
    assert result['state']=='COMPLETED'
    assert result['model_execution']=='not_run'
    assert any(c['claim_type']=='byte_identity' and c['status']=='confirmed' for c in result['claims'])
    assert any(c['claim_type']=='pixel_identity' and c['status']=='confirmed' for c in result['claims'])
    assert before=={str(p):file_hash(p) for p in data.rglob('*') if p.is_file()}
    ledger=read_json(run/'ledger.json'); assert ledger['spent']['audit_runs']==1
    assert ledger['spent']['decoded_pixels']>96*96*5
    assert ledger['spent']['tool_calls']>=3
    assert (run/'evidence.jsonl').stat().st_size>0
    assert read_json(run/'validation.json')['passed']

def test_partial_keeps_evidence_and_coverage(tmp_path):
    task,registry=make_task(tmp_path/'fixture'); task['limits']['max_comparisons_total']=1
    result=run_task(task,registry,tmp_path/'run')
    assert result['state']=='PARTIAL'
    c=result['coverage']['profiles']['base']; assert c['processed_images']<c['fingerprinted_images']
    assert not any(c['claim_type']=='no_evidence_in_scope' for c in result['claims'])

def test_budget_across_profiles(tmp_path):
    task,registry=make_task(tmp_path/'fixture'); task['limits']['max_total_decoded_pixels']=150000
    result=run_task(task,registry,tmp_path/'run',profiles=['base','all'])
    ledger=read_json(tmp_path/'run/ledger.json')
    assert ledger['spent']['decoded_pixels']<=150000
    assert result['state']=='PARTIAL'

def test_T06_bad_and_unknown_inputs(tmp_path):
    task,registry=make_task(tmp_path/'fixture'); root=tmp_path/'fixture/images'
    (root/'test/bad.png').write_text('not an image'); (root/'test/unknown.xyz').write_text('unknown')
    r=run_task(task,registry,tmp_path/'run')
    assert r['state']=='PARTIAL' and r['coverage']['profiles']['base']['errors']
    assert r['claims']

def test_T18_output_overlap_and_symlink(tmp_path):
    task,registry=make_task(tmp_path/'fixture'); root=tmp_path/'fixture/images'
    with pytest.raises(ValueError):run_task(task,registry,root/'output')
    (root/'test/escape.png').symlink_to(tmp_path/'fixture/task.json')
    with pytest.raises(ValueError):run_task(task,registry,tmp_path/'run')

def test_T20_agent_no_consent_no_fallback(tmp_path,monkeypatch):
    task,registry=make_task(tmp_path/'fixture');monkeypatch.setenv('OPENAI_API_KEY','not-authorization')
    with pytest.raises(ValueError,match='authoriz'):run_task(task,registry,tmp_path/'run',mode='agent')
    assert not (tmp_path/'run').exists()

def test_T32_flat_layout_rejected(tmp_path):
    task,registry=make_task(tmp_path/'fixture'); root=tmp_path/'fixture/images'
    import shutil
    for p in list(root.rglob('*.png')): shutil.move(p,root/p.name)
    with pytest.raises(ValueError,match='split'):run_task(task,registry,tmp_path/'run')

def test_T25_proposal_preserves_test_and_source(tmp_path):
    task,registry=make_task(tmp_path/'fixture');run=tmp_path/'run';run_task(task,registry,run)
    proposal=read_json(run/'proposal.json')
    assert proposal['requires_approval'] and proposal['status']=='suggestion_only'
    assert proposal['proposed_exclusions']
    assert proposal['plan_check']['structure']=='passed'
    assert proposal['plan_check']['known_conflicts_remaining']  # validation/test duplicate is intentionally retained
    assert proposal['plan_check']['image_reaudit']=='not_run'
    assert all(row['included'] for row in proposal['new_manifest'] if row['image_split']=='test')
    assert (tmp_path/'fixture/images/train/001.png').exists()

def test_T31_three_scans_and_verifications_share_one_ledger(tmp_path):
    task,registry=make_task(tmp_path/'fixture');run=tmp_path/'run'
    result=run_task(task,registry,run,profiles=['base','transform','local'])
    assert result['state']=='COMPLETED',result['issues']
    ledger=read_json(run/'ledger.json');assert ledger['spent']['audit_runs']==3
    assert len([e for e in ledger['entries'] if e['kind']=='verify'])==3
    assert ledger['spent']['decoded_pixels']==3*(6+3)*96*96
    assert ledger['spent']['comparisons']==sum(e['actual'].get('comparisons',0) for e in ledger['entries'])
    assert ledger['spent']['index_operations']<=task['limits']['max_index_operations_total']
