# SDK 0.2.0 验证

2026-10-13，Python 3.12，源码基线 main `0623c919740461aca574539d22414fe1a7c2ac11`。
当前接口为 Apps HTTP，未保留同一客户端中的 Runtime 直连协议。机读摘要见
[verification.json](verification.json)。

- SDK 离线协议 16 项：简单查询/标量、类型库、CSRF/context、无当前/多个候选、冲突、
  事件拒绝、Operation 错误、运行上下文变化、三类变更及读取超时、无重发、协议与参数校验。
- Apps 管理及既有 RuntimeClient/Softbus/lifecycle 相关回归 64 项；故障状态仍可读取，变更拒绝。
- 前端 193 项测试及生产构建；普通命令 body 不包含部署/修订/请求 ID 或事件载荷。
- SDK 完整目录复制到仓库外，干净 venv 普通安装、导入和 16 项测试；独立 wheel 在另一干净
  venv 安装、导入及 16 项测试。元数据无运行时依赖，导入路径不包含 monorepo，未加载仓库模块或动态库。

既有 Apps `127.0.0.1:8080` 与非 test-mode Runtime 实机验证使用独立纯软件双容器 Source/Sink。
类型库/端口/方向/DINT/WITH/参数定义、当前实例、真实连接和运行状态查询通过。
参数赋值后计数保持，随后独立事件接纳与执行记录匹配；Event/Data 各删除、创建后检查实际行为。
所有变更回执确认 Apps→Runtime transport=softbus。HTTP 200 的实际嵌套参数失败、重复连接冲突、
根围栏事件拒绝、Apps 重启后旧上下文/CSRF 拒绝，以及一次超时请求只完成一次均有实机读回。

实际浏览器看到 SDK 连接变更后边数 2→1→2；Event 与 Data 分别验证，无需页面刷新。
浏览器连接删除/创建及事件触发使用同一简化接口，SDK 读回确认，页面无 JavaScript 错误。
六个初始参数值和两条连接恢复，连接修订正常递增；随后经公共 halt/cleanup/unregister 清理测试部署。
宿主资源拓扑不变；正常 removed 部署和有界诊断记录保留。

安装到实际服务入口。启动期间曾有一次只读 bootstrap 超时，另一次独立管理员测试因本地 IPC
权限被拒绝；改在服务就绪后并用已授权管理员权限验证，未重发业务命令。对应尝试日志保留。
这些是功能 smoke 与协议回归，不是性能或实体设备验收；其他 Python 版本未实测。
