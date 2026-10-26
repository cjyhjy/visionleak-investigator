"""Static, escaped presentation of existing audit facts. No new claims or file reads."""
from __future__ import annotations

from collections import Counter
import html
import json
import re

from .common import digest


CSS = """
:root{color-scheme:light;--ink:#16313c;--muted:#52666f;--line:#d5e1e5;--accent:#126478}
*{box-sizing:border-box}html{scroll-padding-top:20px}body{margin:0;background:#f2f6f7;color:var(--ink);font:16px/1.6 system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:36px 24px 64px}h1{font-size:clamp(28px,5vw,40px);line-height:1.2;margin:8px 0 16px;letter-spacing:-.7px}
h2{font-size:22px;margin:0 0 16px}h3{font-size:18px;margin:0 0 10px}p{margin:8px 0 14px}a{color:#075e75;text-underline-offset:3px}
a:focus-visible,summary:focus-visible{outline:3px solid #d47709;outline-offset:4px}small,.muted{color:var(--muted);font-size:14px}
code,pre,small,dd,td,figcaption,.wrap{overflow-wrap:anywhere}code{font-size:.9em}pre{white-space:pre-wrap;font-size:13px;margin:12px 0}
.eyebrow{font-weight:700;color:var(--accent);letter-spacing:1.5px;font-size:12px}.mode{border-left:4px solid var(--accent);padding:10px 14px;background:#e4f0f3}
.status{border:1px solid var(--line);border-left:5px solid #28745e;background:#fff;padding:20px 24px;border-radius:8px;margin:24px 0}
.status.partial,.status.waiting{border-left-color:#b76a05;background:#fffaf0}.status.failed{border-left-color:#b03035;background:#fff4f4}
.status h2{margin-bottom:4px}.metrics,.budget-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}
.metric{background:#fff;border:1px solid var(--line);padding:16px;border-radius:8px;min-width:0}.metric strong{display:block;font-size:25px;line-height:1.3;margin-top:6px}
nav{display:flex;flex-wrap:wrap;gap:8px 20px;padding:4px 0 20px}section{margin:20px 0;background:#fff;border:1px solid var(--line);border-radius:10px;padding:24px}
article{padding:18px 0;border-top:1px solid var(--line)}article:first-of-type{border-top:0}.badge{display:inline-block;font-size:12px;font-weight:650;padding:3px 9px;border-radius:4px;background:#e8f0f2;color:#365461}
.badge.confirmed{background:#e4f2eb;color:#245b43}.badge.candidate,.badge.inconclusive{background:#fff0d7;color:#855007}
.notice{padding:12px 16px;background:#fff3df;border-left:3px solid #b76a05;border-radius:4px}.notice.danger{background:#ffeded;border-color:#b03035}
ul,ol{padding-left:24px}li{margin:8px 0}dl{display:grid;grid-template-columns:minmax(100px,150px) minmax(0,1fr);gap:8px 18px;margin:12px 0}dt{color:var(--muted)}dd{margin:0}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.pairs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;max-width:620px}figure{margin:8px 0;min-width:0}figure img{width:100%;height:160px;object-fit:contain;background:#eef3f4;border:1px solid var(--line);border-radius:6px}figcaption{font-size:13px;margin-top:4px}
.evidence:target{outline:3px solid #d18a21;outline-offset:5px;border-radius:4px}.source-links{display:flex;gap:8px 18px;flex-wrap:wrap}.budget-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.budget-grid .metric strong{font-size:20px}
details{border-top:1px solid var(--line);padding:12px 0}summary{cursor:pointer;color:#245d70;font-weight:600}.raw{background:#f6f9fa;padding:12px;border-radius:6px;max-height:500px;overflow:auto}
footer{color:var(--muted);font-size:13px;padding-top:12px}@media(max-width:640px){main{padding:22px 14px 40px}section{padding:18px 16px}.status{padding:16px}.metrics,.budget-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.metric{padding:12px}.metric strong{font-size:22px}dl{grid-template-columns:1fr;gap:2px}dd{margin-bottom:10px}th,td{padding:10px 6px}figure img{height:120px}}
@media print{body{background:white}main{max-width:none;padding:0}nav{display:none}section,article,figure{break-inside:avoid}.raw{max-height:none}a{color:inherit}}
"""

STATE = {'COMPLETED':('检查已完成','completed','已完成列明范围的检查；这不代表数据没有风险。'),
         'PARTIAL':('部分完成','partial','存在未完成或未覆盖的检查，不能据此宣布没有风险。'),
         'WAITING_USER':('等待确认','waiting','请查看待确认问题或已请求的人工复核；已有图像证据仍按其原始范围保留。'),
         'FAILED':('执行失败','failed','本次没有形成完整审计；请查看问题和原始记录。')}
