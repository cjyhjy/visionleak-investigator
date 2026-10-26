# 06｜来源、设计决策与核查边界

核查日期：2026-10-26。

本包建立在对用户 GitHub 连接中的 Core 文件读取，以及公开一手文档查阅上。本次没有在本地运行 Core、安装 openJiuwen、调用模型或进行性能评测。文中的“必须/应”是给实现者的要求，不能当成已经完成的事实。

## 一手来源索引

| ID | 来源与位置 | 支持的事实 / 边界 |
|---|---|---|
| S1 | [Core README，固定提交](https://github.com/cjyhjy/moonbit-visionleak/blob/7541888125f86077ab49ce0bdef6f3301f1e9e99/README.md) | 已有功能、当前局限、既有照片分组；README 声明不替代本次复跑 |
| S2 | [Core package.json，固定提交](https://github.com/cjyhjy/moonbit-visionleak/blob/7541888125f86077ab49ce0bdef6f3301f1e9e99/package.json) | 版本 0.5.0、Node >=22、private:true、MIT 字段、sharp 依赖 |
| S3 | [Core CLI 文档，固定提交](https://github.com/cjyhjy/moonbit-visionleak/blob/7541888125f86077ab49ce0bdef6f3301f1e9e99/docs/cli.md) | CLI、预算、scope、退出码、verify/导出等；存在历史阶段说明，应以固定版本实测补验 |
| S4 | [0.5.0 发布记录，固定提交](https://github.com/cjyhjy/moonbit-visionleak/blob/7541888125f86077ab49ce0bdef6f3301f1e9e99/reports/plan-0.5.0/publication-0.5.0/README.md) | 仓库记录 Mooncakes/Release/CI 状态；本次没有独立重新下载发布包或重跑 CI |
| S5 | [本次核对的提交](https://github.com/cjyhjy/moonbit-visionleak/commit/7541888125f86077ab49ce0bdef6f3301f1e9e99) | 设计绑定的 source snapshot，不自动追踪 main |
| S6 | [openJiuwen Agent Core README](https://github.com/openJiuwen-ai/agent-core/blob/main/README.md) | Python SDK、工作流/工具/模型能力与系统要求；具体可用版本由 M0 安装核查 |
| S7 | [Google Harness² README](https://github.com/google-research/harness2/blob/main/README.md) | 策略改进方法、执行器/运行边界、许可声明；不作为本项目实测收益证据 |
| S8 | [Harness² 实验指南](https://github.com/google-research/harness2/blob/main/docs/EXPERIMENTS.md) | 对照、复现、数据与网络隔离的参考 |
| S9 | [openJiuwen 赛事公告](https://bbs.huaweicloud.com/blogs/491289) | 日程、作品/材料要求、推荐技术和参赛条款；正式问卷/协议与书面回复仍需负责人确认 |

文档中提出的架构、状态、schema、预算和验收阈值属于本项目设计，不是从上述来源复制的现成接口。

## 已决策（Codex 默认执行）

| 决策 | 结论 |
|---|---|
| 项目主线 | VisionLeak Investigator，不切回 MoldPlan/记忆诊断/通用 Harness |
| 与 Core 的关系 | 独立应用，固定 Core 依赖，不改原项目 |
| 语言与硬件 | Python 3.12 + Node；先 CPU、本地；不要求 GPU 或 Linux 虚拟机 |
| Agent 形态 | 单 Planner + 确定性执行/验证，不做蜂群 |
| 框架 | 优先 openJiuwen Agent Core；不是 JiuwenSwarm 产品套壳 |
| Harness² | 借鉴领域化有界策略试验，首版不移植执行器 |
| 安全 | 数据只读、工具白名单、预算总账、默认离线 |
| 真值 | evaluator 独立，生产审计不假装有真值 |
| 展示 | CLI 先行、静态证据工作台，不先造大型前端 |
| 公平对照 | 首版 A—D，重点 C vs D；第二阶段 E，比较 D vs E |
| 成果表达 | 既有工具与新增决策层分开；性能提升是待验证假设 |

## 待核实，但不应阻塞全部开发

- 用户当前授权的本地项目路径：Codex 在其工作区检查，不从本包推测 Mac 绝对路径。
- openJiuwen 精确包版本与 API：M0 选择并锁定，兼容测试留证据。
- 原始 Core CLI 文档中的旧阶段段落：以固定代码和实际 smoke 核实，保留偏差记录。
- 模型服务、模型 ID、数据披露和调用预算：用户授权前不调用；先完成离线工作。
- 新测试图来源、许可与样本量：生成最小合成测试先行；真实/公开数据需来源记录。
- 跨赛事复用、知识产权与外部数据赛事审批：阻止正式报名/对外公开，不阻止本地验证。

## 已明确不采用的说法

- 不把“裁切/镜像 0/18”旧报告当当前 0.5.0 全部能力。
- 不说“Core 已发布到 npm”，因为核对时 package 为 private。
- 不说“Google 论文证明我们的数据审计也能提升 X%”。
- 不把策略试跑中更多候选称为真实召回率提高。
- 不把不同仓库当知识产权自动隔离。
- 不把开发过的留出集再次称为全新 holdout。
- 不把 Core complete=true 转成“所有泄漏已被发现”。

## 版本与许可操作

本次只提供计划文件，不授予 Codex 修改已有许可证、对外发布或代表作者接受比赛协议的权限。Core 按其固定版本许可使用，保留声明；若以后复制 Google/openJiuwen 代码，逐文件核查相应许可、NOTICE 与来源，不能只在 README 提到项目名就忽略义务。

本包中的源链接用于追溯；开发前读取最新文档只用于判断版本差异。除显式升级决策外，不能在运行时自动使用 main 变化的代码。

## 0.6.0 衔接决策

历史链接与 SOURCE_BASELINE.json 保留原样；当前执行依赖以 core.lock.json 和 core-capabilities.json 为准。新增 capabilities、verificationScope 是此次实际 Core 实现，精确提交与发布摘要已记录在 core.lock.json，公开 CI 与附件下载、注册表干净导入均已核验。裁切 v2 未发布，仍使用 vl-local-dhash-v1。首版不等待新的检测研究；后续显式升级并重跑 T29—T35。
