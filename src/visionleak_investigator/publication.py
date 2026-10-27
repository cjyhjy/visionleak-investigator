"""Single-pass report preparation followed by a small accounting commit.

The measured phase includes report assembly by the caller, rendering, JSON body
serialization, staged content writes/fsync and HTML hashing. Recording the
measurement itself (ledger, JSON accounting tail, names and checkpoint) is the
commit boundary; whole-worker resource receipts additionally include that I/O.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
import time
from typing import Callable

from .common import file_hash, no_symlink, now, write_json


def _publish_file(staged: Path, destination: Path) -> None:
    """Exclusive publication on the same filesystem; never replace an old report."""
    no_symlink(destination)
    os.link(staged, destination)
    staged.unlink()


def publish_report(out: Path, report: dict, evidence: list[dict], ledger, entry: dict,
                   started: float, renderer: Callable) -> dict:
    if entry['status'] != 'pending':
        raise ValueError('Report publication requires a pending finalization reservation')
    pending_html=no_symlink(out/'report.pending.html')
    pending_json=no_symlink(out/'report.pending.json')
    info={'schema_version':1,'finalization_call_id':entry['call_id'],'full_render_calls':1,
          'html_budget_snapshot':'before_finalization_settlement',
          'measured_scope':'Caller assembly, one full HTML render, JSON body serialization, staged content writes/fsync and HTML hashing.',
          'accounting_commit_scope':'Recording this measurement in the ledger/JSON tail, exclusive file publication and checkpoint. Included in whole-worker resources; excluded from its self-recorded tool interval.'}
    original_issue_count=len(report['issues'])
    try:
        rendered=renderer({**report,'_publication_snapshot':True},evidence)
        with pending_html.open('x',encoding='utf-8') as stream:
            stream.write(rendered);stream.flush();os.fsync(stream.fileno())
        # Write the full non-accounting body now. The final measured values are
        # appended once; the large report and HTML are never rendered/written twice.
        static={k:v for k,v in report.items() if k not in ('budget','state','issues','publication')}
        body=json.dumps(static,ensure_ascii=False,indent=2,allow_nan=False)[1:-1].strip()
        issues=json.dumps(report['issues'],ensure_ascii=False,allow_nan=False)
        with pending_json.open('x',encoding='utf-8') as stream:
            stream.write('{\n'+body+(',\n' if body else '')+'"issues": '+issues[:-1])
            stream.flush();os.fsync(stream.fileno())
        staged_sha=file_hash(pending_html)
        elapsed=time.monotonic()-started
        info.update(measured_wall_seconds=elapsed,measurement_ended_at=now(),staged_html_sha256=staged_sha)
        ledger.settle(entry,{'wall_seconds':elapsed})
        if elapsed>entry['reservation']['wall_seconds']:
            report['state']='PARTIAL';report['issues'].append('Finalization time exceeded reservation')
            # Preserve the pre-settlement view, but never serve its earlier state
            # as the accepted page after an overrun. This is a small status receipt,
            # not a second full evidence render.
            _publish_file(pending_html,out/'report.before-overrun.html')
            status='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'"><title>PARTIAL</title><h1>PARTIAL · 结案超过预留时间</h1><p>'+html.escape(report['issues'][-1])+'</p><p>证据仍保留。最终预算与结论以 <a href="report.json">报告 JSON</a> 和 <a href="ledger.json">预算账本</a> 为准。</p></html>'
            with pending_html.open('x',encoding='utf-8') as stream:stream.write(status)
            info['html_kind']='overrun_status_receipt'
        else:info['html_kind']='audit_snapshot'
        info['html_sha256']=file_hash(pending_html)
        report['publication']=info
        with pending_json.open('a',encoding='utf-8') as stream:
            extra=report['issues'][original_issue_count:]
            for index,issue in enumerate(extra):
                stream.write((',' if original_issue_count or index else '')+json.dumps(issue,ensure_ascii=False))
            stream.write('],\n"state": '+json.dumps(report['state'])+',\n"budget": '+json.dumps(ledger.data,ensure_ascii=False,indent=2,allow_nan=False)+',\n"publication": '+json.dumps(info,ensure_ascii=False,indent=2,allow_nan=False)+'\n}\n')
            stream.flush();os.fsync(stream.fileno())
        _publish_file(pending_html,out/'report.html')
        _publish_file(pending_json,out/'report.json')
        return report
    except Exception as exc:
        if entry['status']=='pending':ledger.settle(entry,None,error='Report publication failed; conservative charge')
        write_json(out/'publication-failure.json',{'state':'FAILED','error_type':type(exc).__name__,'reason':str(exc),'raw_outputs_preserved':True})
        raise ValueError('Report publication failed; output and cost preserved') from exc
