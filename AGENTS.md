# Management SDK Guidelines

本文件适用于独立的公开 `management-sdk` 仓库。在 `industrial-platform` 中工作时，同时遵循平台根 AGENTS；独立克隆只依赖本仓库文档和 Python 标准库。

- 先读 [README](README.md)、[验证说明](docs/verification.md) 和 `src/management_sdk/`；SDK 通过 Apps HTTP 调用，不导入 Apps/Runtime 内部模块或本地动态库。
- 仓库名和普通文档使用小写 kebab-case；Python 文件、包、函数、方法和变量使用 snake_case，类用 PascalCase，常量用 UPPER_SNAKE_CASE。`README.md`、`AGENTS.md`、`MANIFEST.in` 等标准名称保持原样。
- 保持已发布 `management-sdk` 包名和 `management_sdk` 导入路径兼容。保留会话校验、真实错误、结果未知状态及无自动重发约束；测试使用 loopback 模拟服务器，不修改实际应用。
- 本仓库公开源码、使用文档、示例和 SDK 验证；运行缓存、私有配置、平台实验数据和其他组件源码不进入此仓库。
- 独立验证：`python -m pip install .`，再运行 `python -m unittest discover -s tests -v`；发布前验证 wheel 安装和导入。
