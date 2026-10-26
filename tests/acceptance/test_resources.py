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
