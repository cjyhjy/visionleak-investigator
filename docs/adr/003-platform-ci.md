# ADR-003 — 显式平台迁移与真实 Core CI

2026-10-26，accepted。

原 runtime lock 包含 macOS arm64 sharp/libvips，不能直接在 Linux 校验。安装流程新增显式 --migrate-runtime 与必须的新 receipt 路径。原 Core 的非 node_modules 文件集合与摘要、sourceDigest、编译 JS 和 Node 精确版本保持不变；仅将 npm ci（package-lock 完整性校验）安装得到的原生依赖重新固定。迁移前保存完整旧/新锁，绝不在 audit/doctor 时自动重锁。receipt 不是兼容性证明，迁移后必须跑真实契约和审计。

工作流固定官方 Actions 提交、uv 0.12.13、Python/Node 版本，普通运行无需任何 secrets。Ubuntu 与 macOS 全新 checkout 验收；Linux 安装后用独立网络 namespace 禁止测试/审计联网。实际测试基于新合成数据和真实发布 Core，不读历史报告冒充运行。模型仍未运行。

Actions 的构建产物用于保存命令、失败日志、JUnit、迁移锁和新报告；工作流只读 contents 权限。参考官方 [uv 集成文档](https://docs.astral.sh/uv/guides/integration/github/) 与 [GitHub artifact 文档](https://docs.github.com/en/actions/tutorials/store-and-share-data)。
