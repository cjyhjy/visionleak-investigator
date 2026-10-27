"""Real Core reports measure their sole full render and staged content writes."""
from contextlib import contextmanager
from pathlib import Path
import time

import pytest

from visionleak_investigator import workflow, interaction, recovery
from visionleak_investigator.budget import BudgetLedger
from visionleak_investigator.common import read_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run


@pytest.mark.parametrize('mode', ['initial','revision','recovery'])
def test_one_render_and_staged_html_write_are_charged(tmp_path, monkeypatch, mode):
    task,registry=make_task(tmp_path/'fixture',seed=83400)
    run=tmp_path/'run'
    if mode!='initial':workflow.run_task(task,registry,run,profiles=['base'])
    if mode=='recovery':(run/'report.json').unlink()
    module={'initial':workflow,'revision':interaction,'recovery':recovery}[mode]
    original=module.render_report;calls=[]
    def render(*args,**kwargs):
        started=time.monotonic();time.sleep(.12)
        value=original(*args,**kwargs)
        calls.append(time.monotonic()-started)
        return value
    original_open=Path.open;writes=[]
    @contextmanager
    def slow_html(path,*args,**kwargs):
        started=time.monotonic()
        with original_open(path,*args,**kwargs) as stream:yield stream
        time.sleep(.12);writes.append(time.monotonic()-started)
    def opening(path,*args,**kwargs):
        if path.name in ('report.html','report.pending.html') and args and args[0] in ('x','w'):
            return slow_html(path,*args,**kwargs)
        return original_open(path,*args,**kwargs)
    monkeypatch.setattr(module,'render_report',render);monkeypatch.setattr(Path,'open',opening)
    if mode=='initial':report=workflow.run_task(task,registry,run,profiles=['base']);target=run
    elif mode=='revision':
        report=interaction.resume_run(run,{'actor':'scripted accounting acceptance','goal':'content_audit'})
        target=Path(report['revision']['path'])
    else:report=recovery.recover_interrupted(run);target=run
    assert len(calls)==len(writes)==1
    final=report['budget']['entries'][-1]
    assert final['kind'] in ('finalize','recovery_finalize') and final['status']=='settled'
    assert final['actual']['wall_seconds']>=sum(calls)+sum(writes)
    assert report['publication']['full_render_calls']==1
    assert report['publication']['html_budget_snapshot']=='before_finalization_settlement'
    assert '最终预算' in (target/'report.html').read_text()
    assert read_json(target/'report.json')==report==verify_run(target)


def test_revision_proposal_assembly_runs_under_finalization_reservation(tmp_path, monkeypatch):
    task,registry=make_task(tmp_path/'fixture');run=tmp_path/'run'
    workflow.run_task(task,registry,run,profiles=['base'])
    original=interaction.proposal;observed=[]
    def assemble(*args,**kwargs):
        target=Path(read_json(run/'pending-revision.json')['path'])
        entry=read_json(target/'ledger.json')['entries'][-1]
        assert entry['kind']=='finalize' and entry['status']=='pending'
        started=time.monotonic();time.sleep(.12)
        value=original(*args,**kwargs);observed.append(time.monotonic()-started)
        return value
    monkeypatch.setattr(interaction,'proposal',assemble)
    report=interaction.resume_run(run,{'actor':'scripted accounting acceptance','goal':'content_audit'})
    assert len(observed)==1 and report['budget']['entries'][-1]['actual']['wall_seconds']>=observed[0]


def test_render_overrun_is_partial_without_a_second_full_render(tmp_path, monkeypatch):
    task,registry=make_task(tmp_path/'fixture');run=tmp_path/'run'
    reserve=BudgetLedger.reserve;original=workflow.render_report;calls=[]
    def bounded(self,kind,allocation=None,**kwargs):
        if kind=='finalize':allocation={**(allocation or {}),'wall_seconds':.05}
        return reserve(self,kind,allocation,**kwargs)
    def delayed(*args,**kwargs):
        time.sleep(.12);calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(BudgetLedger,'reserve',bounded);monkeypatch.setattr(workflow,'render_report',delayed)
    report=workflow.run_task(task,registry,run,profiles=['base'])
    assert len(calls)==1 and report['state']=='PARTIAL'
    assert report['budget']['entries'][-1]['overrun']['wall_seconds']>0
    assert 'PARTIAL' in (run/'report.html').read_text() and 'COMPLETED' not in (run/'report.html').read_text()
    assert verify_run(run)==report


def test_interrupted_publication_is_not_accepted_and_recovery_keeps_cost(tmp_path, monkeypatch):
    from visionleak_investigator import publication
    task,registry=make_task(tmp_path/'fixture');run=tmp_path/'run'
    original=publication._publish_file
    def fail_after_json(staged,destination):
        original(staged,destination)
        if destination.name=='report.json':raise OSError('controlled publication interruption')
    monkeypatch.setattr(publication,'_publish_file',fail_after_json)
    with pytest.raises(ValueError,match='publication failed'):
        workflow.run_task(task,registry,run,profiles=['base'])
    before=read_json(run/'ledger.json')
    assert before['entries'][-1]['status']=='settled'
    assert read_json(run/'publication-failure.json')['state']=='FAILED'
    with pytest.raises(ValueError,match='Report changed'):verify_run(run)
    monkeypatch.setattr(publication,'_publish_file',original)
    report=recovery.recover_interrupted(run)
    assert report['state']=='PARTIAL' and not report['claims']
    assert report['budget']['spent']['audit_runs']==before['spent']['audit_runs']==1
    assert report['budget']['spent']['wall_seconds']>=before['spent']['wall_seconds']
    assert any(p['path'].endswith('/report.json') for p in report['recovery']['preserved_files'])
    assert verify_run(run)==report==recovery.recover_interrupted(run)


def test_render_failure_preserves_real_outputs_and_unknown_cost(tmp_path, monkeypatch):
    task,registry=make_task(tmp_path/'fixture');run=tmp_path/'run';original=workflow.render_report
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise OSError('controlled renderer failure')
    monkeypatch.setattr(workflow,'render_report',fail)
    with pytest.raises(ValueError,match='publication failed'):
        workflow.run_task(task,registry,run,profiles=['base'])
    ledger=read_json(run/'ledger.json');entry=ledger['entries'][-1]
    assert entry['kind']=='finalize' and entry['status']=='unknown' and entry['actual']==entry['reservation']
    assert list((run/'tools').glob('*/output/report.json')) and not (run/'report.json').exists()
    assert read_json(run/'publication-failure.json')['state']=='FAILED'


def test_published_html_is_bound_to_the_final_report(tmp_path):
    task,registry=make_task(tmp_path/'fixture');run=tmp_path/'run'
    workflow.run_task(task,registry,run,profiles=['base'])
    with (run/'report.html').open('a') as stream:stream.write('tampered display')
    with pytest.raises(ValueError,match='publication accounting or HTML changed'):verify_run(run)
