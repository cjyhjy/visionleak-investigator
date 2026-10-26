# 02｜接口契约、状态与安全边界

本文定义 Investigator 的目标接口；不是声称已有 Core 提供这些高层能力。示例 JSON 见 `examples/`。

## 1. 项目目录建议

```text
visionleak-investigator/
  AGENTS.md
  README.md
  pyproject.toml / uv.lock
  src/visionleak_investigator/
    cli.py
    domain/         # task, action, evidence, coverage, budget, state
    adapters/       # core_cli, openjiuwen_runtime, model, context_reader
    tools/          # audited wrappers, group_check, verify
    workflows/      # state_machine, action_guard, resume
    policies/       # rules, llm_planner, optimizer, policy_validation
    reporting/      # claim_validator, merge, render, proposals
  contracts/        # JSON Schema，与类型模型一致
  configs/          # 默认配置/冻结策略，不含凭据
  tests/
    unit/ integration/ acceptance/ security/
  evaluation/
    runner.py scorer.py baselines.py split_sources.py
  demo/             # 合成生成器、说明与演示脚本
  docs/adr/         # 架构决定
  reports/          # 可公开的运行/验收证据，不能含用户数据
  .deps/            # 固定 Core 副本，gitignored
  runs/             # 运行产物，gitignored
```

源码与用户数据、评测真值、运行产物分开。`.env`、凭据、真实数据及可识别元数据不得入 Git。规划包可保存到 `docs/planning/`，不要让旧规范与实现规范悄悄分叉。

## 2. CoreAdapter：必须真实接通

### 2.1 依赖锁定

- 仓库：`cjyhjy/moonbit-visionleak`。
- 当前开发依赖：Core 0.6.0，提交与摘要以 core.lock.json 为准；启动时查询 capabilities 并按 07_CORE_INTEGRATION.md 核对。
- 原规划阅读的 0.5.0 提交保留在 SOURCE_BASELINE.json，仅作历史来源；0.6.0 仍为 npm private，不假定有同名 npm 可安装包。
- 将固定提交 checkout 到独立 `.deps/visionleak-core`，不操作用户原 Core 工作树。允许用户指定另一已验证只读副本，但必须校验 SHA/构建产物。
- 用户工作区无网络时，使用现有可确认的副本；拿不到真实 Core 就将集成标记 blocked，不用假实现冒充。
- 依赖安装仅在项目局部目录执行，审查安装脚本并保存锁文件。构建/测试写入独立副本是允许的；冻结验收后记录产物摘要，正式审计阶段不改依赖。
- M0 记录 Python、Node、MoonBit（如构建）、sharp、Core commit、CLI/构建产物 SHA-256 与平台。不要拿文档版本号代替实际环境。

### 2.2 第一版只用 CLI，不假定增量能力

已核查的基本形态：[S3]

```sh
node <core>/tools/cli.mjs audit --root <dataset> --out <new-output>
node <core>/tools/cli.mjs verify --report <report.json> --root <dataset>
node <core>/tools/cli.mjs export-html --report <report.json> --out <evidence.html>
```

调用必须是 argv 数组，`shell=False`。模型不能设置 executable、cwd、路径或任意参数。stdout 是运行摘要，完整证据在报告文件中；不能把 stdout 摘要当完整报告。

第一版 profile 都对已登记的完整数据集重扫，不声称 Core 已有断点扫描、增量查询、按 pair 验证候选或缓存接口。重复解码/扫描全部计费。未来需要缓存/子集工具时另建契约和公平基线，不偷偷缩小检查范围。

| profile | 固定参数 | 意义 |
|---|---|---|
| `base` | threshold=6；三种扩展均关闭 | 字节/像素/全图 dHash 基础审计 |
| `transform` | `--include-mirrors --include-rotations` | 基础 + 方向变换候选 |
| `local` | `--include-crops` | 基础 + 局部窗口候选 |
| `all` | 上述三开关全开 | 同工具池的强检测基线 |