GOALS={'content_audit':'图像内容审计','new_entity_generalization':'新实体泛化','same_entity_new_view':'同实体新视角','unspecified':'目标尚未确定'}
KINDS={'byte_identity':'字节相同','pixel_identity':'完整像素相同','perceptual_relation':'待复核的相似线索',
       'declared_entity_overlap':'元数据实体重叠','goal_conflict':'与实验目标冲突','same_source_review':'人工同源确认'}
CALLS={'preflight':'核对输入与 Core','audit':'图像审计','verify':'精确关系复验','interpret_context':'解释目标与元数据','finalize':'生成结论与报告',
       'resume_identity_check':'核对恢复输入','recovery_finalize':'中断后的保守结案','request_review':'请求人工复核','ask_user':'请求澄清'}


def esc(value) -> str:return html.escape(str(value),quote=True)
def number(value) -> str:
    if value is None:return '未记录'
    if isinstance(value,float):return f'{value:,.3f}'
    return f'{value:,}' if isinstance(value,int) else str(value)
def anchor(ref: str) -> str:return 'evidence-'+digest(ref)[:24]
def raw_details(label: str,value) -> str:
    return '<details><summary>'+esc(label)+'</summary><pre class="raw">'+esc(json.dumps(value,ensure_ascii=False,indent=2))+'</pre></details>'
def section(name: str,title: str,body: str) -> str:return f'<section id="{name}" aria-labelledby="{name}-title"><h2 id="{name}-title">{esc(title)}</h2>{body}</section>'
def metric(label: str,value) -> str:return '<div class="metric"><small>'+esc(label)+'</small><strong>'+esc(number(value))+'</strong></div>'


