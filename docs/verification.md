# SDK 0.2.1 验证

2026-10-14，Python 3.12，SDK源码基线 `d0485ae523767de65bf3c5256d0d9da87858dc92`。当前接口通过Apps HTTP管理当前应用，普通方法不增加应用或activation字段。机读摘要见[verification.json](verification.json)。

- SDK协议18项通过：响应中途截断、HTTPException、已收到的HTTP状态与request_id保留、四类修改结果未知、只读请求非修改未知、无重发和恢复正常响应；原有会话、协议、连接、参数与事件回归保留。
- SDK目录复制到仓库外，构建wheel后在另一干净venv安装，18项回归全部通过；导入位置在venv，元数据无运行时依赖，不导入平台模块或加载原生Softbus库。0.2.1亦安装到当前用户环境。
- Apps后端65项、Runtime相关4项回归通过。现有namespace端到端夹具的定向管理场景通过：Apps当前应用校验后推进连接修订并重新激活，再发送原请求；参数WRITE与事件均以RD529拒绝，当前身份正常调用通过。Agent回归另验证旧管理信封不能作用于新activation。
- 已更新实际Apps与Runtime服务。既有 `127.0.0.1:8080` 入口使用安装后的SDK，在纯软件双容器应用上完成参数写入/读回、无隐式事件、事件入队及匹配执行记录检查，修改回执确认transport=softbus。旧activation的两类请求均拒绝；临时应用halt、cleanup、unregister全部成功。

并行运行的namespace HTTP检查曾超时，串行补测通过；全量端到端夹具的额外S0忙轮询场景仍记录为超时，未宣称全量通过。上述验证支持管理行为与安装链路，不构成性能或实体设备验证；论文及既有实验数据未修改。
