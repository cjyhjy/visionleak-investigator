# CLI 与本地文件接口

当前接口为 Python 3.12 CLI `vli`，入口是 `src/visionleak_investigator/cli.py`。没有 HTTP 写接口、通用 shell 工具或已启用的模型提供商。下列命令对应当前实现；设计快照中的其他拟议命令不代表已实现。

## 命令

| 命令 | 必需参数 | 行为和退出码 |
|---|---|---|
| `doctor` | 无；可选 `--core-path`、`--out` | 检查锁定产物、Node、capabilities；0 通过，1 拒绝 |
| `demo` | `--out` | 生成新的受控合成图、任务和 registry；不调用模型 |
| `run` | `--task --registry --out` | 默认 `--mode rules`；可选 `--profiles base,all`；0 完成、2 部分、3 等待用户、1 拒绝/失败 |
| `report` | `--run` | 验证已保存报告，再输出 `--format html/json` 的路径；不重新渲染或重跑审计 |
| `resume` | `--run --answers` | 导入用户目标/字段确认，生成 revision；不恢复 Core 扫描 |
| `review-import` | `--run --review` | 导入绑定当前图像对的人审记录，生成 revision；不升级 Core 证据种类 |
| `recover` | `--run` | 原工作进程停止后保守结案；有完整报告则校验并返回；恢复通常退出 2 |
| `evaluate` | `--out`；可选 `--tasks` | 原有 `synthetic-engineering` 工程集；A/B/C 实际运行，D 受阻 |
| `eval-validate` | `--catalog --root` | 来源、内容、分区和真值隔离检查；可选 `--out` |
| `eval-freeze` | `--catalog --root --protocol --out` | 不可覆盖的输入/实现/依赖/策略/模型声明冻结 |
| `eval-check` | `--catalog --root --protocol --frozen --partition` | 验证冻结；可选 `--out`；不是实验结果 |
| `eval-run` | 上行参数及 `--out` | 执行冻结 A/B/C 和独立评分；可选 `--replay-of`；0 调度结束、2 含执行/评分失败、1 拒绝 |

`--mode agent` 始终拒绝，直到模型提供商、授权和实际适配器完成。环境变量中有 key 不会自动开启模型。`eval-run` 的 0 可以包含 PARTIAL 和 blocked D，不能解释为完整科研评测通过。详细指标与文件布局见 [EVALUATION.md](EVALUATION.md)。

运行输出必须是新目录，不能与图片目录互相包含。源目录、登记文档和输出路径的 symlink 被拒绝。公开历史记录中的绝对路径只描述当时运行；跨机器复现应生成新的任务和 registry，不修改旧回执冒充新运行。

## TaskSpec 与 registry

TaskSpec 的权威 schema 是 `contracts/task.schema.json`。目标包括 `content_audit`、`new_entity_generalization`、`same_entity_new_view` 和 `unspecified`。模型不能修改确认、预算或隐私字段。目录中的 image_split 与评测 catalog 的 benchmark_partition 是两个维度。

Registry 是宿主文件，包含：

- `datasets`：逻辑数据 ID 到绝对本地目录。图片在 train/validation/test 或已声明别名目录中。
- `documents`：逻辑文档 ID 到 `path`、`sha256`；只支持登记的 UTF-8 Markdown/TXT/CSV，大小不超过 1 MiB。
- `confirmations`：确认 ID 到 actor、kind 和目标/字段值。确认不是文档中的一条指令。

元数据 CSV 必须有 `file_id,relative_path`，可附 `image_split,entity_id,capture_session_id,provenance_ref`。目录决定 split；CSV 只补充声明，不覆盖目录。字段冲突、缺行、缺实体或未确认语义都保留为覆盖问题。

## 回答、复核和修订

Answers JSON 只允许非空 `actor` 以及 `goal`、`entity_key` 中至少一项。字段确认要求已经登记相应 CSV。

```json
{"actor":"dataset owner","goal":"new_entity_generalization","entity_key":"entity_id"}
```

Review JSON 必须恰好包含 `reviewer,created_at,dataset_manifest_digest,audit_id,pair_ref,decision,reason`。时间带时区，decision 是 confirmed/rejected/unsure；图像对和摘要取自当前 run 的 reviews/coverage。示例中的身份必须替换为实际用户身份；受控演示中的脚本身份不是真人参与证据。

Revision 保存于 `revisions/<payload-digest>/`，`latest-revision.json` 指向最新解释。相同 payload 返回原有结果，不重新收费或重扫。不同 payload 从最新 revision 沿用累计账本。Core/runtime 或输入变化会拒绝复用。

新 revision 的 `manifest.code_digest` 记录当前处理程序；`image_evidence_origin` 记录最初图像证据的 Investigator 代码摘要、manifest、Core 和运行锁。`parent_manifest_digest`、`parent_report_digest` 绑定父记录。报告中的 `revision` 同时说明处理代码、证据代码、复用条数以及 `core_reexecuted=false`。旧报告保留原来的字段和含义，不追写历史版本。

## 恢复与完整性

`recover` 不是停止进程的命令，调用前必须确认原工作进程已停止。它使用与修订共用的文件锁，串行结算 pending reservation；并发重复恢复不会重复收费。没有结案预算时拒绝并保留原始材料。

保守恢复不接纳中断前的图像证据。旧 evidence、proposal、coverage、claims 等移到唯一的 `pre-recovery/<id>/` 目录，原 tools 仍保留；当前 evidence/claims 为空，proposal 明确不可用。后续目标修订不能重新采用这些未接纳记录。需要新的图像检查时启动新 run。

`recovery-receipt.json` 记录原始 manifest/代码、恢复处理代码、归档路径和 SHA-256；checkpoint 与报告绑定该收据。`verify_run` 还检查 manifest、report、ledger、evidence、模型账本（如有）、Core 报告及声明支持关系。它发现意外内容变化，不是数字签名或防本地管理员的安全边界。

## 建议文件和当前接口缺口

`proposal.json` 是只读建议，内含 `new_manifest` 和 `plan_check`。当前生成器校验结构、保留 test，并列出已知确定性/实体冲突是否仍在；它不移动、删除或重划分原数据，也不声称替用户重训。

当前还没有接收用户自改 manifest 的独立 `plan-check` CLI；已有的是生成建议时的内部检查。这一接口差距保留在交付核对中，不能把设计中的名字当作现成命令。没有 CSV 导出命令；CSV 输入以普通字符串处理，不执行表格公式。

## 进程内接口

`workflow.run_task/run_baseline`、`interaction.resume_run/import_review`、`recovery.recover_interrupted` 和 `integrity.verify_run` 是当前宿主入口；它们仍执行相同验证与预算逻辑。`evaluation_worker`、`evaluation_scoring` 仅供宿主评测启动，不是注册给 Planner 的工具。Python 模块接口目前不承诺独立稳定的第三方 SDK 兼容性。