阈值 6 是冻结初始配置，不是宣称最优。运行时不可调。若后续开发集验证了其他阈值，须形成新 profile 版本，并对所有基线公平开放。基础扫描先强制执行；后续相同 profile/输入/参数的重复调用默认拒绝，预算不足的重试仅在剩余预算和明确失败原因允许时一次执行。

### 2.3 退出码不能混淆

M0 必须实测命令级退出码。当前文档给出：普通 audit 完成可为 0（即使发现重复），不完整可为 2，致命错误为 1；使用 `--fail-on` 命中时为 3；`verify` 发现缺失/失效证据为 4。[S3]

首版常规 adapter 不传 `--fail-on`，从报告获取发现与完整性。适配器仍应正确识别 code 3 是可能有合法报告的关卡命中，不把它当进程崩溃或“无发现”。code 0 也不代表无重复。

若文档与实际固定版本不一致：保留实测日志，更新专属 adapter 契约与 ADR，禁止修改 Core 以迎合假设。

### 2.4 输出安全

报告目录必须位于本次 run 专属目录，与 dataset 互不包含；不用 `--force`。解析后检查 schema、路径/资源边界、`auditId`、引擎信息与实际输入版本。调用 Core 导出/验证逻辑或固定版本提供的验证接口，不重写不兼容的 auditId 算法。

`auditId` 是内容身份，不是签名或来源认证。保存原始 stdout/stderr、原始报告和 wrapper envelope。取证前后检测输入变化；变更后旧结论失效，要求新 run。对不可信本地管理员不能承诺防篡改。

## 3. 输入契约

### 3.1 TaskSpec

规范见 `contracts/task.schema.json`。关键字段：

- `task_id`：任务标识；不能含路径控制字符。
- `dataset_ref`：本地 registry 中的逻辑 ID；真正根路径由用户本地登记，不发给模型。
- `goal`：枚举；`goal_confirmed` 与 `goal_evidence_refs` 记录谁确认、依据何在。
- `metadata_ref` / `context_refs`：只引用登记文件。
- `entity_key`：只允许已登记列名；`entity_key_confirmed` 是字段语义确认，不由模型自填 true。
- `protect_eval_split`：默认 true，禁止自动把 test 改小来获得漂亮结果。
- `limits`：总预算；模型不可改。
- `privacy`：网络与数据披露许可；模型不可改。

模型可以提出 TaskSpec patch，但根权限、预算、确认字段由用户/宿主确定。不能因为模型引用了一段可能不可信说明就把用户确认字段变为 true。

### 3.2 样本元数据

MVP 使用 UTF-8 CSV：`file_id,relative_path,image_split,entity_id,capture_session_id,provenance_ref`。其中只要求 file_id 与 relative_path；其余缺失必须显式记录。entity_id 不属于必填，缺失就不做完整实体泛化结论。

- image_split 与真实目录冲突时产生输入问题，不能由模型随意选一个。
- 同一 file_id 指向不同图、同一路径对应多个相互矛盾实体编号，必须拒绝相关结论。
- 未在数据集的行、未映射图片、空实体、未知 split、跨文件版本不一致均有覆盖报告。
- CSV 中 entity_id 是用户提供的来源声明，不等于经过第三方验证；结论标明依据。
- 没有实体元数据时，不从 class label、路径编号、EXIF 或相似图片擅自生成“真实实体 ID”。

`image_split` 指机器学习训练/验证/测试；评测平台使用 `benchmark_partition`，禁止混用。

### 3.3 文档上下文

只读登记 Markdown/TXT，设字节/片段上限，保存内容摘要和引用位置。文件内容始终是数据，包含“忽略规则、访问网络、删除文件”的句子都不能成为系统命令。远程模型可见内容必须符合显式授权的披露级别；默认无远程发送。

## 4. 工具与动作契约

AgentAction schema 见 `contracts/action.schema.json`。字段固定为 `action_type`、`reason`、`evidence_refs`、`parameters`。

