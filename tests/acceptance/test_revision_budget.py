"""Real Core checks for reservation order and interrupted revision accounting."""
from pathlib import Path

import pytest

from visionleak_investigator.budget import BudgetExceeded
from visionleak_investigator.common import digest, file_hash, read_json
from visionleak_investigator.core import CoreAdapter
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.interaction import resume_run
from visionleak_investigator.workflow import run_task


ANSWER = {'actor': 'scripted budget acceptance; no human participant', 'goal': 'same_entity_new_view'}


def setup_run(tmp_path, calls=16):
    task, registry = make_task(tmp_path/'fixture', seed=83301)
    task['limits']['max_tool_calls'] = calls
    run = tmp_path/'run'
    run_task(task, registry, run, profiles=['base'])
    return run, run/'revisions'/digest(['answers', ANSWER])


def test_denied_revision_does_not_launch_core_or_leave_partial_target(tmp_path, monkeypatch):
    run, target = setup_run(tmp_path, calls=6)
    before = file_hash(run/'ledger.json')
    original = CoreAdapter.inspect_report
    calls = []
    def observe(self, *args, **kwargs):
        calls.append(str(args[0]))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(CoreAdapter, 'inspect_report', observe)
    with pytest.raises(BudgetExceeded):
        resume_run(run, ANSWER)
    assert calls == []
    assert not target.exists()
    assert not (run/'pending-revision.json').exists()
    assert file_hash(run/'ledger.json') == before


def test_real_identity_check_starts_with_persisted_pending_reservation(tmp_path, monkeypatch):
    run, target = setup_run(tmp_path)
    original = CoreAdapter.inspect_report
    seen = []
    def observe(self, *args, **kwargs):
        ledger = read_json(target/'ledger.json')
        entry = ledger['entries'][-1]
        assert entry['kind'] == 'resume_identity_check' and entry['status'] == 'pending'
        assert read_json(run/'pending-revision.json')['path'] == str(target)
        assert kwargs['timeout'] <= entry['reservation']['wall_seconds']
        seen.append(entry['call_id'])
        return original(self, *args, **kwargs)
    monkeypatch.setattr(CoreAdapter, 'inspect_report', observe)
    result = resume_run(run, ANSWER)
    assert len(seen) == 1
    assert not (run/'pending-revision.json').exists()
    assert result['budget']['spent']['audit_runs'] == 1
    assert verify_run(target) == result


def test_failed_revision_is_charged_and_recovered_before_another_attempt(tmp_path, monkeypatch):
    run, target = setup_run(tmp_path)
    original = CoreAdapter.inspect_report
    calls = []
    def fail_after_real_inspection(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        calls.append(result)
        raise ValueError('controlled failure after real Core identity check')
    monkeypatch.setattr(CoreAdapter, 'inspect_report', fail_after_real_inspection)
    with pytest.raises(ValueError, match='controlled failure'):
        resume_run(run, ANSWER)
    ledger = read_json(target/'ledger.json')
    failed = ledger['entries'][-1]
    assert failed['kind'] == 'resume_identity_check' and failed['status'] == 'unknown'
    assert failed['actual'] == failed['reservation']
    assert read_json(target/'revision-failure.json')['state'] == 'FAILED'
    assert (run/'pending-revision.json').exists()
    monkeypatch.setattr(CoreAdapter, 'inspect_report', original)
    recovered = resume_run(run, ANSWER)
    assert recovered['state'] == 'PARTIAL' and recovered['claims'] == []
    assert recovered['budget']['spent']['audit_runs'] == 1
    assert recovered['budget']['spent']['tool_calls'] == ledger['spent']['tool_calls'] + 1
    assert not (run/'pending-revision.json').exists()
    assert verify_run(target) == recovered
    assert resume_run(run, ANSWER) == recovered
    with pytest.raises(BudgetExceeded):
        resume_run(run, {**ANSWER, 'goal': 'content_audit'})
    assert len(calls) == 1


def test_zero_identity_allowance_rejects_before_a_core_process(tmp_path, monkeypatch):
    run, _ = setup_run(tmp_path)
    original = CoreAdapter.verify_artifacts
    called = []
    def observe(self, **kwargs):
        called.append(kwargs)
        return original(self, **kwargs)
    monkeypatch.setattr(CoreAdapter, 'verify_artifacts', observe)
    with pytest.raises(TimeoutError, match='time allowance'):
        verify_run(run, recompute_identity=True, identity_timeout=0)
    assert called == []


def test_interrupted_revision_reservation_is_not_replayed(tmp_path, monkeypatch):
    run, target = setup_run(tmp_path)
    original = CoreAdapter.inspect_report
    def interrupt_after_real_inspection(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise KeyboardInterrupt('controlled interruption')
    monkeypatch.setattr(CoreAdapter, 'inspect_report', interrupt_after_real_inspection)
    with pytest.raises(KeyboardInterrupt):
        resume_run(run, ANSWER)
    assert read_json(target/'ledger.json')['entries'][-1]['status'] == 'pending'
    monkeypatch.setattr(CoreAdapter, 'inspect_report', original)
    recovered = resume_run(run, ANSWER)
    assert recovered['state'] == 'PARTIAL' and not recovered['coverage']['profiles']
    entry = next(e for e in recovered['budget']['entries'] if e['kind'] == 'resume_identity_check')
    assert entry['status'] == 'unknown' and entry['actual'] == entry['reservation']
    assert recovered['budget']['spent']['audit_runs'] == 1
    assert verify_run(target) == recovered
