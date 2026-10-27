# 三分钟本地演示脚本

这是可复现的受控演示脚本，不是已录制视频，也不是已验证的真实 Agent 演示。全部图片自行生成；回答和复核输入是脚本 fixture，没有真人工时测量。

准备命令（输出目录必须全新）：

```sh
.venv/bin/vli doctor
.venv/bin/python scripts/report_smoke.py --out runs/demo-new
.venv/bin/python scripts/controller_smoke.py --out runs/controller-new
```

每份 `receipt.json` 给出真实运行、报告路径和模式；生成过程调用真实 Core，不使用结果回放。保存的新版示例在 `reports/report-demo-final` 与 `reports/report-controller-final`。

0:00—0:25：展示 doctor 中固定的 Core 0.6.0 与产物摘要。说明 Core 提供检测证据，Investigator 新增目标/复核流程、总预算、证据约束和可追溯报告。

0:25—1:05：打开 complete/run/report.html。展示“检查完成不代表没有风险”、已确认结论条目与不同候选图片对。点击待复核编号，展示图片对和复验状态，再打开原始 Core JSON。明确相似候选没有自动成为同源结论。

1:05—1:40：打开 clarification/run/report.html，展示 WAITING_USER 和必要问题。说明 answers.json 是脚本回答，随后打开 receipt 指向的 goal_revision 页面：目标已确认，报告注明复用证据、未重跑 Core，累计扫描调用不增加。

1:40—2:15：打开 partial/run/report.html，展示 ComparisonBudget、6 张已生成指纹与 1 张已处理图像、已扣账 1/1 比较额度。展开预算账本，说明 unknown 的保守结算规则；不完整不能被讲成“未发现泄漏”。

2:15—2:40：打开 controller-new/clarification/run/report.html。醒目展示 SCRIPTED_TEST_ONLY；该流程验证宿主控制器和真实工具调用，不是真实模型 Agent。再展示 review_revision 中 unsure 复核结果，说明测试复核不提供真实人工确认。

2:40—3:00：展示已有 12 个合成任务的 A/B/C 工程结果和 D blocked。本地评测执行器已完成，保存了 36 次真实 Core 运行及完整分母；独立自然图像测试、真实模型对照、统计收益和真人时间节省均未验证。下一步按明确模型/外发/预算契约接入真实 provider，再运行 D 和获准的独立自然数据实验。

已有成果：MoonBit Core 指纹、检索、报告身份与 verify。新增成果：Python 编排、证据/预算账本、目标与元数据解释、恢复、复核、只读建议、来源隔离与工程评测。M4/E 策略优化后置。演示脚本不构成报名、赛事提交或参赛资格确认。
