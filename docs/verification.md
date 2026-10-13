# SDK 0.1.0 验证

2026-10-13，Python 3.12，源码基线 main `392d02383fdcda47f0cfec8a61fa965d8a1a1632`。
机读身份与读回摘要见 [verification.json](verification.json)。

- 17 项离线 HTTP 协议测试通过：查询与成功结果、自动/显式修订、Event/Data 增删、
  RD721 无重试、参数 READ 和嵌套 Operation 成功/failed/partial/running、事件拒绝、
  bytes Base64、三类变更超时无重发、原请求 ID 查询、会话变化、JSON/响应 ID 校验及身份选择。
- 整个分发目录复制到仓库外，在干净 venv 中通过 `pip install ./Management-SDK` 安装，
  正常导入后运行全部 17 项测试。移除 PYTHONPATH/PYTHONHOME，导入位置为该 venv 的 site-packages。
- 从仓库外目录构建 wheel 和源码包。另一干净 venv 用 `pip install --no-deps <wheel>` 安装，
  导入、17 项协议测试、自包含示例及真实 Runtime 查询通过；包元数据无 Requires-Dist，
  sys.path 无 monorepo，未加载 industrial_apps、experiments 或 Softbus 模块。

实际联调使用既有 `127.0.0.1:18080` Runtime，`test_mode=false`，独立的纯软件双容器应用，
由平台既有公共工程入口导入、构建并启动。未连接实体设备。验证了应用/实例/端口/参数/连接/
运行状态查询、参数读写（赋值不触发事件）、5 次事件接纳与相应执行记录（包含显式 bytes ABI）、
一次修订冲突、两次原请求结果查询，以及 Event/Data 各一次删除与创建。
Event 删除后下游不再执行，Data 删除后目标数据不再更新；重建后数据和事件行为恢复。

四次连接变更全部 `saved.applied=true`；Event 删除/创建各有 2 个 Agent 回执，Data 各有 1 个。
恢复读回确认两条初始连接、六个初始参数值和 active 状态一致；修订从 1 递增至 5。
随后通过公共 halt/cleanup/unregister 清理本次应用与 artifact，确认无应用、连接部署和本次活容器，
资源拓扑未变。Runtime 保留正常的 removed 部署和有界诊断记录；不回退修订或清空其他人的记录。

这些是协议回归和功能 smoke，不是性能实验，也不代表所有 Python 版本或实体设备已验证。
