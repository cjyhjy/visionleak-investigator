import copy
import json
from pathlib import Path

import pytest

from visionleak_investigator.common import read_json, write_json
from visionleak_investigator.domain import Registry, input_manifest
from visionleak_investigator.evaluation_data import freeze_catalog
from visionleak_investigator.interaction_evaluation import run_interaction
from visionleak_investigator.interaction_fixture import make_interaction_suite
from visionleak_investigator.interaction_scoring import score_interaction, validate_interaction_truth, validate_transcript


def suite(tmp_path, *, single=False):
    root=tmp_path/'suite';catalog,protocol=make_interaction_suite(root)
    if single:
        catalog['tasks'][0]['benchmark_partition']='validation'
        catalog['tasks'][10]['benchmark_partition']='development'
    frozen=tmp_path/'frozen.json';freeze_catalog(catalog,root,protocol,frozen)
    return root,catalog,protocol,frozen


def test_real_interaction_counts_missingness_overclarification_and_no_model(tmp_path):
    root,catalog,protocol,frozen=suite(tmp_path)
    out=tmp_path/'results'
    result=run_interaction(catalog,root,protocol,frozen,out,partition='development')
    assert result['status']=='completed'
    quality=result['quality']['C']
    assert quality['scheduled_runs']==10 and quality['goal_correct_runs']==8
    assert quality['excessive_questions']==1
    assert quality['necessary_questions']-quality['necessary_questions_asked']==2
    assert quality['risk']['fn']==27 and quality['unsupported_confirmed_claims']==0
    assert result['quality']['D']['status']=='unavailable' and result['model_calls']==0
    assert result['human_time_saved_seconds'] is None
    rows=list(map(json.loads,(out/'per_run.jsonl').read_text().splitlines()))
    assert sum(r['state']=='blocked' for r in rows)==10
    for row in rows:
        if row['condition']=='D':continue
        assert row['costs']['audit_runs']==1 and row['costs']['questions']<=2
        assert row['score']['budget_respected']
        assert all('--truth' not in p['result']['argv'] for p in row['processes'])
        truth=read_json(root/'evaluator-truth'/f'{row["task_id"]}.json')
        assert validate_transcript(out/row['transcript'],truth)
    # The frozen answers cannot be substituted after execution while keeping valid transcripts.
    truth=read_json(root/'evaluator-truth/t001.json')
    truth['answerable_questions']['clarify_goal']['goal']='content_audit'
    with pytest.raises(ValueError,match='Delivered answer'):
        validate_transcript(out/'runs/t001/r01/C/transcript.jsonl',truth)


def test_interaction_contract_rejects_inconsistent_questions_answers_and_labels(tmp_path):
    root,catalog,protocol,frozen=suite(tmp_path)
    task=read_json(root/'tasks/t000/task.json');reg=read_json(root/'tasks/t000/registry.json')
    manifest=input_manifest(Registry(reg).dataset(task['dataset_ref']),task['limits'])
    truth=read_json(root/'evaluator-truth/t000.json')
    for change in ('questions','answer','duplicate','foreign'):
        bad=copy.deepcopy(truth)
        if change=='questions':bad['necessary_questions']=['clarify_goal']
        if change=='answer':bad['answerable_questions']['clarify_goal']['goal']='content_audit'
        if change=='duplicate':bad['risk_positive_pairs'].append(list(reversed(bad['risk_positive_pairs'][0])))
        if change=='foreign':bad['risk_positive_pairs']=[['train/001.png','test/unknown.png']]
        with pytest.raises(ValueError):validate_interaction_truth(bad,task,manifest)
    score=score_interaction(task,reg,truth,tmp_path/'absent',[],failure='unit-scoring failure fixture; no runtime predictions')
    assert score['risk']['fn']==8 and not score['goal_correct']
    assert score['unsupported_confirmed_claims'] is None


