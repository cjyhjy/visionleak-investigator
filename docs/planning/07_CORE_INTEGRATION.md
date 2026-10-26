# 07｜Core 0.6.0 集成契约

本文件是 0.6.0 修订的接口约定。SOURCE_BASELINE.json 只记录原规划阅读 0.5.0 时的事实；当前依赖以 core.lock.json 为准。core-capabilities.json 是实际 CLI 输出的快照，不是 Investigator 已实现的证明。

## 获取与锁定

将发布提交检出到独立 .deps/visionleak-core；也可使用同版本已验收源码 ZIP，并验证下载 SHA-256。不要直接使用正在开发的原 Core 工作树，不跟随 main，不执行 npm install visionleak（npm private）。npm ci 安装锁定的宿主依赖，Node 满足 Core engines。

M0 执行 `node <core>/tools/cli.mjs capabilities`，校验 version、artifactSha256、capabilities/report/identity schema、normalization、local profile。锁文件保存源提交、源码归档摘要、Mooncakes 核心包摘要（仅在实际发布并验证后填写）、编译 JS 摘要和能力快照摘要。源码 ZIP 是 Investigator CLI 集成的交付物；Mooncakes ZIP 仅含 MoonBit 库，不能拿它代替宿主 CLI。

capabilities 能证明已安装程序声明的接口，不能代替真实 smoke、可信下载或审计报告复验。schema 已知时容忍无害新增字段；未知 schema、证据等级、profile 必须报不兼容。

## 已支持与明确未支持

已支持：固定目录全量 audit、四个适配器 profile（base/transform/local/all）、verify 精确证据复验、export-html、export-fixes、capabilities。

未支持：CSV 驱动的 split、manifest 直接输入、pair 子集审计、断点/增量扫描、跨运行指纹缓存、裁切 v2、端到端分块解码、语义泄漏识别。0.6.0 的 MIH 是检索优化，不提升 dHash 的语义判别能力。严格裁切 v2 的旧数据探索召回退化，未进入产品。

第一版输入须使用 train/validation/test 及 capabilities 所列别名。CSV 用 relative_path 映射已登记文件、补充实体/来源，不覆盖目录 split。目录/CSV 冲突是输入错误；缺少字段是覆盖不足。平铺图像目录不能“成功空扫”。

## 退出码与验证状态

普通 audit：0 完整（可含重复），2 不完整但可能有有效证据，1 致命错误。传 fail-on 后 3 是关卡命中，仍须检查 complete；Investigator 常规流程不传 fail-on。

verify：4 为精确证据失效/缺失，1 致命错误，0 没有发现失效精确证据。它不重新计算感知/局部匹配，也不重扫整个数据集；只有候选的报告可 valid=0、skippedCandidates>0、退出 0。读取 verificationScope 与逐项 counts，不把退出 0 作为候选确认。

独立记录三个状态：报告内容身份已核对；特定精确证据已复验；特定候选经谁何时人工复核。人工确认同源不能改变原始 core.local_candidate 类型，更不能推出模型确实训练过该图。

## 完整性和成本

- scope.discoveredAtLeast / entriesScanned：目录发现范围及枚举边界。
- scope.acceptedImages 或 images.length：成功生成指纹的图像数。
- stats.processedImages：进入已处理审计前缀的图像数；近似搜索耗尽预算时，后缀不保证完成精确关系检查。
- coverage、complete、errors、stats.reason：共同解释结果。完整 base 的覆盖结论可保留；不完整 base 不产生全数据集无重复声明。
- comparisons = distanceEvaluations + pairChecks；MIH 另计 indexOperations，上限为该次 maxComparisons × 16。未触发预筛选时字段可能缺省；未知旧版本不能把缺失当已知零成本。
- scope.totalDecodedPixels 是成功解码的源像素量。失败解码仍可能已消耗 CPU/内存，记时间/RSS，未知像素消耗保守扣 reservation，不把失败视为免费。

默认总解码额度 300,000,000 是整个 Investigator 任务预算，包含重复审计和精确证据复验；不是每次 CLI 额度。Core 默认单次是 100,000,000，单次可配置上限是 1,000,000,000。4MP 图片在默认单次额度下约只能处理 25 张，max_images=1000 不是容量保证。M0 预检图片尺寸并展示预计覆盖；不能默默扩大用户额度。

## 预算预留与执行

每次 audit 分配：

- maxComparisons ≤ min(策略额度、剩余 comparisons、10,000,000、floor(剩余 indexOperations / 16))。
- maxTotalPixels ≤ min(策略像素额度、剩余像素、1,000,000,000)；剩余额为 0 则不启动。
- maxDecodePixels、maxPixels、maxFileBytes、maxImages、maxPairs 分别通过实际 capabilities 上下限检查。
- 启动前记 action_id、输入/参数摘要、reservation 和唯一输出目录；完成后结算实际指标与退款。超时/无报告时保守扣除预留，并保留 unknown，不允许重试重置总账。

verify 不接受 audit 的像素额度开关。适配器先从报告列出精确证据端点去重，核对当前输入身份、尺寸和文件限制，预留其解码量，再通过进程组超时及可用平台资源限制执行。预算不足则保留 unverified/partial；不绕过额度。输入变化检查不是对抗性原子快照，强快照需求另用独立拷贝。

模型调用还受 max_llm_output_tokens 与费用约束；不能把未返回 usage 的调用记为零。模型不接触预算修改入口。

为结案预留 2 次工具操作和 10 秒：用于必要验证/确定性报告。启动前验证总预算大于预留额度；规划不得动用预留。报告写入失败应记录 failed，不能无限延长预算；无需验证或额度不足时也要输出明确 partial，不必硬凑一次 verify。用户等待时间不计机器执行时间。

## 结论规则

contracts/claim.schema.json 约束结构，contracts/claim-rules.json 约束必要证据和前提，宿主仍需解析真实字段。规则表不是自然语言蕴含判定器：关键断言由模板生成，模型解释不得引入新肯定事实。

核心关联、元数据来源声明、风险推断保持独立。新实体泛化任务中，已确认的实体列跨 split 重叠可支持“按所提供元数据存在实体重叠”，不能支持“已验证自然来源同一”或“模型已污染”。未知目标/缺字段只能 inconclusive。

## 升级流程

在独立分支显式更新 core.lock → 获取真实 capabilities → 契约与 T29—T35 → 相同数据的语义回归 → 比较资源/完整性变化 → 切换默认依赖。旧报告和复核保留原版本、profile、auditId。0.6.0 改了工作统计和编译摘要，旧复核不能凭文件名自动迁移。

A—D（未来 E）使用同一 Core 锁；Core 版本升级另设因子。不能把新索引更快归因为 Agent 更聪明。首版 M0—M3 + M5 子集不等待 Core 下一版本或策略优化研究。

能力快照摘要只用于追溯本次核查；runtime.node 等环境字段随安装环境变化，不要求整份输出字节相等。身份/profile/范围等关键字段与产物摘要必须匹配锁。注册表发布状态独立记录；CLI 接入不依赖 Mooncakes 发布成功。
