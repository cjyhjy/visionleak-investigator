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