def test_failed_real_subprocess_keeps_cost_record_and_positive_denominator(tmp_path,monkeypatch):
    from visionleak_investigator import interaction_evaluation as runner
    root,catalog,protocol,frozen=suite(tmp_path,single=True)
    original=runner.execute
    def fail_initial(argv,cwd,directory,timeout):
        # Actual OS spawn failure, not a fake Core result or model trajectory.
        if 'visionleak_investigator.evaluation_worker' in argv:
            argv=[str(tmp_path/'deliberately-missing-executable'),*argv[1:]]
        return original(argv,cwd,directory,timeout)
    monkeypatch.setattr(runner,'execute',fail_initial)
    result=runner.run_interaction(catalog,root,protocol,frozen,tmp_path/'results',partition='validation')
    assert result['status']=='completed_with_failures'
    assert result['quality']['C']['failed_runs_in_denominator']==1
    assert result['quality']['C']['risk']['fn']==8
    rows=list(map(json.loads,(tmp_path/'results/per_run.jsonl').read_text().splitlines()))
    assert rows[0]['processes'][0]['result']['error']=='FileNotFoundError'
    assert rows[0]['costs_complete'] is False


def test_interaction_freeze_drift_retains_attempt_and_suppresses_quality(tmp_path,monkeypatch):
    from visionleak_investigator import interaction_evaluation as runner
    root,catalog,protocol,frozen=suite(tmp_path,single=True)
    original=runner.execute
    def change_truth_after_real_worker(argv,cwd,directory,timeout):
        result=original(argv,cwd,directory,timeout)
        if 'visionleak_investigator.evaluation_worker' in argv:
            path=root/'evaluator-truth/t000.json';truth=read_json(path)
            truth['basis']['description']+=' controlled drift injection after real worker'
            write_json(path,truth)
        return result
    monkeypatch.setattr(runner,'execute',change_truth_after_real_worker)
    result=runner.run_interaction(catalog,root,protocol,frozen,tmp_path/'results',partition='validation')
    assert result['status']=='rejected' and result['quality'] is None
    rows=list(map(json.loads,(tmp_path/'results/per_run.jsonl').read_text().splitlines()))
    assert len(rows)==2 and rows[0]['state']=='FAILED' and rows[0]['processes']
    assert rows[1]['state']=='blocked'


def test_real_worker_contract_substitution_is_a_failed_scored_attempt(tmp_path,monkeypatch):
    from visionleak_investigator import interaction_evaluation as runner
    root,catalog,protocol,frozen=suite(tmp_path,single=True)
    substituted=read_json(root/'tasks/t000/task.json')
    substituted['limits']['max_questions']+=1
    path=tmp_path/'controlled-wrong-worker-task.json';write_json(path,substituted)
    original=runner.execute
    def wrong_real_worker(argv,cwd,directory,timeout):
        if 'visionleak_investigator.evaluation_worker' in argv:
            argv=list(argv);argv[argv.index('--task')+1]=str(path)
        return original(argv,cwd,directory,timeout)
    monkeypatch.setattr(runner,'execute',wrong_real_worker)
    out=tmp_path/'results';result=runner.run_interaction(catalog,root,protocol,frozen,out,partition='validation')
    assert result['status']=='completed_with_failures'
    assert result['quality']['C']['failed_runs_in_denominator']==1
    assert result['quality']['C']['risk']['fn']==8
    row=json.loads((out/'per_run.jsonl').read_text().splitlines()[0])
    assert row['state']=='FAILED' and 'task/limits' in row['failure']
    assert row['processes'] and row['costs'] and not row['costs_complete']
    assert row['score']['unsupported_confirmed_claims'] is None


def test_interaction_test_requires_explicit_replay_and_keeps_d_blocked(tmp_path):
    root,catalog,protocol,frozen=suite(tmp_path)
    first=run_interaction(catalog,root,protocol,frozen,tmp_path/'first',partition='test')
    assert first['status']=='completed'
    with pytest.raises(FileExistsError):
        run_interaction(catalog,root,protocol,frozen,tmp_path/'implicit',partition='test')
    assert not (tmp_path/'implicit').exists()
    replay=run_interaction(catalog,root,protocol,frozen,tmp_path/'replay',partition='test',replay_of=tmp_path/'first')
    assert replay['status']=='completed' and replay['quality']['D']['status']=='unavailable'
    assert read_json(tmp_path/'replay/evaluation_manifest.json')['evaluation_role']=='replay'