def render(report: dict,evidence: list[dict]) -> str:
    coverage=report['coverage'];budget=report['budget'];task=report['task'];claims=report['claims']
    # The renderer never promotes retained-but-invalid witnesses after input drift.
    accepted=evidence if coverage.get('source_unchanged') is True else []
    evmap={e['evidence_id']:e for e in accepted}
    profiles=coverage.get('profiles',{})
    raw_reports={c['report_ref'] for c in profiles.values() if re.fullmatch(r'tools/call-[0-9]{4,}/output/report\.json',c.get('report_ref',''))}
    def reference(ref):
        return '<a href="#'+anchor(ref)+'">'+esc(ref)+'</a>' if ref in evmap else '<span class="muted">'+esc(ref)+'（本页无已接纳记录）</span>'
    def badge(value):return '<span class="badge '+('confirmed' if value=='confirmed' else 'candidate' if value=='candidate' else 'inconclusive')+'">'+esc(value)+'</span>'
    title,style,explanation=STATE.get(report['state'],('状态未识别','failed','请查看原始记录。'))
    scripted=report['mode']=='scripted_test_only'
    mode='SCRIPTED_TEST_ONLY · 本地脚本决策测试 · 真实 Core · 模型调用：未运行' if scripted else '确定性本地审计 · 真实 Core 0.6.0 · 模型调用：未运行'
    top='<header><div class="eyebrow">EVIDENCE · COVERAGE · BUDGET</div><h1>VisionLeak Investigator</h1><p class="mode">'+esc(mode)+'</p><p class="wrap">'+esc(task['request_text'])+'</p></header>'
    top+='<div class="status '+style+'"><h2>'+esc(report['state']+' · '+title)+'</h2><p>'+esc(explanation)+'</p></div>'
    if coverage.get('source_unchanged') is False:top+='<p class="notice danger">输入在检查期间发生变化。结论已撤回，保留的原始产物不能作为当前数据的有效证据。</p>'
    if report.get('revision'):top+='<p class="notice">这是'+esc(report['revision']['kind'])+'修订：复用已有图像证据，本次未重跑 Core。账本保留此前累计开销。</p>'
    counts=Counter(c['status'] for c in claims)
    pending=[r for r in report.get('reviews',[]) if r['status']=='pending']
    top+='<div class="metrics">'+metric('输入图像',coverage.get('input_preflight',{}).get('image_count'))+metric('已确认结论条目',counts['confirmed'])+metric('不同候选图片对',report.get('unique_candidate_pairs'))+metric('待复核记录',len(pending))+'</div>'
    navigation='<nav aria-label="报告目录">'+''.join('<a href="#'+name+'">'+label+'</a>' for name,label in [('next','待办与问题'),('scope','检查范围'),('claims','结论'),('budget','预算'),('timeline','执行记录'),('evidence','证据'),('records','原始记录')])+'</nav>'

    todos=''
    questions=report.get('questions') or []
    backlog=report.get('question_backlog') or []
    for label,items in [('待确认问题',questions),('尚未请求的必要问题',backlog)]:
        if items:todos+='<h3>'+label+'</h3><ul>'+''.join('<li>'+esc(q['question'])+'</li>' for q in items)+'</ul>'
    if pending:todos+='<p>'+esc(f'还有 {len(pending)} 条待复核记录，其中 {sum(bool(r.get("requested")) for r in pending)} 条已请求人工处理。候选尚未被确认。')+'</p>'
    if report.get('reviews'):
        todos+='<div class="table-wrap"><table><thead><tr><th>候选证据</th><th>复核状态</th><th>请求情况</th></tr></thead><tbody>'+''.join('<tr><td>'+reference(r['pair_ref'])+'</td><td>'+esc(r['status'])+'</td><td>'+('已请求' if r.get('requested') else '未请求')+'</td></tr>' for r in report['reviews'])+'</tbody></table></div>'
    if report.get('issues'):todos+='<h3>未完成项与异常</h3><ul>'+''.join('<li class="wrap">'+esc(x)+'</li>' for x in report['issues'])+'</ul>'
    if not todos:todos='<p>当前没有待确认问题或已记录的异常；这不代表不存在未检测风险。</p>'

    goal=GOALS.get(task['goal'],task['goal'])
    scope='<dl><dt>审计目标</dt><dd>'+esc(goal)+' · '+('来源已确认' if task.get('goal_confirmed') else '待确认')+'</dd><dt>数据引用</dt><dd>'+esc(task['dataset_ref'])+'</dd><dt>原始输入</dt><dd>'+('前后摘要一致（非原子快照）' if coverage.get('source_unchanged') is True else '发生变化或未确认')+'</dd></dl>'
    for name,c in profiles.items():
        scope+='<article><h3>'+esc(name)+' · '+('已完成' if c.get('complete') else '未完成')+'</h3>'
        scope+='<p>'+esc(f'已发现至少 {number(c.get("discovered_at_least"))} 张；已生成指纹 {number(c.get("fingerprinted_images"))} 张；已处理 {number(c.get("processed_images"))} 张。')+'</p>'
        if c.get('reason'):scope+='<p class="notice">停止原因：'+esc(c['reason'])+'</p>'
        if c.get('core_coverage',{}).get('summary'):scope+='<p>'+esc(c['core_coverage']['summary'])+'</p>'
        if c.get('report_ref') in raw_reports:scope+='<a href="'+esc(c['report_ref'])+'">查看 '+esc(name)+' 原始 Core 报告</a>'
        scope+='</article>'
    if not profiles:scope+='<p class="notice">没有已接纳的图像检查范围，不能解释为零风险。</p>'
    metadata=coverage.get('metadata',{})
    scope+='<p>元数据：'+esc(metadata.get('state','未记录'))
    if 'mapped_rows' in metadata:scope+='；映射 '+esc(number(metadata['mapped_rows']))+' 行，未覆盖 '+esc(number(metadata.get('unmapped_image_count')))+' 张图像'
    scope+='。元数据中的实体身份来自登记声明。</p>'
    scope+=raw_details('展开完整覆盖记录',coverage)

    conclusions=''
    for c in claims:
        conclusions+='<article><h3>'+esc(KINDS.get(c['claim_type'],c['claim_type']))+' '+badge(c['status'])+'</h3><p>'+esc(c['statement'])+'</p><div class="source-links">'+''.join(reference(ref) for ref in c['evidence_refs'])+'</div></article>'
    if not claims:conclusions='<p>没有满足前提的结论条目；这不是“未发现风险”的证明。</p>'
    conclusions+='<details><summary>结论边界</summary><ul>'+''.join('<li>'+esc(s)+'</li>' for s in report['limitations'])+'</ul></details>'

    dimensions=[('tool_calls','max_tool_calls','工具调用'),('audit_runs','max_core_audit_runs','审计扫描调用'),('comparisons','max_comparisons_total','比较次数'),('index_operations','max_index_operations_total','索引操作'),('decoded_pixels','max_total_decoded_pixels','解码源像素'),('wall_seconds','max_tool_wall_seconds','累计工具时间 / 秒'),('questions','max_questions','澄清请求'),('review_pairs','max_review_pairs','复核请求')]
    costs='<p>累计已扣账 / 上限。各维度独立计量，不换算为未定价的金额。</p><div class="budget-grid">'+''.join(metric(label,number(budget.get('spent',{}).get(key))+' / '+number(budget.get('limits',{}).get(limit))) for key,limit,label in dimensions)+'</div>'
    costs+='<p>模型执行：'+esc(report.get('model_execution','未记录'))+'。脚本规划请求不作为真实模型调用。</p>'
    unknown=sum(e.get('status')=='unknown' for e in budget.get('entries',[]))
    if unknown:costs+='<p class="notice">'+esc(f'{unknown} 条调用缺少完整用量，已按预留保守扣账；累计值不全是实测开销。')+'</p>'
    if report.get('planning'):costs+=raw_details('展开脚本规划与独立请求账本摘要',report['planning'])
    costs+=raw_details('展开完整预算账本',budget)

    timeline='<p class="muted">按预算账本顺序显示预留与结算。unknown 表示保守扣账；修订报告包含复用证据的历史调用。</p><div class="table-wrap"><table><thead><tr><th>步骤</th><th>动作</th><th>状态</th><th>预留 / 结算时间</th><th>已扣账秒数</th></tr></thead><tbody>'
    for entry in budget.get('entries',[]):
        timeline+='<tr><td><code>'+esc(entry['call_id'])+'</code></td><td>'+esc(CALLS.get(entry['kind'],entry['kind']))+'</td><td>'+esc(entry['status'])+'</td><td><small>'+esc(entry.get('reserved_at','未记录'))+'<br>'+esc(entry.get('settled_at','尚未结算'))+'</small></td><td>'+esc(number(entry.get('actual',{}).get('wall_seconds')))+'</td></tr>'
        if entry.get('error'):timeline+='<tr><td colspan="5" class="notice wrap">'+esc(entry['error'])+'</td></tr>'
    timeline+='</tbody></table></div>'

    witnesses='<p class="muted">证据类型与复验范围保持原样。指纹相似候选未被精确复验，不会自动升级为同源或泄漏。</p>'
    for e in accepted:
        witnesses+='<article class="evidence" id="'+anchor(e['evidence_id'])+'"><h3>'+esc(e['kind'])+'</h3><p><code>'+esc(e['evidence_id'])+'</code></p>'
        if e.get('files'):witnesses+='<p class="wrap">'+esc(' ↔ '.join(e['files']))+'</p>'
        sources=[]
        for source in e.get('source_positions',[]):
            path,_,pointer=source.partition('#')
            if path in raw_reports and (not pointer or re.fullmatch(r'/pairs/[0-9]+',pointer)):
                sources.append(path);witnesses+='<p><a href="'+esc(path)+'">查看原始 Core JSON</a> <small>'+esc(pointer)+'</small></p>'
            else:witnesses+='<p class="muted wrap">来源位置：'+esc(source)+'</p>'
        if len(set(sources))==1:
            prefix=sources[0].rsplit('/',1)[0]+'/'
            images=''
            for img in e.get('images',[])[:2]:
                thumb=img.get('thumbnail','')
                if re.fullmatch(r'thumbnails/[a-f0-9]{64}\.jpg',thumb):
                    images+='<figure><img loading="lazy" decoding="async" src="'+esc(prefix+thumb)+'" alt="'+esc(img.get('path','')+' 的 Core 缩略图')+'"><figcaption>'+esc(img.get('path',''))+'</figcaption></figure>'
            if images:witnesses+='<div class="pairs">'+images+'</div>'
        witnesses+='<p class="wrap">复核状态：'+esc(json.dumps(e.get('verification_state',{}),ensure_ascii=False))+'</p>'
        witnesses+=raw_details('展开此条证据原文',e)+'</article>'
    if not accepted:witnesses+='<p>本页没有已接纳证据。保留的原始产物不会在恢复或输入变化后自动升级为事实。</p>'

    records='<p>这些文件保留原始身份与记录。输入目录不通过本页提供访问。</p><div class="source-links">'+''.join('<a href="'+path+'">'+label+'</a>' for path,label in [('report.json','完整报告 JSON'),('evidence.jsonl','证据账本'),('ledger.json','预算账本'),('coverage.json','覆盖记录'),('manifest.json','运行身份'),('events.jsonl','状态事件')])+'</div>'
    records+=raw_details('本次任务定义',task)
    body=top+navigation+section('next','待办与问题',todos)+section('scope','目标与检查范围',scope)+section('claims','有证据支撑的结论',conclusions)+section('budget','预算与成本',costs)+section('timeline','执行记录',timeline)+section('evidence','证据明细',witnesses)+section('records','原始记录',records)
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>VisionLeak Investigator · '+esc(report['state'])+'</title><style>'+CSS+'</style></head><body><main>'+body+'<footer>VisionLeak Investigator · 静态本地报告 · 不修改源数据 · 本页没有模型调用或外部脚本</footer></main></body></html>'