`reason` 只需要可供用户核对的短决策依据，不要求模型输出隐藏思维过程。`evidence_refs` 必须存在于本 run 的证据 registry；空列表可用于初始读文档/澄清，但不能支撑风险结论。

| action_type | parameters | 验证点 |
|---|---|---|
| read_context | context_ref | 已登记、大小/权限允许 |
| run_audit | profile | profile 白名单、剩余预算、强制基础检查已执行 |
| check_groups | metadata_ref, entity_key | 目标和字段已确认；相关元数据完整性检查通过 |
| verify_evidence | audit_id | 来源于本 run，文件与身份可复核 |
| request_clarification | question_code, question | 非重复、问题上限、等待用户而非自答 |
| request_review | pair_refs | 数量不超过复核预算；引用存在 |
| finalize | reason_code | 验证器决定是否完成，不由模型覆盖状态 |

第一次模型动作非法：记录拒绝，可给一次结构纠正机会；纠正也消耗调用预算。继续非法/越权/重复空转：安全终止，保留证据并标 partial/failed，不伪造动作执行成功。

## 5. 状态机与恢复

```text
CREATED → VALIDATING_INPUT → BASE_AUDIT → PLANNING
                                          │
                         ┌────────────────┼───────────────┐
                         ↓                ↓               ↓
                      EXECUTING       WAITING_USER     FINALIZING
                         ↓                │               ↓
                      VERIFYING ← resume/确认      COMPLETED / PARTIAL
                         │
                         └────────→ PLANNING

任意执行阶段 → FAILED（不可恢复错误）
预算/步数耗尽 → FINALIZING → PARTIAL
```

- WAITING_USER 不是失败，也不是任务完成。写入待回答问题与 checkpoint，进程退出；不占着循环等待。
- 恢复前核对数据 manifest、TaskSpec、策略、Core 版本与证据。用户改变实验目标应建立 revision，旧结论保留并标 superseded。
- checkpoint 采用原子写入；工具启动前记录 pending action；崩溃后先检查既有唯一 run 产物，不无条件重复执行或重复计费。
- 输入文件在扫描期间变化要检测并报告；若必须得到强快照保证，用用户批准的独立只读拷贝/文件系统快照。仅前后 hash 不是对抗性原子快照。

目标 CLI（需实现）：

```sh
vli doctor --core-path .deps/visionleak-core
vli run --task examples/task.json --mode rules --out runs/demo-001
vli run --task examples/task.json --mode agent --out runs/agent-001
vli resume --run runs/agent-001 --answers answers.json
vli review-import --run runs/agent-001 --review review.json
vli report --run runs/agent-001 --format html
vli evaluate --suite <registered-suite> --conditions A,B,C,D,E
vli optimize --development <suite> --validation <suite> --max-candidates 3
```

`vli` 自身退出码与 Core 分开：0=最终报告已生成（可包含风险）；2=部分完成；3=等待用户；1=错误/配置失败。不要让用户把 0 理解成“无泄漏”。未授权 agent 模式必须清楚报错，不静默切 rules。

## 6. 证据、判断和报告：三个层次

### 6.1 三层不能互相替代

1. **图像关系**：字节相同、规范化像素相同、变换相似候选、局部相似候选。
2. **来源关系**：元数据声明同一实体/采集会话，或经人工确认的同源；可信度与确认者独立记录。
3. **实验风险**：上述关系是否违反已确认实验目标/划分约定。

相似不等于同源；同源不必然违反目标；字节相同也不能证明模型实际训练过该图。禁止用一个“泄漏分数”抹平三层差异。

### 6.2 EvidenceRecord

至少包含：evidence_id、kind、produced_by、core_audit_id（如有）、dataset_manifest_digest、files、source_positions、tool_version、params_digest、created_at、verification_state。

kind 示例：`core.byte_identical`、`core.pixel_identical`、`core.perceptual_candidate`、`core.local_candidate`、`metadata.entity_overlap`、`user.goal_confirmation`、`human.same_source_confirmation`。

