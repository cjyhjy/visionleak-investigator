"""Independent deterministic evaluator. Truth is never an input to run_task."""
from __future__ import annotations
import itertools,json,sys
from pathlib import Path
from .common import PROJECT,digest,file_hash,read_json,write_json,append_json
from .demo import make_task
from .evaluation_data import execution_identity
from .core import execute

def resource_totals(rows: list[dict]) -> dict:
    totals={}
    for condition in ('A','B','C','D'):
        selected=[r for r in rows if r['condition']==condition and r['state']!='blocked']
        measured=[r['full_task_resources'] for r in selected if r.get('full_task_resources')]
        rss=[m['tree_rss_peak_bytes'] for m in measured if m.get('tree_rss_peak_bytes') is not None]
        totals[condition]={'attempted_runs':len(selected),'cpu_measured_runs':len(measured),
                           'cpu_seconds':sum(m['cpu_seconds'] for m in measured) if measured else None,
                           'cpu_total_complete':len(measured)==len(selected) and bool(selected),
                           'rss_sampled_runs':len(rss),'max_sampled_tree_rss_bytes':max(rss) if rss else None,
                           'scope':'whole isolated task process including Python and child Core tools; RSS sampling limitations apply'}
    return totals

def comparable(entries: list[tuple[dict,dict]]) -> None:
    signatures={(m['core_lock_digest'],m['runtime_lock_digest'],m['code_digest'],m['dataset_manifest_digest'],digest(t['limits'])) for m,t in entries}
    if len(signatures)!=1:raise ValueError('Incomparable Core lock, implementation, input identity or total limits')

def check_execution(frozen: dict, out: Path, manifest: dict | None = None) -> None:
    current=execution_identity()
    changed=[k for k,v in current.items() if frozen[k]!=v]
    if manifest:
        changed.extend(k for k in ('core_lock_digest','runtime_lock_digest','code_digest') if manifest[k]!=frozen[k])
    if changed:
        append_json(out/'rejected-comparisons.jsonl',{'reason':'Frozen execution changed','fields':sorted(set(changed))})
        raise ValueError('Execution changed during evaluation; results must not be aggregated')

