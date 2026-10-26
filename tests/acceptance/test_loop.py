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


def test_T06_encoded_and_decoded_limits_preserve_other_real_evidence(tmp_path):
    from PIL import Image
    task,registry=make_task(tmp_path/'fixture');root=tmp_path/'fixture/images'
    (root/'test/large-encoded.png').write_bytes((root/'train/001.png').read_bytes()+b'x'*50000)
    Image.new('RGB',(128,128),(34,56,78)).save(root/'test/large-decoded.png')
    task['limits']['max_file_bytes']=40000
    task['limits']['max_decode_pixels_per_image']=10000
    result=run_task(task,registry,tmp_path/'run')
    assert result['state']=='PARTIAL' and result['coverage']['source_unchanged']
    errors=json.dumps(result['coverage']['profiles']['base']['errors'])
    assert 'large-encoded.png' in errors and 'large-decoded.png' in errors
    assert any(c['claim_type']=='byte_identity' and c['status']=='confirmed' for c in result['claims'])
    assert not result['coverage']['profiles']['base']['complete']


def test_T03_rotation_and_mirror_are_candidates_not_exact_identity(tmp_path):
    from PIL import Image
    task,registry=make_task(tmp_path/'fixture');root=tmp_path/'fixture/images'
    with Image.open(root/'train/001.png') as im:
        im.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(root/'test/007.png')
    result=run_task(task,registry,tmp_path/'run',profiles=['base','all'])
    evidence={e['evidence_id']:e for e in map(json.loads,(tmp_path/'run/evidence.jsonl').read_text().splitlines())}
    for other in ('test/004.png','test/007.png'):
        records=[e for e in evidence.values() if set(e['files'])=={'train/001.png',other}]
        assert records and all('candidate' in e['kind'] for e in records)
        refs={e['evidence_id'] for e in records}
        claims=[c for c in result['claims'] if refs & set(c['evidence_refs'])]
        assert claims and all(c['status']=='candidate' for c in claims)
    assert result['coverage']['source_unchanged']
