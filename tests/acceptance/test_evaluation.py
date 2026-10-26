import copy
import pytest
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_baseline,run_task
from visionleak_investigator.common import read_json
from visionleak_investigator.evaluation import comparable,score_pairs,check_execution,resource_totals
from visionleak_investigator.evaluation_data import execution_identity

def test_T27_T35_same_lock_and_limits_required(tmp_path):
    t,r=make_task(tmp_path/'fixture');a=run_baseline(t,r,tmp_path/'A','A');b=run_baseline(t,r,tmp_path/'B','B')
    assert b['budget']['spent']['audit_runs']==1 and list(b['coverage']['profiles'])==['all']
    ma=read_json(tmp_path/'A/manifest.json');mb=read_json(tmp_path/'B/manifest.json');comparable([(ma,t),(mb,t)])
    mb['core_lock_digest']='different'
    with pytest.raises(ValueError):comparable([(ma,t),(mb,t)])
    mb=copy.deepcopy(ma);changed=copy.deepcopy(t);changed['limits']['max_comparisons_total']+=1
    with pytest.raises(ValueError):comparable([(ma,t),(mb,changed)])
    mb=copy.deepcopy(ma);mb['code_digest']='different'
    with pytest.raises(ValueError):comparable([(ma,t),(mb,t)])

@pytest.mark.parametrize('field',['code_digest','python_lock_digest','policy_digest','environment'])
def test_execution_drift_rejects_aggregate_with_record(tmp_path,field):
    frozen=execution_identity();frozen[field]='changed'
    with pytest.raises(ValueError,match='must not be aggregated'):check_execution(frozen,tmp_path)
    assert field in (tmp_path/'rejected-comparisons.jsonl').read_text()

def test_failed_and_partial_resource_measurements_are_not_zero_cost():
    rows=[{'condition':'A','state':'FAILED','full_task_resources':None},
          {'condition':'A','state':'PARTIAL','full_task_resources':{'cpu_seconds':2,'tree_rss_peak_bytes':None}},
          {'condition':'D','state':'blocked'}]
    values=resource_totals(rows)
    assert values['A']['cpu_seconds']==2 and values['A']['attempted_runs']==2
    assert not values['A']['cpu_total_complete'] and values['A']['max_sampled_tree_rss_bytes'] is None
    assert values['D']['cpu_seconds'] is None and values['D']['attempted_runs']==0

def test_T28_full_denominator_and_na():
    s=score_pairs({('a','b')},{('a','b'),('c','d')});assert s['recall']==0.5 and s['precision']==1
    s=score_pairs(set(),{('a','b')});assert s['precision'] is None and s['recall']==0
    s=score_pairs(set(),set());assert s['precision'] is None and s['recall'] is None
