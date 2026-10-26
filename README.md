# VisionLeak Investigator

独立的 Python 3.12 本地图像数据审计应用，调用固定的真实 VisionLeak Core 0.6.0。已实现 M0、M1，并继续完成目标/元数据解释、澄清恢复、人工复核、只读建议和本地工程评测。当前默认运行确定性规则；**未完成真实模型 Agent 实验**，`--mode agent` 明确拒绝，不静默切换模式。

公开源码仓库：https://github.com/cjyhjy/visionleak-investigator 。Core 作为固定外部依赖单独获取，不随本仓库复制分发。

## 立即运行

完成下方「干净环境安装」后，在本项目根目录执行：

```sh
.venv/bin/vli doctor
.venv/bin/vli demo --out runs/my-fixture
.venv/bin/vli run --task runs/my-fixture/task.json --registry runs/my-fixture/registry.json --mode rules --out runs/my-audit
.venv/bin/vli report --run runs/my-audit --format html
```

输出目录必须全新且与图片目录互不包含。重复执行请使用新目录。`vli run` 默认先 base；明确请求旋转/镜像会追加 transform，裁切追加 local，两者均请求追加 all。也可用宿主 CLI 的 `--profiles base,all` 明确指定最多三次独立完整扫描。阈值固定 6；每次重扫和精确复验计入同一账本。

已有可读结果：`reports/demo-rules/report.html`，原始工具结果在同目录 `tools/`。`reports/engineering-suite/summary.md` 是 12 个合成任务 A/B/C 的工程结果，D 未运行。没有实测准确率优越性、自然泄漏发现或节省人工工时的结论。

## 干净环境安装

