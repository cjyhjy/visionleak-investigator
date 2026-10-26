"""Catalog execution uses real Core; deliberate score/freeze negatives stay explicit."""
import copy
import json
from pathlib import Path

import pytest

from visionleak_investigator.common import file_hash, read_json, write_json
from visionleak_investigator.evaluation_data import freeze_catalog
from visionleak_investigator.evaluation_fixture import make_catalog_suite
from visionleak_investigator.evaluation_runner import run_catalog
from visionleak_investigator.evaluation_scoring import score_labels, validate_truth
from visionleak_investigator.domain import Registry, input_manifest


def prepared(tmp_path, count=3):
    root=tmp_path/'suite'
    catalog,protocol=make_catalog_suite(root,count=count,seed_start=74000)
    frozen=tmp_path/'frozen.json'
    freeze_catalog(catalog,root,protocol,frozen)
    return root,catalog,protocol,frozen


def test_real_catalog_runs_same_inputs_and_separate_scorer(tmp_path):
    root,catalog,protocol,frozen=prepared(tmp_path)
    result=run_catalog(catalog,root,protocol,frozen,tmp_path/'results',partition='development')
    assert result['status']=='completed_no_model'
    assert result['runs']['D']['blocked']==1
    rows=[json.loads(s) for s in (tmp_path/'results/per_run.jsonl').read_text().splitlines()]
    measured=[r for r in rows if r['condition']!='D']
    assert len(measured)==3 and all(r['score']['exact']['truth_denominator']==3 for r in measured)
    manifests=[]
    for row in measured:
        dest=tmp_path/'results'/row['run']
        manifests.append(read_json(dest/'manifest.json'))
        worker=read_json(tmp_path/'results'/row['process_record']/'invocation.json')
        assert not any('truth' in a or 'catalog.json' in a or 'frozen' in a for a in worker['argv'])
        assert (tmp_path/'results'/row['scorer_record']/'result.json').is_file()
        assert row['full_task_resources']['cpu_seconds']>=0
        assert row['score']['source_unchanged'] is True
        assert read_json(dest/'task.json')==read_json(root/catalog['tasks'][0]['task_path'])
    assert len({m['dataset_manifest_digest'] for m in manifests})==1
    b=next(r for r in measured if r['condition']=='B')
    assert b['costs']['audit_runs']==1
    assert list(read_json(tmp_path/'results'/b['run']/'report.json')['coverage']['profiles'])==['all']
    assert result['quality']['A']['exact']['truth_denominator']==3
    assert result['declared_independent_components']==1


def test_partial_labels_unknown_candidates_and_empty_denominators():
    a=('test/a','train/b');b=('test/a','train/c');c=('test/a','train/d')
    labels={'coverage':'partial','positive_pairs':[list(a)],'negative_pairs':[list(b)]}
    score=score_labels({a,b,c},labels,3)
    assert score['tp']==1 and score['fp']==1 and score['unknown_predicted_pairs']==1
    assert score['precision'] is None and score['recall'] is None and score['f1'] is None
    assert score['labeled_subset']['precision']==0.5
    assert score['truth_denominator']==1 and score['truth_denominator_complete'] is False
    empty=score_labels(set(),{'coverage':'exhaustive','positive_pairs':[],'negative_pairs':[]},0)
    assert empty['precision'] is None and empty['recall'] is None and empty['f1'] is None


def test_truth_rejects_unsupported_pairs_and_task_binding(tmp_path):
    root,catalog,_,_=prepared(tmp_path)
    row=catalog['tasks'][0];task=read_json(root/row['task_path'])
    registry=Registry(read_json(root/row['registry_path']))
    manifest=input_manifest(registry.dataset(task['dataset_ref']),task['limits'])
    original=read_json(root/row['truth_path'])
    bad=copy.deepcopy(original);bad['exact']['positive_pairs'].append(['train/001.png','train/006.png'])
    with pytest.raises(ValueError,match='cross-split'):validate_truth(bad,task,manifest)
    bad=copy.deepcopy(original);bad['related_excluding_exact']['positive_pairs'].append(original['exact']['positive_pairs'][0])
    with pytest.raises(ValueError,match='exact'):validate_truth(bad,task,manifest)
    bad=copy.deepcopy(original);bad['dataset_manifest_digest']='0'*64
    with pytest.raises(ValueError,match='identity'):validate_truth(bad,task,manifest)


def test_low_budget_retains_full_denominator_and_test_replay_is_explicit(tmp_path):
    root,catalog,protocol,frozen=prepared(tmp_path)
    first=run_catalog(catalog,root,protocol,frozen,tmp_path/'test-first',partition='test')
    assert first['runs']['A']['PARTIAL']==1
    assert first['quality']['A']['exact']['truth_denominator']==3
    assert first['quality']['A']['exact']['recall']<1
    with pytest.raises(ValueError,match='already attempted'):
        run_catalog(catalog,root,protocol,frozen,tmp_path/'test-second',partition='test')
    replay=run_catalog(catalog,root,protocol,frozen,tmp_path/'test-replay',partition='test',replay_of=tmp_path/'test-first')
    assert replay['evaluation_role']=='replay' and replay['research_gain']=='not_established'


