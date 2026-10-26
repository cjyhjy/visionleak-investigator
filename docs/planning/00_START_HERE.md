# VisionLeak Investigator｜Codex 开工包

版本：设计基线 1.0 · 2026-10-26  
性质：开发规格与验收任务，不是已经实现的 Agent，不包含已运行的性能结论。

## 给用户

将整个文件夹交给 Codex，并发送下面的开工指令。可以将文件夹放在一个新的空项目目录中；不要直接解压到现有 VisionLeak Core 仓库里覆盖文件。

## 可直接发送的开工指令

```text
请按照本文件夹的设计与验收要求，开始实现 VisionLeak Investigator，不要停留在再次讨论选题或只生成计划。

先读 AGENTS.md、01_PRODUCT_AND_ARCHITECTURE.md、02_CONTRACTS_AND_SAFETY.md、03_EVALUATION.md、04_IMPLEMENTATION_PLAN.md；05_COMPETITION.md 与 06_SOURCES_AND_DECISIONS.md 是申报与来源边界。contracts/ 和 examples/ 是契约与示例输入，不是已实现代码或实验结果。

在当前授权工作区内创建独立的 visionleak-investigator 项目，或使用用户已指定的同名空仓库。先检查现有文件、Git 状态和上层 AGENTS.md，不覆盖未提交修改，不改写历史。不要修改原有 cjyhjy/moonbit-visionleak 的工作树、发布版本或许可证。

原规划的历史核查基线为 Core 0.5.0，保留在 SOURCE_BASELINE.json。当前开发依赖改为正式 Core 0.6.0，以 core.lock.json 中的实际发布提交与摘要为准；不要继续使用历史 recommended_dependency_commit。通过固定提交的独立依赖副本接入真实 CLI。不要执行 npm install visionleak：核对时该仓库的 npm package.json 为 private:true。先验证真实接口、报告字段、退出码与本地依赖，再实现。

按 M0→M1→M2→M3→M5 的首版交付子集推进；首版完成 A—D 对照，M4 与 E 留到第二阶段。每阶段先写对应测试，再实现，验收后保存报告。无账号、无模型或无网络时，完成所有可独立完成的本地工作，明确标记受阻项；不要伪造 Agent 调用、真实数据、评测收益、截图或成功日志。

系统是“单一规划 Agent + 确定性审计/证据校验 + 人工确认”。采用 Python 3.12，Node 版本满足 Core 要求并锁定；优先使用 openJiuwen Agent Core 的运行/工作流能力，不安装 JiuwenSwarm 整套通用产品。框架调用必须通过本项目统一工具门禁。借鉴 Harness² 的策略试验思想，第一版不直接依赖 Harness²、不递归修改自身源码。

默认离线，不调用付费模型、不上传图片或项目资料、不公开推送、不发布包、不正式报名。只有用户明确配置并授权了模型服务与预算，才允许实际模型调用。凭据存在不等于允许使用。缺少授权时继续完成离线集成、规则基线、测试、界面与申报草稿。

不要在普通技术选择处反复问“是否继续”。采取规格中的默认值，记录 ADR；只有付费、对外发送、公开发布、修改真实数据、权限升级等事项等待批准。一次会话做不完时，留下可恢复的 WORKLOG.md、STATUS.json 和下一条可执行命令。

首个交付检查点是 M0+M1：真实 Core 接通、不可变证据记录、明确完整性、零模型可运行的本地闭环，以及 tests/acceptance 中的基础验收。不允许用 mock 检测器替代最终集成。
```

## 文件阅读顺序

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 给编码 Agent 的执行约束和完成定义 |
| `01_PRODUCT_AND_ARCHITECTURE.md` | 产品定位、最小范围、架构、Agent/Harness 分工 |
| `02_CONTRACTS_AND_SAFETY.md` | 状态机、真实 Core 适配、证据、预算、安全、输入输出 |
| `03_EVALUATION.md` | 公平基线、数据分割、指标、否证与停止条件 |
| `04_IMPLEMENTATION_PLAN.md` | M0—M5 任务、验收条件、测试矩阵、交付文件 |
| `05_COMPETITION.md` | 创意申报草稿、三分钟演示、版权与公开动作闸门 |
| `06_SOURCES_AND_DECISIONS.md` | 核查来源、已决策/待核实事项、版本锁定依据 |
| `contracts/` | TaskSpec 与 AgentAction 的 JSON Schema |
| `examples/` | 合法示例、默认配置、策略配置；不是实测输出 |
| `SOURCE_BASELINE.json` | 本次核对的 Core 提交与文件 blob SHA |

所有 `vli ...` 命令都是要求 Codex 实现的目标接口，不是本规划包已经提供的可执行命令。

## 不变的项目主线

**面向图像机器学习实验，结合实验目标、数据来源信息和图像证据，自主选择审计步骤；信息不足时追问，证据不足时保留，不把相似图片直接判成泄漏。**

Core 负责“算出什么”；Investigator 负责“为了这个实验目标，还需要查什么、为什么、查到什么程度可以停止”。最终事实结论必须由证据与确定性规则支持，不能由语言模型投票决定。

## 0.6.0 衔接修订

先读 [07_CORE_INTEGRATION.md](07_CORE_INTEGRATION.md) 和 [08_REVISION_NOTES.md](08_REVISION_NOTES.md)。core.lock.json 是运行依赖锁，SOURCE_BASELINE.json 仅是历史源阅读记录。Core 0.6.0 不提供裁切 v2、缓存、子集审计或端到端流式解码，不得把版本号当成这些功能的证明。
