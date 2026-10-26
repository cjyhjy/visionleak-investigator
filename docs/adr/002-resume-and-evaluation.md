# ADR-002 — 保留历史解释、保守恢复和实验边界

2026-10-26，accepted。用户回答和复核生成不可覆盖 revision，原报告不改写；同输入/Core/profile 的图像证据可复制引用而不重扫。基于最新 revision 的累计账本结算后续操作，重复相同 payload 返回已完成结果。使用文件锁串行化 revision。崩溃后 pending 预留全额记 unknown，不自动重试；原始报告保留但不接受为肯定证据，输出 PARTIAL。

目前恢复是保守结案，不是断点扫描或 Core 缓存。图片变化拒绝续用；元数据变化需新登记/新 run。人工同源确认单独保存，原 Core kind 保持不变。

12 个程序生成 seed 只做 development 工程 smoke，不是新自然图像来源。真值在 evaluator 独立目录，生产 registry 不暴露。A/B/C 使用相同 Core 锁、数据和总上限，D 明确 blocked，E deferred。CLI 进程每次重启，没有跨条件指纹缓存；OS 文件缓存没有清空，不能称物理 cold-cache benchmark。没有收集 CPU/进程树 RSS 的数值，不能据此推断性能领先。
