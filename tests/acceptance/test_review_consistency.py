import json
from pathlib import Path

import pytest

from visionleak_investigator.common import digest,file_hash,read_json,write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.interaction import import_review,resume_run
from visionleak_investigator.review_state import review_coverage
from visionleak_investigator.workflow import run_task,run_scripted_task


def review_payload(report, pair, decision='confirmed'):
    return {'reviewer':'scripted consistency fixture, no human participant','created_at':'2026-10-26T21:00:00+00:00',
        'dataset_manifest_digest':report['coverage']['input_manifest_digest'],'audit_id':pair['audit_id'],
        'pair_ref':pair['pair_ref'],'decision':decision,'reason':'Controlled review lifecycle test'}


def test_review_reversal_supersedes_active_claims_and_preserves_payloads(tmp_path):
    task,registry=make_task(tmp_path/'fixture');task['limits']['max_tool_calls']=32
    root=tmp_path/'run';initial=run_task(task,registry,root,profiles=['base','all'])
    payload=review_payload(initial,initial['reviews'][0])
    confirmed=import_review(root,payload);confirmed_path=Path(confirmed['revision']['path'])
    assert confirmed['coverage']['human_review']['confirmed_records']==1
    assert confirmed['coverage']['human_review']['state']=='partial'
    rejected=import_review(root,{**payload,'decision':'rejected'})
    assert not any(c['claim_type']=='same_source_review' for c in rejected['claims'])
    assert rejected['revision']['superseded_review_evidence_refs']
    assert rejected['coverage']['human_review']['confirmed_records']==0
    assert rejected['coverage']['human_review']['rejected_records']==1
    revised=resume_run(root,{'actor':'scripted answer','goal':'content_audit'})
    current=Path(revised['revision']['path']);verify_run(current)
    records=list(map(json.loads,(current/'evidence.jsonl').read_text().splitlines()))
    human=[e for e in records if e['kind'].startswith('human.')]
    assert len(human)==1 and human[0]['facts']['decision']=='rejected'
    for record in human:
        assert all(read_json(current/p)==record['facts'] for p in record['source_positions'])
    assert next(e for e in records if e['evidence_id']==payload['pair_ref'])['verification_state']['human_review']=='rejected'
    assert read_json(confirmed_path/'report.json')==confirmed  # Historical confirmation remains unchanged.
    assert revised['budget']['spent']['audit_runs']==initial['budget']['spent']['audit_runs']
    assert all(e['kind'] not in ('core.byte_identical','core.pixel_identical') for e in records if e['evidence_id']==payload['pair_ref'])


def test_review_payload_and_coverage_integrity_are_checked(tmp_path):
    task,registry=make_task(tmp_path/'fixture');root=tmp_path/'run';initial=run_task(task,registry,root,profiles=['base','all'])
    revised=import_review(root,review_payload(initial,initial['reviews'][0]));current=Path(revised['revision']['path'])
    validation=read_json(current/'validation.json');path=current/next(iter(validation['review_inputs']))
    saved=path.read_bytes();path.write_text('{}')
    with pytest.raises(ValueError,match='Human review input changed'):verify_run(current)
    path.write_bytes(saved)
    report=read_json(current/'report.json');report['coverage']['human_review']['state']='not_run'
    write_json(current/'report.json',report)
    checkpoint=read_json(current/'checkpoint.json');checkpoint['report_digest']=digest(report);write_json(current/'checkpoint.json',checkpoint)
    with pytest.raises(ValueError,match='Human review coverage changed'):verify_run(current)


def test_requested_unsure_review_keeps_waiting_without_recharging_request(tmp_path):
    from visionleak_investigator.controller import PlannerReply
    task,registry=make_task(tmp_path/'fixture');task['limits']['max_tool_calls']=32
    def request(payload):
        observed=payload['observation']
        if 'all' not in observed['profiles']:kind='run_audit';params={'profile':'all'}
        else:
            refs=[e['evidence_id'] for e in observed['evidence'] if 'candidate' in e['kind']]
            kind='request_review';params={'pair_refs':refs[:2]}
        return PlannerReply(json.dumps({'action_type':kind,'reason':'scripted acceptance only','evidence_refs':[],'parameters':params}))
    root=tmp_path/'run';initial=run_scripted_task(task,registry,root,request=request)
    pending=[r for r in initial['reviews'] if r['requested']]
    assert len(pending)==2 and initial['state']=='WAITING_USER'
    revised=import_review(root,review_payload(initial,pending[0],'unsure'))
    assert revised['state']=='WAITING_USER' and revised['coverage']['human_review']['unsure_records']==1
    assert revised['budget']['spent']['review_pairs']==initial['budget']['spent']['review_pairs']==2
    verify_run(Path(revised['revision']['path']))


def test_review_coverage_does_not_resolve_duplicate_or_conflicting_witnesses():
    rows=[{'pair_key':'a','status':'confirmed'},{'pair_key':'a','status':'pending'}]
    assert review_coverage(rows)['resolved_pairs']==0
    rows[1]['status']='rejected'
    assert review_coverage(rows)['state']=='partial'
    rows[1]['status']='confirmed'
    assert review_coverage(rows)['state']=='complete'
    assert review_coverage([])['state']=='not_applicable'


def test_legacy_stale_confirmation_does_not_survive_new_goal_revision(tmp_path):
    task,registry=make_task(tmp_path/'fixture');task['limits']['max_tool_calls']=32
    root=tmp_path/'run';initial=run_task(task,registry,root,profiles=['base','all'])
    payload=review_payload(initial,initial['reviews'][0])
    confirmed=import_review(root,payload);cp=Path(confirmed['revision']['path'])
    old_evidence=next(e for e in map(json.loads,(cp/'evidence.jsonl').read_text().splitlines()) if e['kind']=='human.same_source_confirmation')
    old_claim=next(c for c in confirmed['claims'] if c['claim_type']=='same_source_review')
    rejected=import_review(root,{**payload,'decision':'rejected'});rp=Path(rejected['revision']['path'])
    # Reproduce the already-recorded legacy artifact shape, not a model/production experiment.
    with (rp/'evidence.jsonl').open('a') as output:output.write(json.dumps(old_evidence)+'\n')
    rejected['claims'].append(old_claim);write_json(rp/'report.json',rejected)
    validation=read_json(rp/'validation.json')
    validation.pop('human_review_coverage_digest');validation.pop('review_inputs')
    validation.update(evidence_sha256=file_hash(rp/'evidence.jsonl'),claim_count=len(rejected['claims']))
    write_json(rp/'validation.json',validation)
    checkpoint=read_json(rp/'checkpoint.json');checkpoint['report_digest']=digest(rejected);write_json(rp/'checkpoint.json',checkpoint)
    revised=resume_run(root,{'actor':'scripted legacy fixture','goal':'content_audit'})
    assert not any(c['claim_type']=='same_source_review' for c in revised['claims'])
    assert old_evidence['evidence_id'] in revised['revision']['superseded_review_evidence_refs']
    verify_run(Path(revised['revision']['path']))