- `pair_key` 根据无序 file_id 对确定，但每个工具见证都保留；不同 profile 的重复候选去重计数，不丢来源。
- 确定性证据可以建立 Core 定义的组；候选图的传递闭包不能被视为确定同源组。
- 人工确认改变 review 状态，不把 core.local_candidate 的证据类型篡改成 pixel_identical。
- Reviewer、时间、依据、原 auditId 与 data digest 可追溯；旧复核不能直接套到新内容上。

### 6.3 ClaimRecord

固定字段：claim_id、claim_type、statement、evidence_refs、goal_ref、coverage_ref、status、limitations。status ∈ confirmed / candidate / inconclusive / unsupported。

模型可写草稿，ClaimValidator 必须检查事实与引用，并对不支持的内容拒绝发布。风险结论优先确定性模板。最终数量、预算、版本、完整性只能从程序生成，不能从模型自然语言中提取再当事实。

“没有发现”允许表述为：在列明的 profile、输入、阈值和预算覆盖中，没有发现该类证据。禁止：“这个数据集安全”“完全没有泄漏”。

## 7. CoverageLedger 与总预算

### 7.1 覆盖不是一个 bool

分别记录文件清单覆盖、每个 profile 的完成状态、实体元数据覆盖、证据复验范围、人工复核覆盖。一个 profile 的 complete 不代表另一个 profile 完成。后续局部扫描不完整也不抹掉此前已完整的字节检查；报告必须拆开显示。

Core 的 complete 只保证其声明算法/范围内完成，不能直接转换成“审计目标全部覆盖”。

### 7.2 建议初始预算（工程默认值，不是性能保证）

| 项目 | 初始值 |
|---|---:|
| 最大规划步骤 | 8 |
| Core audit 调用数（含基础，verify 另入工具账） | 3 |
| 全部工具调用数 | 16 |
| 累计 comparisons | 1,000,000 |
| 每个输入数据集图片上限 | 1,000 |
| 每次 Core maxPairs | 2,000 |
| 最大用户澄清问题 | 2 |
| 本次可请求人工复核 pair 数 | 30 |
| 最大模型请求次数（含纠错/重试） | 8 |
| 累计工具执行时间 | 300 秒 |
| 远程模型预算 | 默认 0：未授权 |
| 单图源像素 / 感知采样像素 | 64,000,000 / 4,194,304 |
| 单文件编码字节 | 33,554,432 |
| 任务累计解码源像素（含重扫/复验） | 300,000,000 |
| 任务累计 indexOperations | 16,000,000 |
| 单次模型输出 token 上限 | 1,024 |
| 结案保留工具次数 / 秒数 | 2 / 10 |

基础、重试、Probe、验证、失败、报告生成均计入相应账本。comparisons 是 Core 工作单位，不是像素运算量，不可代替时间/内存/总成本。

每次工具启动前 reservation，结束后记实际消耗与退款。仅串行执行，避免并行竞争导致预算穿透。累计 comparisons 剩余额传给下次 Core；不得每轮重置为 100 万。

出现超时且没有可核验的实际 comparisons 时，将该次 reservation 记为保守消耗/unknown，不假设零。子进程进程组必须可终止并清理。用户等待时间与机器执行时间分开。

模型费用使用提供方 usage + 当次登记费率/账单来源，未提供则 unknown。不能用字符数当 token，不能把订阅额度换算成虚构美元。远程调用同时设调用数、输出 token 上限与可估计费用上限；无法保守估计且要求严格美元上限时拒绝发起。估算不等于真实账单上限保证。

## 8. 修正建议

首版仅导出 suggestion JSON/CSV 与候选 manifest，不执行修改。

