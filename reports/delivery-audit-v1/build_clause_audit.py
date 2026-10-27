"""Build a traceable review index; validation checks references, not software correctness."""
from pathlib import Path
import hashlib,json,re
from collections import Counter
from visionleak_investigator.common import PROJECT,now,write_json
from visionleak_investigator.workflow import code_digest
BASE=PROJECT/'reports/delivery-audit-v1'
BUNDLES={
 'core':(['src/visionleak_investigator/core.py','src/visionleak_investigator/runtime.py','core.lock.json','core.runtime.lock.json','scripts/bootstrap_core.py'],['tests/acceptance/test_core_contract.py','tests/security/test_runtime_migration.py'],['reports/core-smoke/receipt.json','reports/environment.json']),
 'loop':(['src/visionleak_investigator/workflow.py','src/visionleak_investigator/domain.py'],['tests/acceptance/test_loop.py','tests/security/test_guards.py'],['reports/demo-rules/report.json']),
 'metadata':(['src/visionleak_investigator/metadata.py','src/visionleak_investigator/domain.py'],['tests/acceptance/test_interaction.py','tests/acceptance/test_metadata_fields.py'],['reports/interaction-contract-binding-v1/receipt.json']),
 'claims':(['src/visionleak_investigator/reporting.py','src/visionleak_investigator/integrity.py','contracts/claim.schema.json','contracts/claim-rules.json'],['tests/security/test_guards.py','tests/acceptance/test_core_contract.py'],['reports/lifecycle-v1/receipt.json']),
 'revision':(['src/visionleak_investigator/interaction.py','src/visionleak_investigator/recovery.py','src/visionleak_investigator/review_state.py'],['tests/acceptance/test_revision_provenance.py','tests/acceptance/test_review_consistency.py','tests/acceptance/test_revision_budget.py'],['reports/review-lifecycle-v1/receipt.json','reports/revision-budget-v1/receipt.json']),
 'budget':(['src/visionleak_investigator/budget.py','src/visionleak_investigator/publication.py','src/visionleak_investigator/resources.py','docs/adr/014-single-pass-finalization.md'],['tests/acceptance/test_resources.py','tests/acceptance/test_finalization_accounting.py','tests/acceptance/test_revision_budget.py'],['reports/finalization-v1/receipt.json','reports/revision-budget-v1/receipt.json']),
 'planner':(['src/visionleak_investigator/controller.py','src/visionleak_investigator/planner_host.py','src/visionleak_investigator/planning.py','src/visionleak_investigator/model_budget.py','src/visionleak_investigator/openjiuwen_runtime.py'],['tests/acceptance/test_planned_loop.py','tests/unit/test_model_budget.py','tests/unit/test_planner_gate.py'],['reports/controller-sdk/receipt.json','reports/sdk-smoke/receipt.json']),
 'rules':(['src/visionleak_investigator/rules.py','configs/policy.json','docs/adr/012-rules-context-routing.md'],['tests/acceptance/test_rules_routing.py','tests/unit/test_rules_policy.py'],['reports/rules-routing-v2/receipt.json']),
 'proposal':(['src/visionleak_investigator/plan_check.py','src/visionleak_investigator/proposal_export.py'],['tests/acceptance/test_plan_check.py','tests/acceptance/test_proposal_export.py'],['reports/plan-check-v1/receipt.json','reports/proposal-export-v1/receipt.json']),
 'report':(['src/visionleak_investigator/presentation.py','docs/REPORTS.md'],['tests/acceptance/test_report_presentation.py','tests/acceptance/test_finalization_accounting.py'],['reports/report-demo-final/receipt.json','reports/visual-review/report-v2-final/receipt.json']),
 'evaluation':(['src/visionleak_investigator/evaluation_data.py','src/visionleak_investigator/evaluation_runner.py','src/visionleak_investigator/evaluation_scoring.py','src/visionleak_investigator/interaction_evaluation.py','src/visionleak_investigator/interaction_scoring.py','docs/EVALUATION.md','docs/INTERACTION_EVALUATION.md'],['tests/acceptance/test_evaluation_data.py','tests/acceptance/test_catalog_execution.py','tests/acceptance/test_interaction_evaluation.py','tests/acceptance/test_interaction_binding.py'],['reports/catalog-rules-v2/receipt.json','reports/interaction-contract-binding-v1/receipt.json']),
 'delivery':(['README.md','docs/API.md','docs/ARCHITECTURE.md','docs/AI_USAGE.md','docs/DEMO.md','docs/SUBMISSION_DRAFT.md','THIRD_PARTY_NOTICES.md','.github/workflows/ci.yml','STATUS.json'],[],['reports/commands.jsonl','reports/publication.json','reports/licenses/base-dev-v3.json']),
}
R=[]
def add(doc,lo,hi,bundles,status,note):R.append(dict(document=doc,start=lo,end=hi,bundles=bundles.split(),status=status,assessment=note))
# These range assessments are a manual review of the source clauses and referenced
# implementation/tests. They are not automatically inferred from test-file presence.
P='passed_scoped';V='documented_variance';B='blocked';D='deferred';H='reference_only'
add('01',1,29,'loop metadata rules revision proposal',P,'本地真实 Core/规则完成所列流程；自主模型理解未验收，元数据结论只代表声明。')
add('01',30,35,'evaluation',B,'可证伪比较机制已实现；C 对 D 的产品/研究收益尚无真实模型与真人证据。')
add('01',36,50,'core delivery',P,'Core 算法与 Investigator 编排新增贡献分列；历史 0.5.0 不用于执行。')
add('01',51,62,'loop planner evaluation',B,'本地子集已通过；必须项中的真实 Agent、D 仍受阻，E 由修订计划后置。')
add('01',63,72,'loop planner delivery',P,'不含源码自改、群体 Agent、任意执行、训练或自动修改数据；阈值/工具池固定。')
add('01',73,117,'core planner report',P,'精确 Python/Node/SDK 锁，CLI、JSON 持久化、静态页和共用门禁已实现；SDK 仅无模型工作流。')
add('01',118,132,'planner claims budget',P,'有界宿主动作与真实工具已验证；动作来自脚本回调，不宣称模型自适应。')
add('01',133,140,'evaluation',D,'M4/E：候选提案、验证选择与真实优化未实现，按修订明确留到第二阶段。')
add('01',141,144,'delivery',P,'未引入 Harness 上游执行器；只有设计参考，无继承其不受限网络/沙箱设置。')
add('01',145,158,'planner proposal',P,'七种白名单动作通过宿主门禁，建议由确定性后处理生成；仅本地控制器验收。')
add('01',159,164,'report planner delivery',B,'受控真实 Core 演示与规则基线有记录；模型提问/决策演示等待真实轨迹。')
add('01',165,177,'evaluation delivery',P,'收缩条件和证据边界已记录；无未测收益或自然数据结论。比赛权属确认仍外部。')
add('01',178,182,'core evaluation',B,'0.6.0 已锁；首版真实 Agent 与 A–D 目标仍未完成，不能按本地测试替代。')
add('02',1,34,'delivery',V,'采用平面 Python 模块而非建议的多层目录；源码/依赖/运行产物隔离，凭据不入库。')
add('02',35,46,'core',P,'独立发布副本、提交/产物/runtime 锁与 capabilities 实测；未重新编译 MoonBit，记录发布产物。')
add('02',47,69,'core loop rules',P,'固定四 profile、阈值 6、全目录扫描与最多三次 audit。重复调用拒绝，失败保守停止；未实现可选一次重试。')
add('02',70,77,'core',P,'真实 0/2/3/4 命令语义已保存；正常适配器不传 fail-on。')
add('02',78,83,'core loop revision',P,'唯一输出目录、原始日志、Core 身份校验、前后输入摘要；非签名/强快照。')
add('02',84,100,'loop metadata planner',P,'TaskSpec/schema、逻辑 registry、宿主确认、预算/隐私不可由动作修改。')
add('02',101,112,'metadata',P,'CSV 映射、目录 split、实体确认、缺列/缺值/冲突/未映射范围有记录；不推断自然实体。')
add('02',113,116,'metadata rules planner',P,'登记文档 1 MiB 上限、前 8000 字符片段/摘要；说明不可提升权限，远程披露未启用。')
add('02',117,134,'planner claims',P,'严格 action 结构/引用/有限纠错/重复拒绝与白名单；全部模型相关断言限脚本测试。')
add('02',135,156,'revision budget',V,'WAITING_USER 退出、不可覆盖 revision、原子 checkpoint 与累计账本已验；崩溃仅保守 PARTIAL 结案，不恢复 Core 扫描。')
add('02',157,168,'delivery evaluation',V,'实际 CLI 必须给 --registry；catalog 用 eval-validate/freeze/check/run/interaction，evaluate 留作合成工程集；optimize 后置，agent 拒绝。见 API/ADR006。')
add('02',169,171,'loop',P,'宿主退出 0/2/3/1 与 Core 分开；未授权 agent 不回退 rules。')
add('02',172,181,'claims metadata',P,'图像关系/用户来源声明/目标风险分层；没有统一泄漏分数或训练污染断言。')
add('02',182,192,'claims revision',P,'每个见证保留参数/位置/身份、无序 pair 去重、人审来源绑定且类型不升级。')
add('02',193,200,'claims',P,'Claim schema 与确定性模板/蕴含前提；unsupported 被拒绝，未由自然语言生成事实。')
add('02',201,208,'loop metadata revision',P,'输入、各 profile、元数据、复验与人审分开；完整 base 与部分补查不互相替代。')
add('02',209,238,'budget planner',V,'预留/结算/未知/重复审计与模型纠错本地验证；协作式时间预算，记录实际超支。结算自身写入有 ADR014 边界，完整进程另测。真实费用未运行。')
add('02',239,249,'proposal',P,'建议 JSON/CSV/新映射、test 保护、已知冲突 plan-check；不修改数据、不声称重审/重训完成。')
add('02',250,259,'loop planner report',P,'路径/HTML/CSV/提示注入门禁，静态页无写接口；无 provider/远程图片，TLS 配置不能作为真实网络验收。非 OS 沙箱。')
add('02',260,282,'loop report revision',P,'完整成功/部分运行保存列明产物；写入失败保留原件和 failure 收据，不能伪造完整 report。公开仅授权合成记录。')
add('02',283,293,'core claims revision budget',P,'已单独验证 capabilities、候选 skipped、processed 前缀、split/plan-check、身份/人审区别及 revision 证据复用。')
add('03',1,12,'evaluation delivery',P,'工程、产品价值、研究增益分列；只有工程证据，研究增益未建立。')
add('03',13,22,'evaluation rules',B,'A/B/C 真实执行，B 单次 all；D 逐项 blocked，E deferred。A–D 主比较尚未完成。')
add('03',23,34,'evaluation budget',V,'catalog 同输入/锁/总上限、独立交互、失败与完整分母均验收；独立进程不共享指纹，OS cache 未清空，不称物理 cold benchmark。')
add('03',35,44,'evaluation',P,'任务 image_split 与 benchmark_partition 分离；来源/实体/会话/派生连通组隔离，不把 pair 当独立样本。')
add('03',45,50,'evaluation',P,'Core 历史来源 hash/URL/派生仅 development；新自然 test 尚未收集。')
add('03',51,64,'loop evaluation claims',P,'合成复制/重编码/旋转/非对齐裁切+缩放、独立负例、缺失/坏图/注入已验；自然来源/混合变换研究覆盖不作完成声明。')
add('03',65,73,'evaluation',B,'12 任务达到工程起步；10+10+30 自然研究规模及每任务真实 D 重复均未执行，建议规模非功效保证。')
add('03',74,79,'evaluation',P,'来源许可字段、摘要、再分发声明和全任务真值隔离门禁已验；声明不是权属认证，新数据实验需授权。')
add('03',80,89,'evaluation',P,'catalog 独立 scorer 区分精确/非精确、全量 FN、部分标签 unknown、N/A 和完整候选负担；legacy evaluate 仅工程 smoke。')
add('03',90,97,'evaluation metadata',P,'独立交互契约绑定提问/答案/目标/风险和无依据断言；脚本回答，不是真人价值证据。')
add('03',98,106,'budget evaluation planner',P,'真实逐工作进程 CPU/wall/采样进程树 RSS；短峰/短进程及整管线 RSS 局限明确；真人时间与 provider usage 未测。')
add('03',107,118,'evaluation',D,'M4 提案/validation 选优/E 冻结比较未实现；不把枚举或手写规则称作自动优化。')
add('03',119,132,'budget evaluation',D,'在线资源单位分别记录；C_opt 与摊销无真实优化输入，未输出虚构美元或回收次数。')
add('03',133,140,'claims budget loop',P,'局部门禁、输入不变/无外发、候选不升级验收通过；时间超支故障如实保留，不作硬预算零超支承诺。')
add('03',141,152,'evaluation delivery',B,'收益与收缩均是预登记规则；C/D、真人工时和自然精度未知，不能宣布满足研究目标。')
add('03',153,158,'evaluation',P,'catalog 输出 schedule/config/source/per-run/failures/metrics/costs/summary 与原始索引。')
add('03',159,165,'evaluation core rules',B,'版本同一和 B 例外已验；完整 A–D 仍待真实授权数据/模型，E 不阻塞首版。')
add('04',1,8,'delivery',P,'保留命令/退出码/日志/版本/失败与下一步；状态不替代证据。')
add('04',9,24,'core delivery planner',P,'M0：独立项目、真实发布锁/四类 CLI/环境与无模型 SDK smoke；不等待新版 Core。')
add('04',25,41,'loop claims budget report',P,'M1：真实确定性闭环、可追溯证据/覆盖、原图不变/部分结果、CLI；计量边界按 ADR014。')
add('04',42,56,'metadata revision proposal rules',P,'M2：确认/复核/修订、强规则上下文路由和只读建议；恢复限制已声明。')
add('04',57,73,'planner',B,'M3.1/.2/.3/.5 本地测试与无模型 SDK完成；.4 无 provider 选择/披露/预算契约，.6 两条真实轨迹未执行。')
add('04',74,89,'evaluation',D,'M4 明确后置，optimizer 与 E 未实现。')
add('04',90,104,'evaluation report delivery',B,'M5 本地执行器/页面/生成器/文档/稿件完成；独立自然数据和 D 未完成，视频未录制。')
add('04',105,139,'loop evaluation planner',P,'T01–T28 逐项见 requirements.json；T22 后置，其余均有明确 scope，不把脚本测试当真实 Agent。')
add('04',140,146,'delivery core',P,'双平台干净安装/真实 Core/无模型 CI；Linux 业务禁网，macOS 不宣称 OS 隔离。正式新数据/模型独立授权。')
add('04',147,161,'delivery',P,'各阶段文件、累计工作日志与机器可读状态/命令索引均保留，旧失败不抹除。')
add('04',162,167,'delivery',P,'交付清单有文件索引；排除凭据、真实私有图像与无授权素材，许可尚未由作者选择。')
add('04',168,182,'core evaluation',B,'T29–T35 本地通过；首版顺序的真实 M3/D 尚未完成，M4/E 按修订后置。')
add('07',1,12,'core',P,'独立 0.6.0 ZIP 与 SHA/来源、固定编译和 runtime 锁；capabilities 非执行证明，补真实 smoke。')
add('07',13,20,'core loop proposal',P,'四种全目录 profile、目录 split；不支持增量/缓存/语义/v2/CSV 重分组，plan-check 不声称重审。')
add('07',21,28,'core claims revision',P,'命令级退出码与身份/精确复验/人审三类状态分开；local-only valid=0 不升级。')
add('07',29,39,'loop budget',P,'枚举/指纹/processed 前缀、索引/解码量分列；预检像素与未知 header 可见，坏图像素保守计量。')
add('07',40,54,'budget planner core',V,'audit/verify 配额及结案预留已验，unknown 不免费；宿主协作式时限/计量提交边界非 OS 硬上限，真实模型费用尚未验收。')
add('07',55,60,'claims metadata',P,'固定 schema/规则/模板，不以引用存在替代支持；声明实体只支持相应目标风险。')
add('07',61,67,'core evaluation',P,'锁变化显式迁移/重跑，平台 runtime 可变化但关键语义固定；评测锁不一致拒绝，升级收益不归因 Agent。')

