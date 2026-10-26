"""Actual Core reports retain evidence and scope while gaining safe local navigation."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path

from visionleak_investigator.common import read_json,file_hash
from visionleak_investigator.demo import make_task
from visionleak_investigator.workflow import run_task
from visionleak_investigator.interaction import resume_run
from visionleak_investigator.presentation import anchor
from visionleak_investigator.reporting import render_report


class Page(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=[];self.links=[];self.images=[];self.tags=[];self.attributes=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        self.tags.append(tag);self.attributes+=attrs;attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='a':self.links.append(attrs['href'])
        if tag=='img':self.images.append(attrs['src'])


def test_actual_report_links_resolve_to_evidence_and_existing_local_files(tmp_path):
    task,registry=make_task(tmp_path/'fixture');out=tmp_path/'audit'
    report=run_task(task,registry,out,profiles=['base','all'])
    text=(out/'report.html').read_text();page=Page(text)
    assert len(page.ids)==len(set(page.ids))
    for href in page.links:
        if href.startswith('#'):assert href[1:] in page.ids
        else:assert (out/href).is_file() and not Path(href).is_absolute()
    assert page.images and all((out/path).is_file() for path in page.images)
    rows=list(map(json.loads,(out/'evidence.jsonl').read_text().splitlines()))
    assert all(anchor(e['evidence_id']) in page.ids for e in rows)
    assert all('#'+anchor(ref) in page.links for c in report['claims'] for ref in c['evidence_refs'])
    for e in rows:
        if e.get('images'):
            prefix=e['source_positions'][0].split('#')[0].rsplit('/',1)[0]
            for image in e['images']:assert file_hash(out/prefix/image['thumbnail'])==image['thumbnailDigest']
    assert '模型调用：未运行' in text and '这不代表数据没有风险' in text
    assert '索引操作' in text and '精确关系复验' in text and '待复核记录' in text


def test_partial_scope_and_revision_do_not_imply_complete_or_rescan(tmp_path):
    task,registry=make_task(tmp_path/'fixture');task['limits']['max_comparisons_total']=1
    run=tmp_path/'partial';report=run_task(task,registry,run)
    text=(run/'report.html').read_text()
    assert report['state']=='PARTIAL' and 'PARTIAL · 部分完成' in text
    assert '已生成指纹 6 张；已处理 1 张' in text and 'ComparisonBudget' in text
    assert '不是“未发现风险”的证明' in text
    task,registry=make_task(tmp_path/'question-fixture')
    task.update(goal='unspecified',goal_confirmed=False,goal_evidence_refs=[])
    first=run_task(task,registry,tmp_path/'question')
    assert first['state']=='WAITING_USER'
    revised=resume_run(tmp_path/'question',{'actor':'scripted user fixture','goal':'content_audit'})
    page=(Path(revised['revision']['path'])/'report.html').read_text()
    assert '本次未重跑 Core' in page and '核对恢复输入' in page
    assert revised['budget']['spent']['audit_runs']==first['budget']['spent']['audit_runs']


def test_untrusted_fields_cannot_create_remote_paths_scripts_or_images(tmp_path):
    task,registry=make_task(tmp_path/'fixture');out=tmp_path/'audit'
    report=run_task(task,registry,out);evidence=list(map(json.loads,(out/'evidence.jsonl').read_text().splitlines()))
    report=copy.deepcopy(report);report['task']['request_text']='<script>bad()</script><img src="https://external.invalid/track">'
    report['issues']=['<a href="javascript:bad()">click</a>']
    report['coverage']['profiles']['base']['report_ref']='../../secret.json'
    ev=copy.deepcopy(evidence[0]);ev['source_positions']=['javascript:bad()','https://external.invalid/track','../../secret.json']
    ev['images'][0]['thumbnail']='../../secret.jpg';ev['images'][1]['thumbnail']='https://external.invalid/track'
    text=render_report(report,[ev]);page=Page(text)
    assert 'script' not in page.tags and not page.images
    assert '&lt;script&gt;' in text
    assert all(not href.startswith(('http:','https:','javascript:','file:','/','..')) for href in page.links)
    assert all(not key.startswith('on') for key,_ in page.attributes)


def test_input_drift_withholds_evidence_cards_even_if_raw_records_are_retained(tmp_path):
    task,registry=make_task(tmp_path/'fixture');out=tmp_path/'audit';report=run_task(task,registry,out)
    evidence=list(map(json.loads,(out/'evidence.jsonl').read_text().splitlines()))
    report['claims']=[];report['coverage']['source_unchanged']=False;report['state']='PARTIAL'
    text=render_report(report,evidence);page=Page(text)
    assert all(anchor(e['evidence_id']) not in page.ids for e in evidence) and not page.images
    assert '结论已撤回' in text