- 不直接采用 Core export-fixes 的通用保留顺序作为科研修复政策；按照实验目标和 protect_eval_split 另做规则。
- 默认保护原 test；可建议在新实验版本中排除与固定 test 同源的训练样本，但需评估类别缺失/样本量并经人工批准。
- 对实体级分组，只有可信元数据或适当人工确认后才形成分组约束。
- `new_manifest` 只引用原文件，不移动原图；保存旧/新映射、原因、受影响 split 与证据。
- `plan-check` 验证新 manifest 的结构与已知冲突是否消失；不能仅过滤旧报告就宣称重新审计所有图像。
- 原模型已受污染时，修改数据清单不会抹掉训练影响；必须另行重训与独立评估。本项目不自动执行这一步，也不声称改善模型精度。

## 9. 安全与隐私测试边界

- 无任意 shell、Python exec、网络抓取、数据删除工具；所有路径宿主解析，模型只见逻辑 ID。
- 拒绝路径穿越、输出/数据目录嵌套、symlink 逃逸、未登记文件、HTML/CSV 注入。CSV 导出对以 =,+,-,@ 开头的不可信字符串做安全处理。
- 本地界面 GET-only、loopback、自动转义、资源白名单；人工记录从 CLI 导入，不先做公网写接口。
- SDK 的 TLS verify 必须 true；不复制官方示例中的关闭校验设置。
- 远程披露模式：`none` / `aggregates_only` / `approved_text`。MVP 不支持远程图片；数据摘要或摘要 hash 也可能敏感，需要登记披露字段。
- 文档/元数据中的指令与模型输出始终不可信。测试恶意备注要求读取密钥、跳过审计或删除 test；应拒绝且产生审计记录。
- OS 级内存/网络隔离与应用层限制分开声明；仅设置 CLI 像素预算不等于硬内存沙箱。

## 10. 每次 run 的目标产物

```text
run/
  manifest.json          # 输入/代码/策略/模型/版本，保密路径另存
  task.json
  events.jsonl           # 按序动作与结果摘要
  ledger.json            # 比较/时间/token/费用/复核预算
  coverage.json
  checkpoint.json
  tools/<call-id>/        # argv 脱敏、stdout、stderr、原始报告
  evidence.jsonl
  claims.json
  questions.json
  reviews.json
  proposal.json          # 可为空且注明原因
  report.json
  report.html
  validation.json        # 最终 claim/来源/范围校验
```

用户源文件、完整提示词中敏感内容、密钥不得进入公开 reports。公开复现用单独生成的合成或有授权数据。

## 0.6.0 可执行衔接补充

本节与 07_CORE_INTEGRATION.md 更新历史 0.5.0 依赖选择；原有权限与证据边界继续适用。

- 先读取 capabilities，校验锁定的版本、产物摘要、报告身份与 local profile；未知关键语义明确拒绝。
- verify 返回 0 不代表全部证据被复验。只复验 byte-identical/pixel-identical，候选在 skippedCandidates 中；valid=0 的成功结果不能显示“候选全部验证通过”。verification_state 分开记录 report_identity、exact_recomputed、human_review；人审不改变 core 证据类型。
- 输入仅支持 split 目录及 Core 声明的别名。CSV 补充实体/来源字段，不创建或覆盖 split；冲突需用户解决，平铺目录加 CSV 首版明确不支持。new_manifest 的 plan-check 仅做结构及已知冲突检查；重新审计需要另行构建合法数据视图。
- 使用 contracts/claim.schema.json 与 claim-rules.json。关键 statement 从已验证字段生成；模型文本只能作为有标签的解释，不以“引用存在”代替蕴含验证。不支持的断言保留为 unsupported，不进入肯定式报告。
- 每次 CLI 调用预算重新初始化；宿主总账覆盖多次 audit、verify、重试与模型纠错。完整 reservation/settlement、unknown 消耗与结案保留额度见 07。
- 只有完整 base 才能保留其完整覆盖结论；部分扫描中 images.length 是生成指纹数，stats.processedImages 才是已审计前缀。精确证据与近似搜索交织，不能宣称未处理后缀已完成精确检查。
- 只修改实验目标而输入/Core/profile 不变时，可引用经过身份检查的旧图像关系证据，生成新 revision 的风险解释；标明来源 run，不能谎称重新执行。输入或 profile 变更时旧复核不自动迁移。