DOCS={k:next((PROJECT/'docs/planning').glob(k+'_*.md')) for k in ('01','02','03','04','07')}
# Retain one record for every nonblank nonheading line: list/table/code lines
# remain individually locatable even when they share the same review finding.
clauses=[];sections=[]
for i,row in enumerate(R,1):
 p=DOCS[row['document']];lines=p.read_text().splitlines();refs={key:sorted(set(v for b in row['bundles'] for v in BUNDLES[b][j])) for j,key in enumerate(('implementation','tests','evidence'))}
 section={**row,'review_id':f'R{i:03d}','source':str(p.relative_to(PROJECT)),**refs};sections.append(section)
for key,p in DOCS.items():
 for lineno,line in enumerate(p.read_text().splitlines(),1):
  if not line.strip() or line.startswith('#') or re.fullmatch(r'\s*\|?[\s|:-]+\|?\s*',line):continue
  rows=[r for r in sections if r['document']==key and r['start']<=lineno<=r['end']]
  assert len(rows)==1,(key,lineno)
  clauses.append({'clause_id':f'{key}:L{lineno}','source':str(p.relative_to(PROJECT)),'line':lineno,'text':line,'review_id':rows[0]['review_id'],'status':rows[0]['status']})
for row in sections:
 for group in ('implementation','tests','evidence'):
  for ref in row[group]:assert (PROJECT/ref).is_file(),ref
