# 验收索引

执行状态以 reports/commands.jsonl 和原始日志为准；下面仅映射范围。

| 用例 | 对应实测 |
|---|---|
| T01/T02 | test_core_contract + test_loop：真实byte/pixel，证据引用与源不变 |
| T03/T04/T29 | 真实旋转/局部/平色候选；local-only verify valid=0、skippedCandidates>0 |
| T05/T07/T30 | max-comparisons=1：6指纹/1processed；audit 2/3、verify 4 |
| T06 | 坏PNG、未知扩展已测；超大真实图像的专门容量实验 not_run |
| T08—T12 | test_interaction：两目标、缺失/冲突、WAITING_USER、恢复和输入变化 |
| T13—T16 | schema、伪引用、未知工具、注入文档、重复profile拒绝 |
| T17 | 真实sleep子进程超时，unknown保守扣除，pending注入恢复；非自然崩溃统计实验 |
| T18/T19 | 目录逃逸/symlink和HTML转义；当前不导出CSV，不声称CSV导出专项通过 |
| T20/T24 | agent模式在存在key环境变量仍拒绝；scripted_test_only仅结构单测；无真实Agent调用 |
| T21/T33 | 复核 audit/input绑定、候选不升级；模板与证据蕴含拒绝 |
| T22 | not_run，优化器/E在第二阶段 |
| T23 | 未登记truth被拒绝，评测truth在dataset/registry之外；应用级隔离 |
| T25 | 建议manifest保护test，保留剩余已知冲突；源文件不修改 |
| T26/T31 | reservation、unknown、预留结案；三次audit+verify共享像素/比较/索引账本 |
| T27/T28/T35 | evaluator拒绝不同锁/总预算；全量分母和N/A；revision预算累积且不重复audit |
| T34 | artifact mismatch、报告篡改、未知schema拒绝；有合法新auditId的无害新增字段接受 |

41项测试含参数化用例，不能等同于41个独立自然任务。SDK无模型工作流另有一次真实smoke。A/B/C另外运行12个合成任务；真实模型D/E和独立自然图像test未运行。