def test_frozen_drift_and_output_overlap_reject_before_execution(tmp_path):
    root,catalog,protocol,frozen=prepared(tmp_path)
    with pytest.raises(ValueError,match='disjoint'):
        run_catalog(catalog,root,protocol,frozen,root/'results',partition='development')
    assert not (root/'results').exists()
    truth=root/catalog['tasks'][0]['truth_path'];truth.write_bytes(truth.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='changed'):
        run_catalog(catalog,root,protocol,frozen,tmp_path/'results',partition='development')
    assert not (tmp_path/'results').exists()


def test_entity_goal_truth_scores_actual_metadata_claims(tmp_path):
    from visionleak_investigator.evaluation_scoring import score_run
    from visionleak_investigator.workflow import run_task
    root,catalog,protocol,_=prepared(tmp_path)
    row=catalog['tasks'][0];task=read_json(root/row['task_path']);reg=read_json(root/row['registry_path'])
    task.update(goal='new_entity_generalization',entity_key='entity_id',entity_key_confirmed=True,
                entity_key_evidence_refs=['entity-confirmation'],metadata_ref='metadata')
    reg['confirmations']['user.local-task']['goal']=task['goal']
    reg['confirmations']['entity-confirmation']={'kind':'user.entity_key_confirmation','entity_key':'entity_id','actor':'synthetic test fixture'}
    paths=sorted(row['image_sources']);metadata=root/'entities.csv'
    metadata.write_text('file_id,relative_path,entity_id\n'+''.join(f'f{i},{name},{"same" if name in ("train/006.png","test/004.png") else str(i)}\n' for i,name in enumerate(paths)))
    reg['documents']['metadata']={'path':str(metadata),'sha256':file_hash(metadata)}
    truth=read_json(root/row['truth_path']);truth['goal']=task['goal']
    truth['entity_goal_conflict']['positive_pairs']=[['train/006.png','test/004.png']]
    run_task(task,reg,tmp_path/'entity-run')
    result=score_run(task,reg,truth,tmp_path/'entity-run')
    assert result['entity_goal_conflict']['tp']==1 and result['entity_goal_conflict']['fp']==0
    task['goal']='same_entity_new_view';reg['confirmations']['user.local-task']['goal']=task['goal']
    truth['goal']=task['goal'];truth['entity_goal_conflict']['positive_pairs']=[]
    run_task(task,reg,tmp_path/'view-run')
    result=score_run(task,reg,truth,tmp_path/'view-run')
    assert result['entity_goal_conflict']['predicted_pairs']==0 and result['entity_goal_conflict']['recall'] is None


def test_actual_worker_spawn_failure_retains_full_denominator(tmp_path,monkeypatch):
    # Fault injection changes only the worker executable for C. execute() really
    # attempts it and records FileNotFoundError; no replacement detector exists.
    import visionleak_investigator.evaluation_runner as runner
    root,catalog,protocol,frozen=prepared(tmp_path)
    original=runner.execute
    def missing_worker(argv,*args,**kwargs):
        if 'visionleak_investigator.evaluation_worker' in argv and argv[-1]=='C':
            argv=[str(tmp_path/'missing-python'),*argv[1:]]
        return original(argv,*args,**kwargs)
    monkeypatch.setattr(runner,'execute',missing_worker)
    result=run_catalog(catalog,root,protocol,frozen,tmp_path/'failure-results',partition='development')
    assert result['status']=='completed_with_failures' and result['runs']['C']['FAILED']==1
    assert result['quality']['C']['failed_runs_in_denominator']==1
    assert result['quality']['C']['exact']['truth_denominator']==3
    assert result['quality']['C']['exact']['fn']==3 and result['quality']['C']['exact']['recall']==0
    assert result['resources_by_condition']['C']['cpu_measured_runs']==0
    assert result['resources_by_condition']['C']['cpu_seconds'] is None


def test_rules_one_call_budget_still_runs_base_and_records_omitted_scope(tmp_path):
    from visionleak_investigator.workflow import run_task
    root,catalog,protocol,_=prepared(tmp_path)
    task=read_json(root/catalog['tasks'][0]['task_path']);reg=read_json(root/catalog['tasks'][0]['registry_path'])
    task['limits']['max_core_audit_runs']=1
    report=run_task(task,reg,tmp_path/'one-call')
    assert report['state']=='PARTIAL' and report['budget']['spent']['audit_runs']==1
    assert list(report['coverage']['profiles'])==['base']
    assert report['coverage']['unexecuted_profiles']==[{'profile':'all','reason':'max_core_audit_runs'}]
    assert any(c['claim_type']=='byte_identity' and c['status']=='confirmed' for c in report['claims'])


def test_actual_midrun_input_change_rejects_aggregation_and_keeps_attempt(tmp_path,monkeypatch):
    import visionleak_investigator.evaluation_runner as runner
    root,catalog,protocol,frozen=prepared(tmp_path)
    original=runner.execute
    def mutate_after_worker(argv,*args,**kwargs):
        result=original(argv,*args,**kwargs)
        if 'visionleak_investigator.evaluation_worker' in argv:
            path=root/catalog['tasks'][0]['truth_path']
            path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(runner,'execute',mutate_after_worker)
    result=run_catalog(catalog,root,protocol,frozen,tmp_path/'rejected',partition='development')
    assert result['status']=='rejected' and result['quality'] is None
    rows=[json.loads(s) for s in (tmp_path/'rejected/per_run.jsonl').read_text().splitlines()]
    assert len(rows)==4 and rows[0]['comparison_status']=='rejected'
    assert rows[0]['full_task_resources']['cpu_seconds']>0
    assert result['runs']['B']['not_run']==1 and result['runs']['C']['not_run']==1
