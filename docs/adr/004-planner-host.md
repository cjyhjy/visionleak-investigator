# ADR-004 — 共用审计操作、受限 Planner 循环与测试来源

2026-10-26，accepted。

原规则实现按固定 profile 列表循环。现在 audit_profile/verify_report 是同一宿主函数；规则与受限 Planner 使用同一 CoreAdapter、输入身份检查、BudgetLedger 和 ClaimValidator。Planner 只选白名单动作，不能更改阈值、预算、路径、工具实现或结论。host 先执行强制 base，再暴露脱敏观察。

controller.AccountedRequest 先持久化模型预算预留，再调用宿主配置的 callback。每次结构纠错独立计数；传输/usage 失败不当作 JSON 纠错重试。usage 缺失、崩溃、超额和异常保守结算。回调拿到 JSON 深拷贝而非宿主状态引用。观察最多 128 条证据并标明截断；不包含私有路径、实体值、自由请求文本或原始文档，文档/实体列通过别名登记。批准文本披露尚未实现。

所有七类白名单动作均接入宿主。已完成的 profile/verify 拒绝重做；不重新收费。人审请求先占用配额，随后同一 pending review 的第一次 import 不再重复计数。澄清 backlog 与实际请求分列；缺少目标而未追问不能称主动澄清或完整完成。模型不能生成最终事实，停止/异常仍由确定性宿主结案。

当前仅暴露 Python run_scripted_task 测试入口，强制 local-only TaskSpec；不增加假 Agent CLI 模式。`--mode agent` 仍拒绝，没有 provider、凭据发现或网络客户端。标签 scripted_test_only 不是授权。真实 provider、授权契约、费用估算与 token 上限在提供商侧的落实仍待明确服务后实施和实测。

复现：`.venv/bin/python scripts/controller_smoke.py --sdk --out runs/new-controller-sdk`。SDK 0.1.19.post2 真正经过 ToolGate 调用真实 Core，Python socket.connect 被阻止；这只是本地控制器/框架验收，不是两条真实 Agent 轨迹。测试报告、trace、账本和 HTML 都显式标 SCRIPTED_TEST_ONLY，模型调用仍为 0。

恢复结算 pending 模型请求并保留脚本来源，不自动重放。answers/review revision 复制原账本/trace，并明确 host_revision_only_no_new_planning；不会在回答后自动启用模型或重置预算。验证器核对模型账本摘要。源图变化时停止后续工具、清空可发布 claims 和修正建议。
