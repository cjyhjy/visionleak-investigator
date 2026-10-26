import pytest
from visionleak_investigator.common import write_json
from visionleak_investigator.rules import load_policy


@pytest.mark.parametrize(('key','value'),[
    ('threshold',1),('mandatory_profile','all'),('max_audits',8),('learning',True),
    ('shell','cat secrets'),('hint_terms',{'transform':['.*'],'local':['crop']}),
])
def test_frozen_policy_rejects_changes_to_guarded_semantics(tmp_path,monkeypatch,key,value):
    from visionleak_investigator import rules
    policy=load_policy();policy[key]=value
    write_json(tmp_path/'configs/policy.json',policy);monkeypatch.setattr(rules,'PROJECT',tmp_path)
    with pytest.raises(ValueError,match='rules-policy'):rules.load_policy()
