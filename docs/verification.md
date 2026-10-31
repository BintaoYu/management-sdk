# SDK 验证

## 当前分发验证

2026-10-25：0.3.0 新增静态 Runtime 选择、设备目录读取和 FB START/STOP/KILL/RESET 方法。
22 项 loopback 协议测试通过；wheel 在独立 `/tmp/management-sdk-0.3-verify` venv 安装后同一 22 项通过。
wheel SHA-256 为 `c338146d81fc550cda63eed5a095c02b4bb3deb81569ad37cb165ff258c0517e`。
此记录只证明客户端协议与独立分发；双 Runtime 执行验证归 Apps 既有 e2e fixture 记录。

## 0.2.2 分发记录

2026-10-20：0.2.2 wheel构建完成，在独立干净venv中安装并通过19项协议测试，导入路径来自该venv。
测试使用loopback模拟服务，未发送真实设备或应用修改命令。该版源码摘要和 wheel 摘要见[机读记录](verification.json)；该文件保存 0.2.2 及更早记录，不代表 0.3.0 的分发身份。

## 0.2.2 账号认证

2026-10-16 新增可选 `ManagementClient(..., token=...)`。19 项协议回归通过，覆盖 bootstrap、读取和修改请求都携带 Bearer 认证、拒绝非法请求头，并保持不自动重发。
wheel 构建、安装成功，实际安装包为 0.2.2；经已启用账号的 Apps 入口读取 39 项类型，未触发运行操作。
源码包与安装包均暴露相同 token 参数；凭据由调用环境提供，不写入日志或项目。

## 0.2.1 集成记录

验证日期为 2026-10-14，Python 3.12，SDK 源码基线为
`d0485ae523767de65bf3c5256d0d9da87858dc92`。历史记录保留在[verification.json](verification.json)的`prior_integration_verification`中，调用方式见[使用说明](usage.md)。下列小节仅描述该次 0.2.1 验证，不代表当前服务安装身份，也不替代上面的新版分发记录。

### 协议与分发

| 项目 | 结果 |
| --- | --- |
| SDK 协议回归 | 18 项通过 |
| 仓外复制、构建 wheel、另一干净 venv 安装 | 同一 18 项通过；导入位于 venv |
| 运行依赖 | 无；不导入平台模块，不加载原生 Softbus 库 |
| 当次用户环境安装 | 0.2.1 |
| Apps 后端回归 | 65 项通过 |
| Runtime 定向回归 | 4 项通过 |

覆盖响应中途截断、HTTPException、已收到的 HTTP 状态与 request_id 保留、四类修改结果未知、
只读请求不误报为修改结果未知、无自动重发及恢复正常响应。原有会话、协议、连接、参数和事件回归保留。

### 身份与实际服务

现有 namespace 管理场景在 Apps 当前应用校验后推进连接修订并重新激活，
再发送原请求：参数 WRITE 和事件均以 RD529 拒绝，当前身份调用通过。
Agent 回归验证旧管理信封不能作用于新 activation。

该次验证使用当时更新后的 Apps / Runtime 服务。安装后的 SDK 经既有 `127.0.0.1:8080` 入口，
在纯软件双容器应用上完成参数写入与读回、无隐式事件、事件入队与匹配执行记录检查；
修改回执确认 `transport=softbus`。旧 activation 的两类请求拒绝，临时应用 halt、cleanup、unregister 全部成功。

### 限制与未通过项

并行 namespace HTTP 检查曾超时，串行补测通过。全量端到端夹具中的额外 S0 忙轮询场景仍为超时，
不宣称全量通过。上述结果支持管理行为与分发安装链路，不构成性能或实体设备验证。