def score_pairs(predicted: set,truth: set) -> dict:
    tp=len(predicted&truth);fp=len(predicted-truth);fn=len(truth-predicted)
    precision=tp/len(predicted) if predicted else None;recall=tp/len(truth) if truth else None
    return {'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,'truth_denominator':len(truth),'predicted_pairs':len(predicted)}

def run_engineering_suite(out: Path,count: int=12) -> dict:
    if not 1<=count<=100:raise ValueError('Engineering suite size limit')
    out.mkdir(parents=True,exist_ok=False)
    frozen={'conditions':['A','B','C','D'],'D':{'status':'blocked','reason':'No authorized model/provider/usage budget'},'E':{'status':'not_run','reason':'Second phase'},'core_lock_digest':file_hash(PROJECT/'core.lock.json'),'runtime_lock_digest':file_hash(PROJECT/'core.runtime.lock.json'),'rules':'v1: base; explicit request orientation -> transform; local crop -> local; both -> all','threshold':6,'seed_start':2026102600,'task_count':count,'benchmark_partition':'development','cache':'fresh CLI process, no shared fingerprints; OS cache not flushed','claims':'engineering smoke only, no independent natural-scene research claim'}
    frozen.update(execution_identity())
    write_json(out/'frozen_config.json',frozen,exclusive=True)
    rows=[];sources=[]
    for i in range(count):
        case=out/f'tasks/t{i:03d}';task,registry=make_task(case,2026102600+i)
        task['task_id']=f't{i:03d}'
        if i%3==1:task['request_text']='请检查图像内容及可能的旋转、镜像。'
        elif i%3==2:task['request_text']='请检查图像内容及可能的旋转、镜像、裁切。'
        if i==count-2:task['limits']['max_comparisons_total']=1
        if i==count-1:(case/'images/test/007.png').write_text('deliberately invalid engineering fixture')
        write_json(case/'task.json',task)
        names=['train/001.png','test/002.png','validation/003.png','test/004.png','validation/005.png','train/006.png']
        pairs={tuple(sorted(p)) for p in itertools.combinations(names,2) if p[0].split('/')[0]!=p[1].split('/')[0]}
        exact={p for p in pairs if set(p)<={'train/001.png','test/002.png','validation/003.png'}}
        related={p for p in pairs if 'train/006.png' not in p}-exact
        truth={'exact':sorted(exact),'related_excluding_exact':sorted(related),'source':'generator provenance','benchmark_partition':'development'}
        truthpath=out/'evaluator-truth'/f't{i:03d}.json';write_json(truthpath,truth,exclusive=True)
        sources.append({'task_id':task['task_id'],'source_group':f'procedural-seed-{2026102600+i}','benchmark_partition':'development','kind':'synthetic controlled; not an independent photograph','license':'self-generated','truth_digest':file_hash(truthpath)})
        manifests=[]
        for condition in ['A','B','C']:
            check_execution(frozen,out)
            dest=out/'runs'/task['task_id']/condition
            process_result=None;m=None
            try:
                process_result=execute([sys.executable,'-m','visionleak_investigator.evaluation_worker',
                    '--task',str(case/'task.json'),'--registry',str(case/'registry.json'),
                    '--out',str(dest),'--condition',condition],PROJECT,out/'processes'/task['task_id']/condition,
                    task['limits']['max_tool_wall_seconds']+30)
                if process_result['error']:raise ValueError('Isolated task process failed: '+process_result['error'])
                result=read_json(dest/'report.json')
                if process_result['exit_code']!={'COMPLETED':0,'PARTIAL':2,'WAITING_USER':3,'FAILED':1}[result['state']]:raise ValueError('Worker exit/report status mismatch')
                m=read_json(dest/'manifest.json');manifests.append((m,task))
                evidence=[json.loads(s) for s in (dest/'evidence.jsonl').read_text().splitlines()]
                predicted_exact={tuple(sorted(e['files'])) for e in evidence if e['kind'] in ('core.byte_identical','core.pixel_identical')}
                predicted_approx={tuple(sorted(e['files'])) for e in evidence if 'candidate' in e['kind']}-exact
                row={'task_id':task['task_id'],'condition':condition,'state':result['state'],'exact':score_pairs(predicted_exact,exact),'related_excluding_exact':score_pairs(predicted_approx,related),'candidate_burden':len({e['pair_key'] for e in evidence if 'candidate' in e['kind']}),'costs':result['budget']['spent'],'model_execution':'not_run','run':str(dest.relative_to(out))}
            except Exception as e:
                row={'task_id':task['task_id'],'condition':condition,'state':'FAILED','error':str(e)}
            check_execution(frozen,out,m)
            row['full_task_resources']=process_result.get('resources') if process_result else None
            row['full_task_wall_seconds']=process_result.get('wall_seconds') if process_result else None
            row['process_record']=str((out/'processes'/task['task_id']/condition).relative_to(out))
            if row['state']=='FAILED':append_json(out/'failures.jsonl',row)
            rows.append(row);append_json(out/'per_run.jsonl',row)
        if manifests:
            try:comparable(manifests)
            except ValueError:
                append_json(out/'rejected-comparisons.jsonl',{'task_id':task['task_id'],'reason':'Incomparable conditions'})
                raise
        append_json(out/'comparison_checks.jsonl',{'task_id':task['task_id'],'accepted_manifests':len(manifests),'status':'passed' if len(manifests)==3 else 'partial','failure_rows_preserved':True})
        row={'task_id':task['task_id'],'condition':'D','state':'blocked','reason':'No model authorization','model_execution':'not_run'};rows.append(row);append_json(out/'per_run.jsonl',row)
    write_json(out/'source_split_manifest.json',sources,exclusive=True)
    check_execution(frozen,out)
    summary={'status':'engineering_only','tasks':count,'independent_photographic_sources':0,'synthetic_source_groups':count,'runs':{c:{s:sum(r['condition']==c and r['state']==s for r in rows) for s in ['COMPLETED','PARTIAL','WAITING_USER','FAILED','blocked']} for c in ['A','B','C','D']},'real_agent_experiment':'not_run','research_gain':'not_established','cpu_seconds':'not_measured','peak_rss':'not_measured; no parent-only RSS claim','limitations':['Controlled procedural images only.','No independent validation/test partition collected.','No statistical significance or natural leakage claim.','D/E not run, so no Agent-vs-rule comparison.']}
    write_json(out/'evaluation_manifest.json',{'config_digest':digest(frozen),'source_split_digest':digest(sources),'truth_isolation':'evaluator-truth is outside dataset roots and document registry; application-level isolation, not admin-proof'},exclusive=True)
    summary['cpu_seconds']='measured per isolated task; see resources_by_condition and per_run.jsonl'
    summary['peak_rss']='sampled process-tree sum, not parent-only; shared pages may be counted twice and short peaks missed'
    summary['resources_by_condition']=resource_totals(rows)
    write_json(out/'metrics.json',summary,exclusive=True);write_json(out/'costs.json',[{k:r[k] for k in ('task_id','condition','costs','full_task_resources','full_task_wall_seconds','process_record') if k in r} for r in rows],exclusive=True)
    if not (out/'failures.jsonl').exists():(out/'failures.jsonl').touch()
    (out/'summary.md').write_text('# 本地工程评测\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n\n逐任务原始分母、失败与成本见 per_run.jsonl。A=base 一次；B=all 一次；C=规则；D 因未授权不运行。\n')
    return summary