环境锁：Python **3.12.14**、Node **26.7.0**、sharp **0.35.5** / libvips **8.18.7**；当前原生运行锁来自 macOS arm64。`uv.lock` 锁定全部 Python 依赖，openJiuwen **0.1.19.post2** 为可选 `agent` extra。业务层与普通测试无需导入 SDK。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" UV_PYTHON_INSTALL_DIR="$PWD/.cache/python" uv sync --frozen
.venv/bin/python scripts/fetch_core.py --out .cache/visionleak-0.6.0.zip
.venv/bin/python scripts/bootstrap_core.py --archive .cache/visionleak-0.6.0.zip
.venv/bin/vli doctor
.venv/bin/python -m pytest -q
```

已有本地发布包时可省略 fetch，并给 bootstrap 传入该文件路径。fetch 是显式联网安装步骤，只接受锁定的公开发布地址和 SHA-256，不由审计触发。

发布包来源与 SHA-256 见 `core.lock.json`。bootstrap 只读取指定 ZIP，验证摘要，解压到本项目 `.deps`，按发布的 package-lock 安装 sharp，禁用 npm 安装脚本。不会操作原 Core 工作树，不使用 `npm install visionleak`，不运行时更新依赖。已有 `.deps/visionleak-core` 时拒绝覆盖。首次下载依赖需要联网；审计不需要联网。跨平台首次安装请为 bootstrap 增加 `--migrate-runtime --receipt reports/my-platform-migration.json`；该显式操作保存旧/新锁和平台信息，仅允许原生依赖差异，仍强制固定 Core 源码、编译产物及 Node 版本。安装已完成但锁不同，可执行 `.venv/bin/python scripts/pin_core.py --migrate-runtime --receipt reports/my-platform-migration.json`，随后必须跑 doctor 和全套测试。不要用迁移绕过版本升级审核；不同运行锁的评测仍禁止合并。

可选 SDK 环境：`UV_CACHE_DIR="$PWD/.cache/uv" uv sync --frozen --extra agent`。无模型 SDK smoke 的原始日志与收据已经保存于 `reports/sdk-smoke/`；该脚本要求其输出目录全新，不覆盖既有验收结果。

## 输入与人工确认

TaskSpec 使用 `contracts/task.schema.json`；本地 registry 包含 `datasets`（逻辑 ID→绝对目录）、`documents`（逻辑 ID→path/sha256）、`confirmations`（用户确认目标/实体列的 actor、kind、值）。生成器提供最小示例。真实图像必须在 train/validation/test 或 Core 声明的别名目录内。CSV 仅补充实体/来源，不重定义 split；平铺目录、冲突和 symlink 会被拒绝。

未知目标进入 `WAITING_USER`。由用户提供 answers JSON，例如：

```json
{"actor":"dataset owner","goal":"new_entity_generalization","entity_key":"entity_id"}
```

```sh
.venv/bin/vli resume --run runs/my-audit --answers answers.json
.venv/bin/vli review-import --run runs/my-audit --review review.json
.venv/bin/vli recover --run runs/interrupted-audit
```

`entity_key` 只在已有登记 CSV 时填写。确认不会由文档或模型自行填写。每次更新产生不可覆盖 revision；只改目标可复用已验证图像证据，明确标识未重跑 Core。不同 revision 累计沿用账本，重复相同输入不会重复审计或计费。原记录保留，`latest-revision.json` 指向最新解释。崩溃恢复保守结算 pending，保留原始产物，形成 PARTIAL，不盲目重跑或把未接受报告升级为事实。

review JSON 必须含 `reviewer`、带时区的 `created_at`、`dataset_manifest_digest`、`audit_id`、`pair_ref`、`decision`（confirmed/rejected/unsure）、`reason`。这些 ID 可在 `reviews.json` 和 `coverage.json` 找到。人工同源确认另存证据，不将 candidate 改成 pixel-identical。未请求/未完成的复核队列始终可见。

## 证据与预算

每个 run 保存 task、manifest、输入 hash、原始 argv/stdout/stderr/report、事件、不可覆盖的证据 JSONL、claims、coverage、ledger、questions/reviews、proposal、校验结果和 HTML。报告身份由真实 Core 验证器计算，未重新实现其 auditId 算法。报告引用存在不等于支持断言；关键结论由固定模板和证据前提生成。

预算包括 audit 次数、工具次数、comparisons、indexOperations、源像素、工具时间、澄清/人审次数。先 reservation，再实际结算；未知失败按预留保守扣除。预留结案工具与时间；verify 没有像素开关，宿主预先核算精确端点解码量。候选不被 verify 重算，`valid=0/skippedCandidates>0` 不是候选确认。指纹数与 processedImages 分列，不完整后缀不写成已完成精确检查。

退出码：0=报告完成（可包含风险）；2=部分完成；3=等待用户；1=输入/配置/执行错误。Core 的退出码单独保留。

## 测试、评测和阶段记录

```sh
python3 scripts/record.py regression .venv/bin/python -m pytest -q
.venv/bin/vli evaluate --suite synthetic-engineering --tasks 12 --out runs/evaluation-001
```

命令、退出码和日志索引为 `reports/commands.jsonl`；阶段状态在 `STATUS.json`、`WORKLOG.md`、`reports/milestones/M*.md`。测试使用真实 Core，只有规划器结构纠错单元测试使用明确标为 `scripted_test_only` 的输入。A/B 为独立固定驱动，B 只扫一次 all；生产规则与未来 Agent 门禁仍强制 base。真值位于 evaluator 专属目录，未登记为工具输入。失败、PARTIAL 和 D blocked 都保留。

## 限制与后续

- M3 已接通共用真实审计操作、脱敏观察、七类白名单动作循环、模型预算预留/结算、结构纠错、停止与保守恢复；这些仅经过明确标注的脚本测试及无模型 SDK 验收。尚无配置并授权的真实模型 provider adapter 或两条真实模型轨迹；D=blocked，M4/E=not_run。
- 全部评测输入为受控合成工程数据；未建立独立自然图像 test，不宣传泛化或算法收益。
- 前后 hash 不是原子快照；应用门禁不是对恶意本地管理员的沙箱或数字签名。资源限制主要由 Core 和进程组超时执行，无 OS 硬内存上限。
- CPU/完整进程树 RSS 未测，报告写 not_measured，不用 Python 母进程数据冒充。
- proposal 是新实验版本的建议，保留 test，未移动或删除图片；结构检查不替代重新审计、训练或独立评价。
- 无模型调用、向模型上传图片、软件包发布或赛事提交。负责人已授权将代码、开发文档、合成测试素材与实际工程日志发布至独立公开仓库；仓库内历史证据保留当时的本地路径，复现请重新生成 registry。

开发设计的原始快照保存在 `docs/planning/`；实现偏差与边界见 `docs/adr/`。第三方许可与来源见 `THIRD_PARTY_NOTICES.md`。

## 持续集成

`.github/workflows/ci.yml` 在 Ubuntu 24.04 与 macOS 14 的全新 checkout 中安装冻结依赖，下载并验证 Core，显式记录平台锁，运行完整测试和新生成合成图的 base+all 审计。Linux 测试与审计在禁用网络的 namespace 中执行；macOS 不宣称 OS 网络隔离。没有模型凭据或 agent extra。失败时也上传命令、日志、JUnit、平台锁和真实审计证据，保留 14 天。远端完成前仅表示工作流已配置，不表示跨平台通过。

控制器测试（不是 Agent 演示）：`.venv/bin/python scripts/controller_smoke.py --sdk --out runs/new-controller-sdk`。需已安装 agent extra；省略 `--sdk` 可在基础环境验证同一宿主循环。结果醒目标注 `SCRIPTED_TEST_ONLY`；受控回调输入不是模型决策，D 条件仍 blocked。已运行证据见 `reports/controller-sdk/receipt.json`，实现边界见 `docs/adr/004-planner-host.md`。
