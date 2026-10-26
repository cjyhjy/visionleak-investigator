# 实施日志

2026-10-26：按 00→AGENTS→01→02→03→04→07/08 阅读。独立项目创建；原 Core 只读。

M0：本地发布 ZIP 的 SHA-256、源码摘要和编译产物全部匹配 0.6.0 锁。Python 3.12.14 / Node 26.7.0 / sharp 0.35.5。首次沙箱依赖下载 DNS 失败；获网络安装权限后仅下载依赖，未调用模型。openJiuwen 0.1.19.post2 的真实本地工具工作流通过。

M1：先记录缺模块的 red 测试，再实现。CLI 契约、输入不变、预算、报告身份、安全测试 25 passed。保留了失败日志（含测试 fixture 未产生 candidate 的错误），补充 all-profile 实测后修正。原始开发包未改写。

所有实际命令、退出码和日志：reports/commands.jsonl。模型调用=not_run。

M2：目标/实体语义、CSV 冲突、WAITING_USER、用户回答 revision、人工复核、只读建议、保守崩溃恢复完成。7 项交互专项通过，后续加入累计 revision 预算与三次 audit/verify 预算测试。真实用户未参与；interaction-demo 的回答明确为 scripted user fixture，不是模型实验。

M3：SDK 工作流与本地 ToolGate/结构化规划接口已落地；3 项结构纠错/门禁测试通过。没有 provider adapter、没有真实模型调用；M3.2/3.4/3.6 保留未运行或受阻。

M5：12 个合成任务 x A/B/C = 36 次真实 Core 条件运行（30 COMPLETED、6 PARTIAL）；D 12 次 blocked，E 未运行。B 每任务只 all 一次。真值在 evaluator-truth，生产 registry 不暴露；未采独立自然图像 test，未报告算法收益。

干净 Python 环境：13 个基础开发依赖，不安装 agent extra，完整测试 40 passed；额外 schema 向前兼容测试单独通过。所有代码在独立本地 Git 项目中，未提交/推送；实际版本用 reports/source-manifest.json 和各 run manifest.code_digest 标识。原 Core scoped git status 无变化。

恢复命令：`.venv/bin/vli demo --out runs/next-fixture`，随后按 README run；继续模型前需用户显式选择服务和授权预算。目前无需任何模型即可复现本地工作。

最终交付复验：delivery-regression 在干净 Python 环境 41 passed；delivery-demo 使用当前代码与真实 Core 再次运行 base+all。新增字段兼容测试首次保留旧 auditId 因身份校验正确失败；改为测试fixture使用真实Core重算新身份后通过，没有放松验证器。所有失败日志保留。建议manifest现保存实际结构检查和仍存已知冲突；所有Node子进程均清理非白名单环境变量。

公开归档准备：负责人明确授权建立并推送独立公开 GitHub 仓库 cjyhjy/visionleak-investigator；仓库已创建，首次推送待核验。提交范围为实现、原始设计、合成数据和工程验收记录；依赖、虚拟环境、根目录临时运行与 SDK 日志排除。修正忽略规则，保留 reports/logs 与 reports/engineering-suite/runs 原始证据。对 1887 个待提交文件（约 12 MB）扫描，未发现所检查的凭据模式、符号链接或超 10 MiB 文件。没有代码运行逻辑变更，沿用 delivery-regression 的 41 passed 结果。

公开推送完成：实现提交 `2a7bfb5222e24e3e247566fe6182fb4d4bb53c79` 已推送 main；GitHub API 返回 PUBLIC，远端 refs/heads/main 与本地提交一致。命令与回执见 reports/publication.json。本条为后续文档记录，不改变代码与测试结果。原始设计快照及历史原始日志保留其空白格式，实现文件的 diff whitespace 检查通过。

自主推进 / 复现与 CI：显式平台运行锁迁移、SHA 验证下载、双平台无模型 CI 已实现。本地 platform-regression 46 passed；platform-current-lock 确认旧运行锁未变化。Linux/macOS 远端结果待实际运行；模型仍为 not_run。

CI 首次运行 40384746048：Linux/macOS 均在安装后被 symlink 门禁拒绝。实际 npm ci 会创建未使用的 .bin/semver 软链接，而早期本地 staging 副本未带此链接。安装增加 --bin-links=false，保留原有禁止 symlink 的运行边界；原始失败日志存 reports/ci-history/40384746048-failed.log。真实契约测试尚未在该次 CI 执行，不记通过。

CI 第二次运行 40384953736：macOS 完整通过；Linux 46 项测试和全新 base+all 审计通过，但上传 root 拥有的 0600 checkpoint 文件失败。修正为创建隔离网络后降回 runner UID/GID 执行，保留文件最小权限。失败日志原样保留。