requirements=json.loads((BASE/'requirements.json').read_text())
assert len(requirements['matrix'])==35 and {r['requirement'] for r in requirements['matrix']}=={f'T{i:02d}' for i in range(1,36)}
for row in requirements['matrix']:
 if row['source']:
  assert row['test'] in (PROJECT/row['source']).read_text(),row
record={'audit_status':'review_complete_with_explicit_exceptions','implementation_complete':False,'created_at':now(),'reviewed_code_digest':code_digest(),'reviewed_commit':'3146889f60274866955845dfcdbaef183628a139','method':'Manual implementation/test/receipt review grouped by source ranges. Every content line is indexed; references checked mechanically. Index validity is not proof of runtime correctness, exhaustive security, model performance, or independent human review.','documents':{str(p.relative_to(PROJECT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in DOCS.values()},'sections':sections,'clauses':clauses,'counts':dict(Counter(r['status'] for r in sections)),'T01_T35':'reports/delivery-audit-v1/requirements.json','regression':'reports/logs/20261026T235150644662-finalization-regression.log','remaining_required':['M3.4 selected provider/model/endpoint, explicit disclosure and spend contract; implement adapter after selection.','M3.6 at least two actual authorized model trajectories, including clarification and evidence/stop.','M5 authorized independent natural sources, source grouping, frozen C/D comparison and measured research results.','Owner project license and competition decisions; do not infer them from public-repository authorization.'],'deferred':['M4/E optimizer, candidate selection and amortized comparisons after stable real Agent.'],'review_only':['Planning 05/06 are historical competition/source references; current submission/AI/third-party documents preserve their boundaries. No current legal/competition eligibility or deadline was asserted.'],'local_actionable_findings':[],'scope_exceptions':['Cooperative tool wall-time, explicit accounting commit, sampled RSS; no hard OS budget or atomic snapshot.','Crash recovery produces conservative PARTIAL, no Core resume.','CLI catalog commands differ from planning example; see docs/API.md and ADR006.','Fresh CLI processes without shared fingerprints; OS caches not flushed.','Local controlled/scripted acceptance only; model_calls=0, human_participants=0.','Historical ADRs/receipts are snapshots; later ADRs supersede them without altering their bytes.'],'fixed_during_review':['docs/DEMO.md obsolete next step corrected to acknowledge completed evaluation executor.']}
write_json(BASE/'clauses.json',record)
print(json.dumps({'audit_status':record['audit_status'],'review_sections':len(sections),'indexed_content_lines':len(clauses),'T_cases':35,'counts':record['counts'],'local_actionable_findings':0,'model_calls':0}))
