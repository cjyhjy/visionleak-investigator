# 第三方与 AI 使用说明

- **VisionLeak Core 0.6.0**，cjyhjy/moonbit-visionleak，提交 c69824ee63da3134a1ddb455f9ff9a90ee8d2607，MIT。原 LICENSE 保留于独立 `.deps/visionleak-core/LICENSE`；发布包、编译 JS、源码和运行摘要见 core.lock.json / core.runtime.lock.json。原项目未重写、未重新许可；指纹、检索、报告身份与 verify 算法属于既有 Core。
- **openJiuwen 0.1.19.post2**，通过 PyPI 安装，官方来源 https://github.com/openJiuwen-ai/agent-core 。仅运行本地无模型 Workflow API。依赖及摘要在 uv.lock；第三方包自带 LICENSE/metadata 保留在环境中，未复制 SDK 源码到项目。
- Pillow、jsonschema、pytest、sharp 及其依赖版本/来源由 uv.lock 和 Core package-lock.json 记录；不将它们归为本项目新增算法。发布前须另行汇总所有发行物许可。
- 开发文档中 Harness² 仅为方法参考；本项目未复制或运行其执行器，没有声称复现其研究结论。
- 本项目代码由 Codex 辅助编写与测试。测试图像是程序生成或其受控变换；无外部照片下载、无模型请求或向模型上传图片；负责人授权公开的测试图片均为合成素材。旧 Core 验收素材未用作新独立 test。
- 负责人于 2026-10-26 明确授权建立独立公开 GitHub 仓库并推送本项目代码及工程证据。未授予 Investigator 新许可证、发布软件包、接受赛事条款或提交赛事材料。
