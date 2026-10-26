# 08｜规划修订记录

本次修订依据实际 Core 0.6.0 实现与发布验收，保留原架构和历史 SOURCE_BASELINE，不将规划文本当实现成果。

1. 原 0.5.0 源阅读记录与当前执行依赖锁分开；新锁只填写真实发布 SHA/摘要。
2. 增加实际 capabilities 快照，明确 v1 local、全目录扫描、无缓存/增量/v2/端到端流式。
3. 补齐 verify 退出 0 但候选跳过的语义，独立记录报告身份、精确复验、人审。
4. 补齐解码像素、文件、索引和模型输出预算；保留结案额度，失败与未知保守计费。
5. 区分枚举、生成指纹、已审计前缀，修正目录与 CSV/manifest 输入边界。
6. 新增 ClaimRecord Schema 与规则表；关键结论用程序模板，不把引用存在等同于支持断言。
7. 首版交付 A—D，M4/E 后置；Core 升级收益与 Agent 效果分开。
8. 增加 T29—T35，覆盖上述真实接口陷阱。

本次没有创建 Investigator 实现，没有调用收费模型，没有替用户提交赛事。PLAN_VALIDATION.json 仅证明规划文件/契约的结构校验，Core 的验收来自独立发布收据，不能替代 Investigator 待实施测试。

正式依赖已锁定 Core 0.6.0 的公开提交 c69824ee63da3134a1ddb455f9ff9a90ee8d2607。GitHub 附件与 Mooncakes 均完成下载核验，详见 core.lock.json 和 CORE_RELEASE_RECEIPT.json。
