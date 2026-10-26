# ADR-001 — 固定发布 CLI 与本地领域层

2026-10-26，accepted。Python 3.12.14 + Node 26.7.0；使用开发包锁定的 Core 0.6.0 本地发布 ZIP，原 Core 工作树只读。源码与编译 JS 摘要均复验。sharp 安装在独立目录，先使用独立 npm staging 安装后复制，避免与 DNS 失败的首次安装并发写同一目录。`npm ci --ignore-scripts --no-audit --no-fund`；实际命令与失败均保留。

openJiuwen 0.1.19.post2 使用安装后的 Workflow/WorkflowComponent/Start/End/create_workflow_session API；已运行无模型工具工作流。领域层不导入 SDK；框架回调接受逻辑动作并经过本项目门禁。未实现或启用远程 provider adapter，不能声称真实 Agent 已完成。

证据身份通过一个固定 Node bridge 调用发布包的 report-identity / review-validation / workflow API；不重写 SHA 身份协议。bridge 为只读固定宿主代码，模型不能选择 import/path。0.6.0 report.localProfile 实际为含 version/windows 的对象，适配器读取 version，而非误当字符串；capabilities 使用 profiles.local.id。

默认规则仅依据明确请求文本选择补充 profile；确定性目标/元数据解释另做检查。它是透明、未调优的可复现规则对照，后续还需在独立开发集检验其强度，不以弱基线包装 Agent 收益。局部候选默认关闭。

A/B 由独立固定驱动入口调用公共审计管线，B 直接 all 一次；此例外不暴露给生产 Agent 动作门禁。首版计时覆盖工具调用和宿主校验；CPU/进程树 RSS 暂不报告数值。预算分配优先保留复验像素，不保证耗尽可用额度。

运行产物使用 exclusive create，证据由 hash/原报告身份交叉核验；账本/checkpoint 原子替换。完整的防管理员篡改、OS 网络隔离和强快照不在此实现保证内。