M3 本地后续：新增独立持久化模型预算账本（无模型客户端）。decimal 费用、调用前预留、usage 缺失保守结算、超额停止、绑定不变的恢复与无重放恢复均有专项测试。完整回归 59 passed；尚未接入实际 Planner 循环/提供商，不能作为真实 Agent 验收。状态生成脚本首次误用系统 Python 3.9 导入项目失败，已改用项目 Python 3.12，不影响已完成测试。

CI 第三次 40385473497（6f823de）完整通过：Ubuntu 24.04 与 macOS 14 各 59 项测试，新 base+all 真实审计完成且产物上传成功。下载实际产物后，本地再次验证 JUnit、checkpoint/report digest、evidence hash 和四份真实 Core 报告身份。完整证据与校验回执位于 reports/ci-history/40385473497。模型调用仍为 0。

自主推进 / Planner：共用审计操作重构先跑 59 passed；接入循环后新增 18 项真实 Core 控制器验收，完整回归 77 passed。实际 SDK dispatch 的补充取证/澄清脚本场景通过并保留 trace、报告、账本；非真实 Agent 实验。新增 ledger 摘要校验、脚本来源保留、输入变化后撤回 claims/建议、已请求复核首次导入不双扣预算。命令与日志沿用 reports/commands.jsonl。

控制器 CI 40387674329（9829ed5）通过：Ubuntu/macOS 各 77 passed，规则新审计及两个 SCRIPTED_TEST_ONLY 控制器场景通过。实际产物下载到 reports/ci-history/40387674329；M3-ci-artifact-integrity 重核六份宿主报告及其 Core 报告、evidence/model-ledger hash 和 JUnit 通过。

依赖通知清单：基础环境 13、SDK 环境 162 个已安装 Python distribution，Core+Node 依赖 7 项。实际许可证/通知文件摘要、元数据与采集脚本保存在 reports/licenses；保留首次过宽的文件名前缀采集，v2 排除源码扩展名。openJiuwen/docx2txt 缺结构化 license 字段，已核对安装包 LICENSE 文件标题，不推定未知许可；未给 Investigator 新设许可证、未发布依赖包。

资源与评测隔离：新增 psutil 7.2.2 锁、OS CPU 与完整任务进程树 RSS 采样。初次 macOS 沙箱无法枚举进程的失败日志保留；权限不足现明确写 partial/null，不再中断审计。可读进程元数据的本地真实测试通过。新版 eval-validate/freeze/check 绑定来源分组、派生关系、历史 Core 来源、全任务真值隔离、代码/策略/依赖与协议；只做配置门禁，不把合成分区 fixture 说成自然测试集。

本批完整回归先 94 passed；扩展冻结与跨任务真值测试后 101 passed/1 failed（额外数据集测试样本没有图像，先被既有输入门禁拒绝）。补齐真实图像 fixture 后 resource-freeze-regression-final 为 102 passed。evaluation-gate-cli 实际执行 9 条 CLI，包含 3 次预期拒绝；原冻结在负例后仍能校验。全部日志与退出码见 reports/commands.jsonl。

frozen-resource-engineering-suite 在固定实现下再跑 12 个合成任务 × A/B/C，共 36 次真实 Core 条件运行：各 10 COMPLETED + 2 PARTIAL，D 12 blocked。每条件 12 次 CPU/RSS 均有实测；A/B/C CPU 总和分别 7.082670/8.157289/10.613831 秒，最大采样树 RSS 分别 121274368/136642560/135528448 字节。只作本机工程资源记录，无自然场景/模型增益结论。新目录 reports/engineering-resources-frozen；先前运行 reports/engineering-resources 及所有旧证据不覆盖。代码快照 reports/source-manifests/resources-and-provenance.json。v3 许可清单增加 psutil 后基础/SDK Python 包为 14/163 项。

当前待办：为登记 catalog 接通真实 A/B/C 运行、独立来源准备、页面视觉验收和演示复验；模型接入/真实 D 等授权，M4 继续后置。跨平台 CI 已加入来源 CLI 和资源评测，尚待此次推送后的实际结果。模型调用 0，原 Core 未改。

资源/来源实现已提交并推送 `54df5312b2ce9754eab0f560e43f4fae951eac4d`。CI 40391572151 在 Ubuntu 24.04/macOS 14 各 102 passed、零 skip，CLI 来源冻结/预期拒绝和每平台 9 次 A/B/C 资源运行通过。两份原始 ZIP 与 GitHub artifact SHA-256 一致；只提取当前 CI 输入、产物和命令日志，保存在 reports/ci-history/40391572151。本地复核 24 份宿主报告及其 Core 身份/claims/input/evidence/model-ledger hash、18 份完整任务资源收据及 18 条来源 CLI 命令，结果 passed。历史绝对 registry 未改写，只在验证器中映射下载路径。

