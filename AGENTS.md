# Management SDK 协作规则

本文件适用于独立的公开 `management-sdk` 仓库；在完整平台中同时遵循平台根规则。
按任务查阅 [README](README.md)、[使用说明](docs/usage.md)、[验证记录](docs/verification.md)和 `src/management_sdk/`。

## 接口与独立使用

- SDK 通过 Apps 公开 HTTP 管理应用，不导入 Apps/Runtime 私有模块或本机动态库；保持独立安装、标准库运行依赖及 Windows/Linux 客户端可用边界。
- 保持已发布 `management-sdk` 包名、`management_sdk` 导入路径和公共接口兼容；协议或分发演进须同步实现、文档、版本与相关验证。
- 保留目标 Runtime、会话和激活身份检查，真实错误、部分结果及结果未知状态；修改操作超时不自动取消、重试或切换目标重发。
- 请求受理与应用/设备执行完成分别表示，不根据客户端调用成功推断物理业务效果。
- 本仓库仅发布所属 SDK 的源码、文档、示例和验证材料；凭据、缓存、私有配置、平台实验数据及其他组件源码不得进入公开历史。

## 验证与文档

- 协议单测使用 loopback 模拟服务器，不修改真实应用；明确授权的集成验证按对应目标和操作范围另行执行与记录。
- 代码改动在隔离虚拟环境中安装包，运行受影响测试；完整回归入口为 `python -m unittest discover -s tests -v`。分发/依赖变更或版本发布时验证 wheel 安装和导入。
- 仅文档或 AGENTS 改动检查链接和差异，不因此重新安装包、构建 wheel 或调用实际服务。
- 用法与错误语义更新 README/usage，验证事实更新 verification；不把待实现接口写成已支持，不为规则整理新建并行计划。

## 命名与提交

文档采用 kebab-case，Python 文件、包、函数和变量使用 snake_case，类 PascalCase，常量 UPPER_SNAKE_CASE；保留标准文件名和既有符号。
检查工作区并保护已有修改；提交/推送遵循用户已有授权和约定分支，精确暂存本轮文件，使用 Conventional Commits。
