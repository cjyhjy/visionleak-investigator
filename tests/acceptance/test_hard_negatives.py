"""T04: real Core false candidates are retained as measured controlled negatives."""
from visionleak_investigator.common import file_hash
from visionleak_investigator.demo import make_hard_negative_task
from visionleak_investigator.domain import Registry,input_manifest
from visionleak_investigator.evaluation_scoring import score_run
from visionleak_investigator.workflow import run_task


def test_T04_flat_and_gradient_candidates_stay_unconfirmed_and_count_as_false_positives(tmp_path):
    task,registry=make_hard_negative_task(tmp_path/'fixture')
    root=Registry(registry).dataset(task['dataset_ref'])
    before=input_manifest(root,task['limits'])
    result=run_task(task,registry,tmp_path/'run')
    assert result['state']=='COMPLETED' and result['reviews']
    assert all(c['status']=='candidate' and c['claim_type']=='perceptual_relation' for c in result['claims'])
    empty={'coverage':'exhaustive','positive_pairs':[],'negative_pairs':[]}
    truth={'schema_version':1,'task_id':task['task_id'],'dataset_manifest_digest':before['digest'],'goal':task['goal'],
           'basis':{'kind':'synthetic_generation','description':'Four independently constructed controlled negative source records; flat/gradient ambiguity.'},
           'exact':empty,'related_excluding_exact':empty,'entity_goal_conflict':empty}
    scored=score_run(task,registry,truth,tmp_path/'run')
    assert scored['exact']['predicted_pairs']==0
    assert scored['related_excluding_exact']['fp']>0
    assert scored['related_excluding_exact']['precision']==0 and scored['related_excluding_exact']['recall'] is None
    assert scored['candidate_burden']==scored['pending_review_pairs']>0
    assert scored['related_excluding_exact']['eligible_pairs']==4
    assert input_manifest(root,task['limits'])==before
