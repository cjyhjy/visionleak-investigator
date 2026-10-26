import copy
import pytest
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_baseline,run_task
from visionleak_investigator.common import read_json
from visionleak_investigator.evaluation import comparable,score_pairs

def test_T27_T35_same_lock_and_limits_required(tmp_path):
    t,r=make_task(tmp_path/'fixture');a=run_baseline(t,r,tmp_path/'A','A');b=run_baseline(t,r,tmp_path/'B','B')
    assert b['budget']['spent']['audit_runs']==1 and list(b['coverage']['profiles'])==['all']
    ma=read_json(tmp_path/'A/manifest.json');mb=read_json(tmp_path/'B/manifest.json');comparable([(ma,t),(mb,t)])
    mb['core_lock_digest']='different'
    with pytest.raises(ValueError):comparable([(ma,t),(mb,t)])
    mb=copy.deepcopy(ma);changed=copy.deepcopy(t);changed['limits']['max_comparisons_total']+=1
    with pytest.raises(ValueError):comparable([(ma,t),(mb,changed)])

def test_T28_full_denominator_and_na():
    s=score_pairs({('a','b')},{('a','b'),('c','d')});assert s['recall']==0.5 and s['precision']==1
    s=score_pairs(set(),{('a','b')});assert s['precision'] is None and s['recall']==0
    s=score_pairs(set(),set());assert s['precision'] is None and s['recall'] is None
