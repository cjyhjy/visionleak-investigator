# 示例说明

这些是规格用的输入和策略样例，不是已运行的程序输出。

- `task.example.json` 可以通过 TaskSpec schema，但其中的逻辑 registry 引用尚需开发者用合成演示生成器注册。
- `action.ask-goal.example.json` 是合法的澄清动作结构。
- `action.run-transform.example.json` 结构合法，但引用只是示例；运行时在 registry 不存在该证据时必须拒绝执行。
- `policy.example.json` 是未验证的策略配置起点，不是已优化结果。
- `runtime.defaults.json` 默认禁用远程模型和发布；无凭据不阻止离线开发。

JSON Schema 只能验证结构。所有权限、证据存在性、同一 run 归属、总预算与状态前置条件仍需服务端强制校验。

- `claim.local-candidate.example.json` 演示结构合法但尚待复核的候选结论，不能自动改为 confirmed。
- 新资源预算默认值是工程起点，M0 必须以图像尺寸和 Core 能力预检覆盖；不是性能承诺。
