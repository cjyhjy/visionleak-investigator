"""Measure real processes, including a memory-heavy child and timeout path."""
import json
import sys
import pytest

from visionleak_investigator.core import execute
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task
from visionleak_investigator.common import read_json


def test_cpu_and_child_tree_rss_are_measured(tmp_path):
    child = "import time; b=bytearray(32*1024*1024); end=time.monotonic()+0.4\nwhile time.monotonic()<end: sum(range(10000))\ntime.sleep(0.1)"
    parent = "import subprocess,sys; subprocess.run([sys.executable,'-c',sys.argv[1]],check=True)"
    result = execute([sys.executable,'-c',parent,child],tmp_path,tmp_path/'call',3)
    assert result['exit_code']==0
    m=result['resources']
    assert m['cpu_seconds']>0.1
    if m['access_denied_samples']:
        assert m['tree_rss_status'] in ('partial','not_measured')
        pytest.skip('OS denied process enumeration; run unsandboxed or CI to verify full tree RSS')
    assert m['observed_process_count']>=2
    assert m['tree_rss_peak_bytes']>m['root_rss_peak_bytes']+16*1024*1024
    assert sum(p['rss_bytes'] for p in m['peak_members'])==m['tree_rss_peak_bytes']
    assert m['samples']>1


def test_timeout_is_reaped_and_keeps_measurements(tmp_path):
    result=execute([sys.executable,'-c','import time; b=bytearray(16*1024*1024); time.sleep(20)'],tmp_path,tmp_path/'call',0.2)
    assert result['error']=='timeout' and result['exit_code']<0
    assert result['wall_seconds']<3
    assert result['resources']['cpu_seconds']>=0
    assert read_json(tmp_path/'call/result.json')==result


def test_spawn_failure_is_unknown_not_zero_resources(tmp_path):
    result=execute([str(tmp_path/'missing-executable')],tmp_path,tmp_path/'call',1)
    assert result['status']=='failed' and result['resources'] is None


def test_real_core_calls_include_node_resources(tmp_path):
    task,registry=make_task(tmp_path/'fixture')
    run_task(task,registry,tmp_path/'audit')
    calls=[read_json(p) for p in (tmp_path/'audit/tools').glob('*/result.json')]
    assert calls and all(c['resources']['cpu_seconds']>0 for c in calls)
    for call in calls:
        m=call['resources']
        if m['tree_rss_status']=='sampled':assert m['tree_rss_peak_bytes']>0
        else:assert m['tree_rss_peak_bytes'] is None and m['access_denied_samples']>0


def test_timeout_terminates_spawned_descendant_not_only_worker(tmp_path):
    import os
    import signal
    import psutil
    pidfile=tmp_path/'owned-child.json'
    child="import time; time.sleep(20)"
    parent="import subprocess,sys,json,os,time; p=subprocess.Popen([sys.executable,'-c',sys.argv[1]]); open(sys.argv[2],'w').write(json.dumps({'child':p.pid,'parent':os.getpid()})); time.sleep(20)"
    result=execute([sys.executable,'-c',parent,child,str(pidfile)],tmp_path,tmp_path/'call',0.5)
    ids=json.loads(pidfile.read_text())
    assert result['error']=='timeout'
    try:
        process=psutil.Process(ids['child'])
        assert process.status()==psutil.STATUS_ZOMBIE, 'Timed-out process group left a live descendant'
    except psutil.NoSuchProcess:
        pass
    except psutil.AccessDenied:
        pytest.skip('OS denied child status; verify process-group cleanup with process access or CI')
    finally:
        # Clean only this exact fixture child if a regression leaves it alive.
        try:
            p=psutil.Process(ids['child'])
            if p.status()!=psutil.STATUS_ZOMBIE and p.cmdline()==[sys.executable,'-c',child]:
                os.kill(ids['child'],signal.SIGKILL)
        except (psutil.NoSuchProcess,psutil.AccessDenied,ProcessLookupError):
            pass
