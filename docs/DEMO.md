# 三分钟本地演示脚本

这是受控演示方案，不是已录制视频，也不冒充真实 Agent。

0:00—0:30：运行 `vli doctor`，展示固定 Core 0.6.0、Node、sharp 和编译摘要。说明 Core 提供图像证据，Investigator 新增预算、目标、复核和追溯。

0:30—1:10：展示 `reports/demo-rules/report.html` 与同目录工具日志：真实 byte/pixel 证据及 all-profile 候选，指出候选未被自动确认为同源。

1:10—1:50：展示 `reports/interaction-demo/run/report.html` 的 WAITING_USER，打开 answers.json，明确说明此为脚本化用户答案 fixture。打开 receipt.json 指向的 revision：新实体目标出现元数据风险；audit_runs 仍是1，图像证据复用。2/6元数据覆盖使状态保持PARTIAL。

1:50—2:25：展示 ledger reservation/settlement、Core partial 的6个指纹/1个已处理图，以及 invalid verify code4。打开 proposal.json，指出 test 保留、仍可能存在已知冲突，修改未经执行。

2:25—3:00：展示12任务的 A/B/C 工程结果和 D blocked；明确没有真实模型调用、独立自然图像测试、统计收益或真人时间节省结论。说明下一步需授权真实模型契约，再实施和记录 D。

已有成果：MoonBit Core 检测/索引/报告身份。新增成果：Python 编排、账本、证据约束、目标/元数据解释、恢复、复核、只读建议与公平工程驱动。Harness策略优化和E为后续。