Chrome 页面初验：实际打开完成、预算不足、脚本控制器待澄清三个已保存报告，截图与可访问文本确认状态、模式和局限标识可见。发现覆盖/预算是长 JSON，缺少直接证据导航和简洁工具时间线，状态记 needs_improvement 而不是完成。记录 reports/visual-review/initial/observations.json；仅 127.0.0.1 临时服务，检查后已停止。无模型调用，无自然测试结果；该发现成为下一步本地工作。

报告页面改进：新增独立静态 presentation 模块，首页显示状态/待办/覆盖/预算，区分指纹数和处理数，候选链接到证据卡片、Core 缩略图与原始 JSON。执行记录来自实际账本预留/结算，完整 JSON 仍可展开；修订明确复用图像证据、未重跑 Core。无脚本、无表单、无远程资源；固定路径白名单和属性转义，输入变化/保守恢复不把未接纳原始产物显示为有效证据。

报告验收首次 23 passed/1 failed：测试把 section 标题 evidence-title 当成证据卡片；改为检查实际 evidence ID 对应的片段。新增真实 Core 链接/缩略图摘要、预算不完整、目标修订、注入与输入变化测试，最终 report-final-regression 为 106 passed。report-final-demo 生成 5 个新报告（3 次审计+2 次保留证据的修订）；report-final-controller 运行两条醒目标注 SCRIPTED_TEST_ONLY 的控制器测试。合成来源、脚本回答和复核在页面与收据标明；没有真人参与或模型请求。

Chrome 实际验收：桌面与临时 390×844 窄屏下查看 6 个最终报告，证据片段、缩略图、原始 JSON 导航、折叠明细、预算和修订提示可用，无采样页面横向溢出。8 张截图、DOM 与服务日志保存在 reports/visual-review/report-v2-final。立即读取 lazy 图片时 ready=false，随后的真实截图已显示图片；保留早期采样，未伪造最终 DOM-ready 断言。直接 file:// 核验被浏览器 URL 策略拒绝（仅支持 http/https），未绕过，不宣称验证直接文件模式。临时视口已恢复、本地服务已关闭。新文档 docs/REPORTS.md 与更新的三分钟脚本 docs/DEMO.md 对应实际产物；没有录制视频。当前代码快照 reports/source-manifests/report-presentation.json，等待推送后双平台 CI。

报告实现提交 `09abc4f698f96db59a779bf179f1b6c5ddd7a8c1` 已公开推送。CI 40395014802 在 Ubuntu 24.04/macOS 14 各 106 passed、零测试 skip；两平台真实 Core 审计、脚本控制器、来源门禁、资源评测与报告演示均通过。下载的原始 ZIP 与 GitHub artifact SHA-256 一致；`report-ci-artifact-integrity` 退出码 0，复核 34 份宿主报告及其 Core 身份/claims/输入和账本摘要、页面链接/缩略图与 18 份任务资源收据。原始证据见 reports/ci-history/40395014802/verification.json。模型调用仍为 0，catalog 执行器、独立自然数据和真实 Agent 实验仍未完成。

catalog 执行器已实现：严格 evaluator-only 真值 schema、冻结 metric_definition=catalog-pairs-v1、同输入/总预算 A/B/C 真实工作进程、独立评分进程、执行前后冻结检查、完整预登记次数与 test 首次执行/replay 标记。完整/部分标注分开；未知候选不算假阳性；失败工作进程的已知正例保留在分母，评分失败则拒绝成功子集汇总。命令/环境/资源/原始证据和未运行条目均保留。没有模型请求或新自然数据采集。

专项验收先 5 passed，再 8 passed；集成发现规则的 max_core_audit_runs=1 会在基础扫描前拒绝补充计划，修正为执行 base 并明确 PARTIAL 和未执行 profile；显式非法 profile 列表仍拒绝。加入真实子进程启动失败（缺失可执行文件）的受控故障验收，未替换 Core 检测器。catalog-full-regression 为 114 passed/1 skipped（沙箱禁止进程枚举）；在可读取进程资源权限下复验 catalog-full-regression-process-access 为 115 passed、零 skip。日志见 reports/commands.jsonl。

catalog-frozen-cli 通过：12 个全新受控合成任务，development=10/validation=1/test=1，36 次真实 A/B/C 运行；每条件 10 COMPLETED+2 PARTIAL，D 共 12 blocked，E not_run。所有任务 CPU/RSS 资源收据与独立评分保存，报告/原始 Core 身份再验通过；普通重复 test 请求退出 1，未创建新实验目录。该分区命名只验证执行管线，不能称独立自然测试或 Agent 收益。证据 reports/catalog-execution-v1/receipt.json；源快照 reports/source-manifests/catalog-execution.json。新增 docs/EVALUATION.md 与 ADR-006，CI 已接入新的三任务 catalog smoke，远端结果待推送核验。
