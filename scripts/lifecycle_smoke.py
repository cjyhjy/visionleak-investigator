"""Real-Core lifecycle/negative acceptance, with explicitly controlled interruption."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from visionleak_investigator.common import PROJECT,read_json,write_json,file_hash,digest
from visionleak_investigator.demo import make_task,make_hard_negative_task
from visionleak_investigator.domain import Registry,input_manifest
from visionleak_investigator.core import execute
from visionleak_investigator.workflow import run_task,code_digest
from visionleak_investigator.interaction import resume_run
from visionleak_investigator.recovery import recover_interrupted
from visionleak_investigator.integrity import verify_run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--historical-run',type=Path)
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    reports=[];cases=[]
    def keep(run,label):
        r=verify_run(run,recompute_identity=True)
        reports.append({'case':label,'run':run.relative_to(out).as_posix(),'state':r['state'],
            'manifest_sha256':file_hash(run/'manifest.json'),'report_sha256':file_hash(run/'report.json')})
        return r
    for kind in ('fresh','historical') if args.historical_run else ('fresh',):
        run=out/kind/'run'
        if kind=='fresh':
            task,reg=make_task(out/kind/'fixture',76000)
            task['request_text']='受控合成生命周期验收；回答为脚本输入，无真人或模型参与。'
            write_json(out/kind/'fixture/task.json',task)
            run_task(task,reg,run,profiles=['base','all'])
        else:
            source=args.historical_run.resolve();verify_run(source,recompute_identity=True)
            shutil.copytree(source,run,ignore=shutil.ignore_patterns('revisions','latest-revision.json','.revision.lock'))
        before=keep(run,kind+'_original');manifest=read_json(run/'manifest.json')
        original_tools={str(f.relative_to(run)):file_hash(f) for f in (run/'tools').rglob('*') if f.is_file()}
        revised=resume_run(run,{'actor':'controlled scripted fixture, not a human participant','goal':'same_entity_new_view'})
        dest=Path(revised['revision']['path']);keep(dest,kind+'_revision')
        current=read_json(dest/'manifest.json')
        assert current['code_digest']==code_digest()
        assert current['image_evidence_origin']['investigator_code_digest']==manifest['code_digest']
        assert current['parent_report_digest']==digest(before)
        assert revised['budget']['spent']['audit_runs']==before['budget']['spent']['audit_runs']
        assert all(file_hash(dest/name)==sha for name,sha in original_tools.items())
        if kind=='historical':assert manifest['code_digest']!=current['code_digest']
        cases.append({'case':kind+'_revision','status':'passed','original_code_digest':manifest['code_digest'],
            'processor_code_digest':current['code_digest'],'evidence_code_digest':current['image_evidence_origin']['investigator_code_digest'],
            'core_reexecuted_for_revision':False,'historical_source':str(args.historical_run) if kind=='historical' else None})
    task,reg=make_task(out/'recovery/fixture',76001)
    task['request_text']='受控合成中断恢复验收；删除本次新建的最终报告以注入故障，无真实业务事故或模型参与。'
    write_json(out/'recovery/fixture/task.json',task)
    run=out/'recovery/run';initial=run_task(task,reg,run)
    write_json(out/'recovery/report-before-controlled-removal.json',initial,exclusive=True)
    (run/'report.json').unlink()  # Only this newly created synthetic run, never a user or historical report.
    result=recover_interrupted(run);keep(run,'conservative_recovery')
    assert not result['claims'] and (run/'evidence.jsonl').read_bytes()==b''
    assert not read_json(run/'proposal.json')['proposed_exclusions']
    assert recover_interrupted(run)==result
    revised=resume_run(run,{'actor':'scripted recovery fixture','goal':'content_audit'})
    dest=Path(revised['revision']['path']);keep(dest,'revision_after_recovery')
    assert not revised['revision']['image_evidence_reused'] and not revised['claims']
    assert not read_json(dest/'proposal.json')['proposed_exclusions']
    cases.append({'case':'conservative_recovery','status':'passed','interruption_kind':'controlled final-artifact removal, not an observed production crash',
        'raw_records_preserved':len(result['recovery']['preserved_files']),'accepted_image_evidence_count':0,
        'core_reexecuted':False,'idempotent':True})
    task,reg=make_hard_negative_task(out/'negative/fixture')
    before=input_manifest(Registry(reg).dataset(task['dataset_ref']),task['limits'])
    run=out/'negative/run';report=run_task(task,reg,run);keep(run,'hard_negatives')
    empty={'coverage':'exhaustive','positive_pairs':[],'negative_pairs':[]}
    truth={'schema_version':1,'task_id':task['task_id'],'dataset_manifest_digest':before['digest'],'goal':task['goal'],
           'basis':{'kind':'synthetic_generation','description':'Four separately constructed controlled negative records; not natural-scene identity labels.'},
           'exact':empty,'related_excluding_exact':empty,'entity_goal_conflict':empty}
    truthpath=out/'evaluator-truth/negative.json';write_json(truthpath,truth,exclusive=True)
    result=execute([sys.executable,'-m','visionleak_investigator.evaluation_scoring',
        '--task',str(out/'negative/fixture/task.json'),'--registry',str(out/'negative/fixture/registry.json'),
        '--truth',str(truthpath),'--run',str(run),'--out',str(out/'negative/score.json')],PROJECT,out/'negative/scorer',60)
    assert result['exit_code']==0 and result['error'] is None
    score=read_json(out/'negative/score.json')
    assert score['exact']['predicted_pairs']==0 and score['related_excluding_exact']['fp']>0
    assert score['related_excluding_exact']['precision']==0 and score['related_excluding_exact']['recall'] is None
    assert all(c['status']=='candidate' for c in report['claims'])
    assert input_manifest(Registry(reg).dataset(task['dataset_ref']),task['limits'])==before
    cases.append({'case':'hard_negatives','status':'passed','known_false_candidates':score['related_excluding_exact']['fp'],
        'candidate_burden':score['candidate_burden'],'exact_predictions':0,'score':'negative/score.json'})
    receipt={'status':'passed','code_digest':code_digest(),'model_calls':0,'real_agent_experiment':'not_run',
        'data_kind':'self-generated controlled synthetic fixtures and optional verified historical synthetic evidence reuse',
        'human_inputs':'scripted fixture answers, no human participant','cases':cases,'reports':reports}
    write_json(out/'receipt.json',receipt,exclusive=True)
    print(json.dumps({'status':'passed','reports':len(reports),'model_calls':0,'cases':cases},ensure_ascii=False))


if __name__=='__main__':main()
