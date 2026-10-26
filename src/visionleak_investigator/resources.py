"""POSIX child accounting and bounded-overhead process-tree RSS sampling."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import psutil


def measured_wait(process: subprocess.Popen, timeout: float, *, interval: float = 0.02) -> tuple[int, str | None, dict]:
    """Own this child's wait4; do not concurrently poll/wait on the same Popen.

    CPU is OS wait4 accounting; RSS is a sampled sum, never a hard memory limit
    or unique physical-memory measurement. Only the created child is observed.
    """
    started = time.monotonic()
    deadline = started + max(0.001, timeout)
    try:
        root = psutil.Process(process.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
        root = None
    samples, peak, root_peak = 0, 0, 0
    seen, peak_members = set(), []
    denied, races = (0 if root else 1), 0
    error = None
    try:
        while True:
            members = []
            try:
                candidates = [root, *root.children(recursive=True)] if root else []
            except psutil.NoSuchProcess:
                candidates = []; races += 1
            except (psutil.AccessDenied, PermissionError):
                candidates = [root]; denied += 1
            for child in candidates:
                try:
                    identity = (child.pid, child.create_time())
                    rss = child.memory_info().rss
                    seen.add(identity)
                    members.append({'pid': child.pid, 'rss_bytes': rss})
                    if child.pid == process.pid:
                        root_peak = max(root_peak, rss)
                except psutil.NoSuchProcess:
                    races += 1
                except (psutil.AccessDenied, PermissionError):
                    denied += 1
            if members:
                samples += 1
                total = sum(row['rss_bytes'] for row in members)
                if total > peak:
                    peak, peak_members = total, members
            pid, status, usage = os.wait4(process.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() >= deadline:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, usage = os.wait4(process.pid, 0)
                error = 'timeout'
                break
            time.sleep(min(interval, max(0, deadline-time.monotonic())))
        process.returncode = os.waitstatus_to_exitcode(status)
    except BaseException:
        # Cancellation must not leave this command or its worker group running.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    measurement = {
        'schema_version': 1, 'cpu_method': 'os.wait4',
        'cpu_user_seconds': usage.ru_utime, 'cpu_system_seconds': usage.ru_stime,
        'cpu_seconds': usage.ru_utime + usage.ru_stime,
        'cpu_scope': 'OS child accounting including reaped descendants; not detached/unreaped descendants',
        'wait4_maxrss_bytes': usage.ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
        'wait4_maxrss_scope': 'OS child maximum RSS; not simultaneous process-tree sum',
        'tree_rss_method': 'psutil recursive children; sampled sum RSS',
        'tree_rss_status': 'not_measured' if not samples else 'partial' if denied else 'sampled',
        'tree_rss_peak_bytes': peak if samples and not denied else None,
        'observed_rss_peak_bytes': peak if samples else None,
        'root_rss_peak_bytes': root_peak if samples else None,
        'sample_interval_seconds': interval, 'samples': samples,
        'observed_process_count': len(seen), 'peak_members': peak_members,
        'access_denied_samples': denied, 'process_exit_races': races,
        'sampler_wall_seconds': time.monotonic()-started,
        'limitations': ['Short-lived processes or peaks between samples may be missed.',
                        'Summed RSS can count shared pages more than once.',
                        'This is measurement, not an OS memory limit.'],
    }
    return process.returncode, error, measurement
