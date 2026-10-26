import copy
import sys
from pathlib import Path

import pytest

from visionleak_investigator.common import PROJECT, digest, read_json, write_json
from visionleak_investigator.core import execute
from visionleak_investigator.domain import Registry, input_manifest
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.interaction_fixture import make_interaction_suite
from visionleak_investigator.interaction_scoring import score_interaction
from visionleak_investigator.workflow import run_task


@pytest.fixture
def case(tmp_path):
    root=tmp_path/'suite';make_interaction_suite(root)
    task=read_json(root/'tasks/t000/task.json');registry=read_json(root/'tasks/t000/registry.json')
    truth=read_json(root/'evaluator-truth/t000.json');run=tmp_path/'run'
    run_task(task,registry,run)
    return root,task,registry,truth,run


@pytest.mark.parametrize('change',['task_id','request','limits','registry','input','initial_goal'])
def test_foreign_or_changed_expected_contract_is_unusable(case,change):
    root,task,registry,truth,run=case
    task=copy.deepcopy(task);registry=copy.deepcopy(registry);truth=copy.deepcopy(truth)
    if change=='task_id':task['task_id']=truth['task_id']='other-task'
    if change=='request':task['request_text']+=' different initial request'
    if change=='limits':task['limits']['max_questions']-=1
    if change=='registry':registry['documents']['other']=copy.deepcopy(registry['documents']['metadata'])
    if change=='input':
        registry['datasets']=read_json(root/'tasks/t001/registry.json')['datasets']
        truth['dataset_manifest_digest']=input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])['digest']
    if change=='initial_goal':
        task.update(goal='unspecified',goal_confirmed=False,goal_evidence_refs=[])
        registry['confirmations'].pop('user.local-task');truth['necessary_questions']=['clarify_goal']
    saved=read_json(run/'report.json')
    transcript=[{'run':'run','report_digest':digest(saved),'questions':saved['questions'],
                 'answered_questions':[],'answer_path':None,'answer_result':None}]
    score=score_interaction(task,registry,truth,run,transcript)
    assert not score['usable_output'] and score['state']=='FAILED' and score['failure']
    assert not score['goal_correct'] and not score['field_correct']
    assert score['risk']['fn']==score['risk']['truth_denominator']==8
    assert score['risk']['tp']==score['risk']['fp']==0
    assert score['accepted_output'] is None and score['unsupported_confirmed_claims'] is None
    assert score['question_budget_spent'] is None


def test_initial_run_and_legitimate_revision_bind_to_expected_contract(tmp_path):
    root=tmp_path/'suite';make_interaction_suite(root)
    task=read_json(root/'tasks/t003/task.json');registry=read_json(root/'tasks/t003/registry.json')
    truth=read_json(root/'evaluator-truth/t003.json');run=tmp_path/'run'
    initial=run_task(task,registry,run)
    observation={'run':'run','report_digest':digest(initial),'questions':initial['questions'],
                 'answered_questions':[],'answer_path':None,'answer_result':None}
    first=score_interaction(task,registry,truth,run,[observation])
    assert first['usable_output'] and not first['goal_correct']
    assert first['accepted_output']['verified_revision_count']==0
    payload={'actor':'fixed scripted answer broker; no human participant','goal':truth['goal'],'entity_key':truth['entity_key']}
    write_json(tmp_path/'answer.json',payload)
    process=execute([sys.executable,'-m','visionleak_investigator.cli','resume','--run',str(run),'--answers',str(tmp_path/'answer.json')],PROJECT,tmp_path/'answer-process',30)
    assert process['error'] is None and process['exit_code'] in (0,2,3)
    revision=Path(read_json(tmp_path/'answer-process/stdout.log')['report']).parent
    final=verify_run(revision)
    observation.update(answered_questions=['clarify_goal','clarify_entity_key'],answer_path='answer.json',answer_result='answer-process/result.json')
    transcript=[observation,{'run':str(revision.relative_to(tmp_path)),'report_digest':digest(final),'questions':final['questions'],
                            'answered_questions':[],'answer_path':None,'answer_result':None}]
    score=score_interaction(task,registry,truth,revision,transcript)
    assert score['usable_output'] and score['goal_correct'] and score['field_correct']
    assert score['accepted_output']['verified_revision_count']==1
    assert score['accepted_output']['initial_report_digest']==digest(initial)
    assert score['accepted_output']['report_digest']==digest(final)
    assert score['initial_task_digest']==digest(task) and score['initial_registry_digest']==digest(registry)
    assert score['risk']['fn']==0 and score['risk']['tp']==8
    # A locally consistent child checkpoint alone cannot attest to its parent.
    record=read_json(revision/'manifest.json');record['parent_report_digest']='0'*64
    write_json(revision/'manifest.json',record)
    checkpoint=read_json(revision/'checkpoint.json');checkpoint['manifest_digest']=digest(record)
    write_json(revision/'checkpoint.json',checkpoint)
    verify_run(revision)
    rejected=score_interaction(task,registry,truth,revision,transcript)
    assert not rejected['usable_output'] and 'parent binding' in rejected['failure']
    assert rejected['risk']['fn']==8


def test_foreign_question_transcript_cannot_be_scored_with_another_valid_run(case):
    root,task,registry,truth,run=case
    other_task=read_json(root/'tasks/t003/task.json');other_reg=read_json(root/'tasks/t003/registry.json')
    other=run_task(other_task,other_reg,run.parent/'other-run')
    transcript=[{'run':'other-run','report_digest':digest(other),'questions':other['questions'],
                 'answered_questions':[],'answer_path':None,'answer_result':None}]
    score=score_interaction(task,registry,truth,run,transcript)
    assert not score['usable_output']
    assert score['risk']['fn']==8 and score['unsupported_confirmed_claims'] is None
    assert score['questions_asked']==0 and score['answers_delivered']==0
