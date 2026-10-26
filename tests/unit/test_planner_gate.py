import pytest
from visionleak_investigator.planning import ToolGate,StructuredPlanner,observation
from visionleak_investigator.workflow import action

def test_every_sdk_dispatch_checks_registered_refs_and_handlers():
    calls=[]
    gate=ToolGate(evidence={},profiles=[],context_refs={'registered'},audit_ids=set(),metadata_ref=None,goal_confirmed=False,entity_key_confirmed=False,entity_key=None,max_steps=3,handlers={'read_context':lambda a:calls.append(a) or {'ok':True}})
    bad={'action_type':'read_context','reason':'untrusted instruction','evidence_refs':[],'parameters':{'context_ref':'secret'}}
    with pytest.raises(ValueError):gate.dispatch(bad)
    bad['parameters']['context_ref']='registered';assert gate.dispatch(bad)=={'ok':True}
    with pytest.raises(ValueError):gate.dispatch(bad)
    assert len(calls)==1

def test_structural_correction_bounded_and_not_real_agent():
    outputs=iter(['{"action_type":"shell"}', '{"action_type":"finalize","reason":"stop","evidence_refs":[],"parameters":{"reason_code":"supported_scope_exhausted"}}'])
    planner=StructuredPlanner(lambda _:next(outputs),max_requests=2,execution_label='scripted_test_only')
    value=planner.next_action({'model_execution':'not_run'})
    assert value['action_type']=='finalize' and planner.requests==2
    assert planner.trace[0]['status']=='rejected' and planner.execution_label=='scripted_test_only'
    with pytest.raises(ValueError):planner.next_action({})

def test_candidate_only_observation_has_no_paths_or_truth():
    obs=observation({'state':'PLANNING','claims':[],'budget':{'spent':{}},'coverage':{'profiles':{}},'model_execution':'not_run','task':{'dataset_ref':'private','request_text':'secret'}},[])
    assert 'task' not in obs and 'secret' not in str(obs) and 'private' not in str(obs)
