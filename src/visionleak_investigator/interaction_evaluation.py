"""Frozen C/D interaction evaluation; deterministic C only, D remains blocked."""
from __future__ import annotations

import json
import resource
from pathlib import Path
import sys
import time

from .common import PROJECT, append_json, digest, file_hash, no_symlink, now, read_json, safe_child, write_json
from .core import execute
from .domain import Registry, input_manifest
from .evaluation_data import verify_frozen
from .integrity import verify_run
from .interaction_scoring import METRIC_VERSION, validate_interaction_truth


def summarize_interaction(rows: list[dict]) -> dict:
    result = {}
    for condition in ('C','D'):
        selected = [r for r in rows if r['condition']==condition]
        scores = [r['score'] for r in selected if 'score' in r]
        if not selected or len(scores)!=len(selected):
            result[condition] = {'status':'unavailable','scheduled_runs':len(selected),'scored_runs':len(scores),
                                 'reason':'All scheduled scores required; blocked/missing runs are not successes'}
            continue
        sums = {k:sum(s[k] for s in scores) for k in ('necessary_questions','necessary_questions_asked','questions_asked','excessive_questions','unanswerable_questions','answers_delivered')}
        risks = {k:sum(s['risk'][k] for s in scores) for k in ('tp','fp','fn','truth_denominator','predicted_pairs')}
        tp,fp,fn = (risks[k] for k in ('tp','fp','fn'))
        fields = [s['field_correct'] for s in scores if s['field_correct'] is not None]
        result[condition] = {'status':'scored','scheduled_runs':len(selected),'scored_runs':len(scores), **sums,
            'failed_runs_in_denominator':sum(not s['usable_output'] for s in scores),
            'goal_correct_runs':sum(s['goal_correct'] for s in scores),'goal_accuracy':sum(s['goal_correct'] for s in scores)/len(scores),
            'field_evaluable_runs':len(fields),'field_accuracy':sum(fields)/len(fields) if fields else None,
            'risk':{**risks,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
                    'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None},
            'unsupported_confirmed_claims':sum(s['unsupported_confirmed_claims'] for s in scores) if all(s['unsupported_confirmed_claims'] is not None for s in scores) else None,
            'human_time_saved_seconds':None, 'interpretation':'Descriptive repeated-run counts, not independent human/Agent gains'}
    return result


def run_interaction(catalog: dict, root: Path, protocol: dict, frozen_path: Path, out: Path, *, partition: str, replay_of: Path | None = None) -> dict:
    start=time.monotonic(); cpu_start=resource.getrusage(resource.RUSAGE_SELF)
    root,out,frozen_path=(no_symlink(p) for p in (root,out,frozen_path))
    if out.exists() or out.is_relative_to(root) or root.is_relative_to(out) or frozen_path.is_relative_to(out):
        raise ValueError('Interaction output must be new and disjoint from suite/freeze')
    frozen=read_json(frozen_path); freeze_sha=file_hash(frozen_path)
    check=verify_frozen(frozen,catalog,root,protocol,partition=partition)
    if protocol['metric_definition']!=METRIC_VERSION or protocol['conditions']!=['C','D']:
        raise ValueError('Interaction evaluation requires a frozen interaction-v1 C/D protocol')
    tasks=[r for r in frozen['catalog']['tasks'] if r['benchmark_partition']==partition]
    if not tasks: raise ValueError('No tasks in selected interaction partition')
    contracts={}
    for row in tasks:
        task=read_json(safe_child(root,row['task_path'])); registry=Registry(read_json(safe_child(root,row['registry_path'])))
        if task['privacy']['remote_model_allowed']: raise ValueError('Local interaction evaluator cannot authorize remote models')
        if any(registry.document(ref).is_relative_to(out) for ref in registry.value.get('documents',{})):
            raise ValueError('Output overlaps a registered document')
        truth=read_json(safe_child(root,row['truth_path']))
        info=validate_interaction_truth(truth,task,input_manifest(registry.dataset(task['dataset_ref']),task['limits']))
        contracts[row['task_id']]={'answers':truth['answerable_questions'],'info':info}
    if replay_of is not None:
        previous=read_json(no_symlink(replay_of)/'evaluation_manifest.json')
        if previous['freeze_digest']!=frozen['freeze_digest'] or previous['benchmark_partition']!=partition:
            raise ValueError('Replay must reference the same frozen interaction partition')
    if partition=='test':
        claim=frozen_path.with_name(frozen_path.name+'.executions')/'interaction-test.json'
        if replay_of is None:
            write_json(claim,{'freeze_digest':frozen['freeze_digest'],'output':str(out),'started_at':now()},exclusive=True)
        elif read_json(claim)['freeze_digest']!=frozen['freeze_digest']:
            raise ValueError('Frozen test execution claim changed')
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/'frozen_config.json',frozen,exclusive=True)
    write_json(out/'source_split_manifest.json',{'sources':catalog['sources'],'components':frozen['catalog']['components']},exclusive=True)
    schedule=[{'task_id':t['task_id'],'condition':c,'repetition':n} for t in tasks for n in range(1,protocol['repetitions']+1) for c in ('C','D')]
    manifest={'schema_version':1,'created_at':now(),'metric_definition':METRIC_VERSION,'freeze_digest':frozen['freeze_digest'],
        'benchmark_partition':partition,'schedule':schedule,'status':'running','model_calls':0,
        'evaluation_role':'replay' if replay_of else 'evaluation','replay_of':str(replay_of) if replay_of else None,
        'answer_policy':'Identical frozen answerable questions for C and future D; broker releases only answers to actually requested questions.',
        'truth_isolation':'Workers receive task/registry or a requested answer payload only; scorer receives truth. Application boundary, not OS secrecy.',
        'human_inputs':'scripted contract, no human participants','review_policy':'Backlog and actual review charges recorded; no unsolicited simulated reviews supplied.',
        'cache':'fresh Core process per task; no shared fingerprints; OS cache not flushed'}
    write_json(out/'evaluation_manifest.json',manifest,exclusive=True)
    for name in ('per_run.jsonl','failures.jsonl','gate_checks.jsonl'): (out/name).touch(exist_ok=False)
    rows=[]; rejected=None; by_id={t['task_id']:t for t in tasks}

    def gate(phase,item):
        try:
            if file_hash(frozen_path)!=freeze_sha: raise ValueError('Frozen file changed during interaction evaluation')
            verify_frozen(frozen,catalog,root,protocol,partition=partition)
        except (ValueError,OSError) as error:
            append_json(out/'gate_checks.jsonl',{'phase':phase,'item':item,'status':'rejected','error':str(error)});raise
        append_json(out/'gate_checks.jsonl',{'phase':phase,'item':item,'status':'passed'})

    def save(row):
        rows.append(row);append_json(out/'per_run.jsonl',row)
        if row['state']=='FAILED':append_json(out/'failures.jsonl',row)

    try:
        for item in schedule:
            gate('before_task',item)
            if item['condition']=='D':
                save({**item,'state':'blocked','reason':'No authorized provider/adapter; no scripted D substitute','model_calls':0});continue
            taskrow=by_id[item['task_id']];taskpath=safe_child(root,taskrow['task_path']);regpath=safe_child(root,taskrow['registry_path'])
            task=read_json(taskpath); contract=contracts[item['task_id']]
            base=out/'runs'/item['task_id']/f'r{item["repetition"]:02d}'/'C';base.mkdir(parents=True,exist_ok=False)
            transcript=base/'transcript.jsonl';transcript.touch(exist_ok=False)
            anchor=base/'run';current=anchor;processes=[];failure=None;report=None;delivered=set()
            tick=time.monotonic()
            def invoke(argv,label):
                directory=base/'processes'/label
                remaining=task['limits']['max_tool_wall_seconds']+30-(time.monotonic()-tick)
                if remaining<=0:raise ValueError('Interaction task wall budget exhausted')
                result=execute(argv,PROJECT,directory,remaining);processes.append({'record':str(directory.relative_to(out)),'result':result})
                if result['error'] or result['exit_code'] not in (0,2,3):raise ValueError('Interaction worker failed: '+str(result['error'] or result['exit_code']))
                return result,directory
            try:
                invoke([sys.executable,'-m','visionleak_investigator.evaluation_worker','--task',str(taskpath),'--registry',str(regpath),'--out',str(anchor),'--condition','C'],'initial')
                for turn in range(task['limits']['max_agent_steps']+1):
                    gate('before_observation',item);report=verify_run(current)
                    questions=report['questions'];available={q['question_code']:contract['answers'][q['question_code']] for q in questions if q['question_code'] in contract['answers'] and q['question_code'] not in delivered}
                    observation={'turn':turn,'run':str(current.relative_to(base)),'report_digest':digest(report),
                                 'questions':questions,'answered_questions':[],'answer_path':None,'answer_result':None}
                    if not available or turn==task['limits']['max_agent_steps']:
                        append_json(transcript,observation);break
                    payload={'actor':'fixed scripted answer broker; no human participant'}
                    for answer in available.values():payload.update(answer)
                    answerpath=base/f'answers/{turn:02d}.json';write_json(answerpath,payload,exclusive=True)
                    observation['answer_path']=str(answerpath.relative_to(base))
                    try:
                        _,directory=invoke([sys.executable,'-m','visionleak_investigator.cli','resume','--run',str(anchor),'--answers',str(answerpath)],f'answer-{turn:02d}')
                        observation['answer_result']=str((directory/'result.json').relative_to(base))
                        destination=Path(read_json(directory/'stdout.log')['report']).parent
                        if not destination.is_relative_to(anchor/'revisions'):raise ValueError('Answer revision escaped run')
                        current=destination;observation['answered_questions']=sorted(available);delivered.update(available)
                    finally:append_json(transcript,observation)
                    gate('after_answer',item)
                report=verify_run(current)
                if report['budget']['spent']['questions']>task['limits']['max_questions'] or report['budget']['spent']['review_pairs']>task['limits']['max_review_pairs']:
                    raise ValueError('Interaction question/review budget exceeded')
            except (ValueError,OSError,KeyError) as error:failure=str(error)
            row={**item,'state':'FAILED' if failure else report['state'],'failure':failure,
                 'run':str(current.relative_to(out)),'transcript':str(transcript.relative_to(out)),
                 'processes':processes,'task_wall_seconds':time.monotonic()-tick,
                 'costs':report['budget']['spent'] if report else None,'costs_complete':failure is None,'model_calls':0}
            measured=[p['result']['resources'] for p in processes if p['result'].get('resources')]
            rss=[p['tree_rss_peak_bytes'] for p in measured if p.get('tree_rss_peak_bytes') is not None]
            row['worker_resources']={'cpu_seconds':sum(p['cpu_seconds'] for p in measured) if measured else None,
                'cpu_complete':bool(processes) and len(measured)==len(processes),
                'max_sampled_tree_rss_bytes':max(rss) if rss else None,'rss_complete':bool(processes) and len(rss)==len(processes),
                'scope':'All initial/resume subprocess trees; broker CPU recorded separately at pipeline level; sampled RSS is not a hard limit'}
            try:gate('before_scoring',item)
            except (ValueError,OSError) as error:
                row.update(state='FAILED',failure=str(error),costs_complete=False);save(row);raise
            scorepath=base/'score.json';scorer=base/'scorer'
            argv=[sys.executable,'-m','visionleak_investigator.interaction_scoring','--task',str(taskpath),'--registry',str(regpath),
                '--truth',str(safe_child(root,taskrow['truth_path'])),'--run',str(current),'--transcript',str(transcript),'--out',str(scorepath)]
            if failure:argv.extend(['--failure',failure])
            scored=execute(argv,PROJECT,scorer,60)
            row.update(scorer_record=str(scorer.relative_to(out)),scoring_resources=scored.get('resources'))
            if scored['exit_code']==0 and scored['error'] is None:
                row['score']=read_json(scorepath)
            else:
                row.update(state='FAILED',failure='Interaction scorer failed; no success-only aggregate')
            save(row);gate('after_task',item)
    except (ValueError,OSError,KeyError) as error:
        rejected=str(error)
    done={(r['task_id'],r['condition'],r['repetition']) for r in rows}
    for item in schedule:
        if (item['task_id'],item['condition'],item['repetition']) not in done:
            save({**item,'state':'blocked' if item['condition']=='D' else 'not_run','reason':rejected or 'Schedule interrupted','model_calls':0})
    status='rejected' if rejected else 'completed_with_failures' if any(r['state']=='FAILED' for r in rows) else 'completed'
    cpu_end=resource.getrusage(resource.RUSAGE_SELF)
    metrics={'status':status,'rejection':rejected,'metric_definition':METRIC_VERSION,
             'quality':None if rejected else summarize_interaction(rows),'scheduled_runs':len(schedule),
             'declared_independent_components':check['independent_components'],'model_calls':0,'real_agent_experiment':'not_run',
             'human_participants':0,'human_time_saved_seconds':None,'wall_seconds':time.monotonic()-start,
             'broker_cpu_seconds':cpu_end.ru_utime+cpu_end.ru_stime-cpu_start.ru_utime-cpu_start.ru_stime,
             'pipeline_peak_rss_bytes':None,
             'limitations':['Separate interaction benchmark; not combined with detection precision/recall.',
                            'Scripted answers are not model decisions or measured human labor.',
                            'Failed/unresolved cases remain in denominators; missing scores suppress aggregates.',
                            'Repeated tasks are not independent sampling units; no significance or research-gain claim.']}
    write_json(out/'metrics.json',metrics,exclusive=True)
    write_json(out/'costs.json',[{k:r.get(k) for k in ('task_id','condition','repetition','state','costs','costs_complete','processes','worker_resources','scoring_resources','task_wall_seconds')} for r in rows],exclusive=True)
    write_json(out/'evaluation_manifest.json',{**manifest,'status':status,'finished_at':now(),'rejection':rejected})
    (out/'summary.md').write_text('# Interaction evaluation\n\n'+json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return metrics
