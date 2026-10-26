"""Real-Core review reversal/provenance acceptance; every review is an explicit scripted fixture."""
import argparse
import json
from pathlib import Path
import shutil

from visionleak_investigator.common import file_hash,read_json,write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.interaction import import_review,resume_run
from visionleak_investigator.workflow import run_task,code_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--legacy-run',type=Path);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False);reports=[]
    def keep(run,label):
        value=verify_run(run,recompute_identity=True)
        reports.append({'case':label,'run':str(run.relative_to(out)),'report_sha256':file_hash(run/'report.json'),
                        'manifest_sha256':file_hash(run/'manifest.json')})
        return value
    task,registry=make_task(out/'fixture',80001);task['limits']['max_tool_calls']=32
    write_json(out/'fixture/task.json',task)
    run=out/'run';initial=run_task(task,registry,run,profiles=['base','all']);keep(run,'original')
    candidate=initial['reviews'][0]
    payload={'reviewer':'controlled scripted reviewer, not a human participant','created_at':'2026-10-26T21:00:00+00:00',
        'dataset_manifest_digest':initial['coverage']['input_manifest_digest'],'audit_id':candidate['audit_id'],
        'pair_ref':candidate['pair_ref'],'decision':'confirmed','reason':'Controlled lifecycle acceptance, not a real source annotation'}
    confirmed=import_review(run,payload);cp=Path(confirmed['revision']['path']);keep(cp,'confirmed')
    assert confirmed['coverage']['human_review']['confirmed_records']==1
    assert any(c['claim_type']=='same_source_review' for c in confirmed['claims'])
    rejected=import_review(run,{**payload,'decision':'rejected'});rp=Path(rejected['revision']['path']);keep(rp,'rejected')
    assert not any(c['claim_type']=='same_source_review' for c in rejected['claims'])
    assert rejected['coverage']['human_review']['rejected_records']==1
    revised=resume_run(run,{'actor':'controlled scripted answer','goal':'content_audit'});vp=Path(revised['revision']['path']);keep(vp,'goal_revision')
    assert revised['budget']['spent']['audit_runs']==initial['budget']['spent']['audit_runs']
    assert revised['budget']['spent']['review_pairs']==2
    assert read_json(cp/'report.json')==confirmed
    evidence=list(map(json.loads,(vp/'evidence.jsonl').read_text().splitlines()))
    human=[e for e in evidence if e['kind'].startswith('human.')]
    assert len(human)==1 and human[0]['facts']['decision']=='rejected'
    assert all(read_json(vp/p)==human[0]['facts'] for p in human[0]['source_positions'])
    legacy=None
    if args.legacy_run:
        source=args.legacy_run.resolve();old=verify_run(source,recompute_identity=True)
        assert any(c['claim_type']=='same_source_review' for c in old['claims'])
        copied=out/'legacy-run';shutil.copytree(source,copied,ignore=shutil.ignore_patterns('revisions','latest-revision.json','.revision.lock'))
        keep(copied,'legacy_original')
        current=resume_run(copied,{'actor':'scripted legacy repair fixture','goal':'same_entity_new_view'})
        destination=Path(current['revision']['path']);keep(destination,'legacy_reinterpretation')
        assert not any(c['claim_type']=='same_source_review' for c in current['claims'])
        assert current['revision']['superseded_review_evidence_refs']
        assert current['budget']['spent']['audit_runs']==old['budget']['spent']['audit_runs']
        assert verify_run(source)==old
        legacy={'status':'passed','source_report_unchanged':True,'stale_confirmation_removed_from_new_revision':True}
    receipt={'status':'passed','code_digest':code_digest(),'reports':reports,'legacy':legacy,'model_calls':0,
             'real_agent_experiment':'not_run','human_participants':0,'data_kind':'controlled synthetic image and review lifecycle fixtures',
             'source_review_history_preserved':True,'image_reaudit_for_revisions':False}
    write_json(out/'receipt.json',receipt,exclusive=True);print(json.dumps({'status':'passed','reports':len(reports),'legacy':legacy,'model_calls':0}))


if __name__=='__main__':main()
