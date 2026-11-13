# Management SDK 使用说明

先按[README](../README.md)安装并连接 Apps，再按下述接口查询类型、修改连接、读写参数或触发事件。错误处理与打包约定见后文。
代码中的引用必须替换为实例查询返回的实际名称。Shell 命令均在 SDK 仓库根目录执行。

## 连接与调用边界

`ManagementClient()` 默认连接 Apps `http://127.0.0.1:8080`，等待预算为 10 秒；
可显式设置 `ManagementClient(base_url, timeout=5)`；本机非浏览器调用无需凭据，按Apps服务所属管理员处理。SDK内部仅获取运行上下文，不请求或传递认证材料。
客户端不使用环境 HTTP 代理，不跟随重定向；同一实例按顺序调用。

`list_runtimes()` 返回 Apps 静态设备目录；`ManagementClient(..., runtime_id="right")` 将所有请求及会话绑定到该目标。
不提供目标时沿用工程默认 Runtime；默认端点存在歧义时明确拒绝。SDK 不将操作广播到所有设备。

## 客户端模块边界（设计）

当前实现仍集中在 `src/management_sdk/client.py`，公共导入、`ManagementClient` 和 `ManagementError` 保持。
为独立开发和测试预留以下逻辑边界；本节不表示新增文件、传输选项或插件入口。

| 边界 | 职责与约束 |
| --- | --- |
| 公共管理接口 | 实例/类型、连接、参数、事件与 FB 生命周期方法；不依赖 Apps 私有源码或本机 Runtime 动态库 |
| 协议与运行上下文 | 请求/响应校验、目标/会话/激活关联、修订和错误解释；保留结果未知，不自动刷新后重放 |
| HTTP 适配 | 地址、超时、有界收发、关联 ID 和协议错误；不决定应用目标，不自行切换设备或重试修改 |
| 包与测试 | 标准库运行依赖、稳定导入和独立安装；loopback 协议测试与实际 Apps/Runtime 集成分别验证 |

后续有明确维护需求时才按这些边界拆分实现，通过内部受控注入验证传输失败及上下文变化；
不要求每类业务方法单独成包，也不预留 API 凭据认证。发布版本与已验证范围仍见[验证说明](verification.md)。

## 类型库与已部署实例

```python
print(client.list_block_types())
# name 使用查询返回的完整名字；不同内容的同名类型带 @ 摘要后缀，避免混淆
print(client.get_block_type("sdk::SOURCE"))
print(client.list_instances())
```

类型库是 Apps 各项目既有库的合并视图，不表示类型已部署，也不创建功能块。
`get_block_type(name)` 返回 `interface`（event_inputs/outputs、data_inputs/outputs），
包括方向、数据类型、数组大小、初值及事件的 with_variables；`parameters` 包含数据变量
和内部参数定义。类型库在无运行应用时仍可查询。

`list_instances()` 只查询当前 Runtime 中编译、部署的实例，返回 name、type、container、state、
host_state、event_ports 与 data_ports。`state` 是 FB 的 `IDLE/RUNNING/STOPPED/KILLED/UNKNOWN`，`host_state` 是承载执行器状态，两者独立。
实际引用以 name/端口查询结果为准，如 `app.Source.IN`。
库定义描述可用参数；旧程序若未编译对应读写回调，实际参数访问会返回明确的 Runtime 错误，
须由管理员用匹配原生 SDK 重建。

## 功能块生命周期

```python
client.stop_function_block("app.Source")
client.reset_function_block("app.Source")
client.start_function_block("app.Source")
# client.kill_function_block("app.Source")
```

上述命令只控制指定编译实例；复合实例包含其内部子实例。STOP 保留变量，RESET 恢复参数化初值及 ECC 初始状态。
允许的转换为 IDLE→START→RUNNING，RUNNING→STOP→STOPPED，RUNNING→KILL→KILLED，STOPPED→START→RUNNING，
STOPPED/KILLED→RESET→IDLE。其他转换明确报错；不把重复 STOP 当作新命令的成功。
各方法返回 `completed`、`function_blocks` 和实际管理回执；仍受会话及激活身份约束，不自动重发。
Python/HMI 等未实现 reset callback 的实例由 Runtime 拒绝 RESET，不能把局部重置包装成成功。

## 查询和修改连接

```python
print(client.get_connections())  # [{source, destination, type: "Event"|"Data"}, ...]
print(client.get_status())       # state、agents、实际 topology、commands 和诊断

# 用已有实例的实际端口替换下面的引用
removed = client.delete_connection("app.Source.CNF", "app.Sink.REQ")
created = client.create_connection("app.Source.CNF", "app.Sink.REQ")
print(created["completed"], created["applied"])

# Data 端口使用相同方法，Apps 自动识别
# client.delete_connection("app.Source.Value", "app.Sink.X")
# client.create_connection("app.Source.Value", "app.Sink.X")
```

连接增删仅操作已有编译实例和端口。Apps 从端口定义推断 Event/Data，内部读取指定当前
连接部署的修订，Runtime 保留 CAS、所有权、ABI、单驱动和容量检查。读与写间的修订冲突
直接反馈 RD721，不刷新后自动重试覆盖。

连接操作同步完成，返回 completed、applied 和可关联 request_id；复杂实际应用回执、新修订
和传输信息保存在 diagnostics。连接配置不是执行证明；`get_status().topology` 缺失/null 表示
执行拓扑尚未确认，不能用旧拓扑冒充正在运行的连接。恢复拓扑用新的操作，修订正常递增。

## 固定实例的批量拓扑更新

批量接口保持实例、算法、端口和部署位置，允许同批替换 Data 驱动以及修改 Event 连接。先读取当前版本并规划，审阅候选图与影响范围后，显式提交相同的变更、版本、摘要和激活身份：

```python
client = ManagementClient("http://127.0.0.1:8080", timeout=70)
changes = [
    {"operation": "DELETE", "type": "Data", "source": "app.Source.A", "destination": "app.Sink.X"},
    {"operation": "CREATE", "type": "Data", "source": "app.Source.B", "destination": "app.Sink.X"},
]
revision = client.get_status()["connection_revision"]
plan = client.plan_topology_update(changes, expected_revision=revision)
print(plan.get("plans") if plan.get("distributed") else plan["network_binding"])
# 在调用方完成候选审阅后执行：
result = client.apply_topology_update(changes, expected_revision=revision,
    plan_sha256=plan["plan_sha256"], activation_id=plan["activation_id"], timeout_ms=10000)
print(result["completed"], result.get("participants", result.get("operation")))
print(client.get_status()["topology_update"])
```

`plan_topology_update` 只读，失败不标成未知写入。提交不会自动重新规划、刷新 revision 或重试。
`get_status` 同时返回当前连接 revision 和 Runtime 的 `topology_update` 事务记录；跨版本读回冲突会明确报错。
应用被隔离时仍可查询事务并显式调用 `recover_topology_update(transaction_id, action="abort"|"finish")`。
提交前可请求恢复旧图，提交决定后只能 finish；Runtime 核验当前事务、参与者和决策，SDK 不自行回滚。
单端 `completed` 仅在 Operation 成功时为 true；跨端仅在所有参与者发布并放行后为 true。partial、失败、结果未知和业务执行完成各自判断。
超时不会取消或重发工作；先读取原事务状态。`timeout_ms` 为 Runtime 的 1..60000 ms 等待预算，客户端 HTTP `timeout` 应留出额外处理时间。

单 Runtime 支持 SHM/TCP/UDP、既有背压 profile、受支持的 Basic-FB C++/Python 托管边界；SDK 0.22 的 Runtime 可核验托管载荷引用排空，支持内联与缓冲区 Event。
已部署的 SYS 可经同一接口协调其全部 Runtime：`plan.distributed=true` 时，`plans` 和 `participants` 封存每端会话、版本和物理 owner，返回的共同摘要须原样提交。
`expected_revision` 约束所选 Runtime；共同摘要同时约束其他参与端，SDK 不为旧计划选择新的版本。
跨端成功结果包含 `transaction_id`、`decision=commit`、`state=succeeded` 和各端 `participants`，不返回伪造的单个 Runtime Operation。
失败后用该共同事务 ID 显式恢复；未知修改保留 `outcome_unknown`，不自动重发。

跨端当前为同 ABI、非分类 TCP/UDP 的 `event-bytes-with/2`，保留 `inline-event-with/1` 兼容；大载荷传实际字节，接收端重建本机缓冲区/FrameRef，不传共享内存引用。远端 WITH Data 的发布者须与 Event 来源同容器；本地 Data 来源可独立。
其他设备上的独立 Data、注册 I/O、未托管引用、不同 ABI 和物理设备资格分别验证，不支持的组合明确拒绝。管理客户端版本保持 0.5；载荷能力取决于目标 Runtime 与匹配的原生 SDK。
Runtime 选择只绑定客户端上下文，参与范围仍由该 SYS 的完整设备目录确定；连接/提交完成不等于物理设备动作完成。

## 参数读写与事件触发

```python
before = client.read_parameter("app.Source.IN")  # 直接得到值
client.write_parameter("app.Source.IN", 42)
receipt = client.trigger_event("app.Source.REQ")
print(receipt["accepted"], receipt["request_id"])
```

参数赋值不会触发事件。读写直接使用 JSON 布尔、整数、有限实数及固定长度数组，不做
字符串/数字或布尔/整数转换。WRITE 必须实际 Operation 成功才返回 completed=true；
HTTP 200 中嵌套的 failed/partial/running 不会被包装成成功。

`trigger_event(reference)` 只触发已声明输入事件，返回接纳结果；accepted=true 不代表执行
完成。普通接口不暴露 Base64 或原始 ABI 载荷。需要确认 handler 完成时，查询 get_status 的
agents，通过 diagnostics 中的 admission.sequence 对应同一 activation/Agent 的 event_executions。
单个输入 handler 的执行结果不证明整个下游链完成；有界历史缺失时结果仍未知。

## 错误、会话变化与超时

```python
from management_sdk import ManagementError

try:
    client.trigger_event("app.Source.REQ")
except ManagementError as error:
    print(error.code, error.http_status, error.request_id, error.details)
    if error.outcome_unknown:
        print("结果未知；核对当前状态及命令记录，不自动重发")
```

ManagementError 保留 http_status、服务端 code、request_id、details、完整 response 以及
outcome_unknown。Runtime 拒绝原因及嵌套 Operation/事件拒绝回执保留在 details 中。
MG_NO_CURRENT、MG_MULTIPLE_CURRENT、MG_NOT_READY、MG_IDENTITY_UNCONFIRMED 说明当前应用
不能安全确定；RD721 是连接修订冲突；MG_EVENT_REJECTED 保留 accepted=false 与 Reason。
客户端网络/格式错误使用 SDK_TIMEOUT、SDK_TRANSPORT、SDK_PROTOCOL。
HTTP响应中途截断及其他HTTP协议异常统一转换为ManagementError，保留本次request_id及已收到的HTTP状态。
修改请求无法确认结果时outcome_unknown=true；响应读取失败不触发自动重发。

运行应用、激活或 Runtime/Apps 会话变化时，返回 MG_SESSION_CHANGED 或 RD017；浏览器会话另受 CSRF 校验。
旧客户端不会自动刷新后重放命令；请新建 ManagementClient、重新查询实例，再明确决定新操作。
若当前应用校验后、实际执行前发生重新激活，Runtime以RD529拒绝本次旧身份请求，参数和事件不会转交给新activation。
客户端超时不取消已接纳工作，也不自动重发连接变更、参数写入或事件。异常的 request_id 可与
get_status 中有界 commands / 事件接纳记录关联；记录缺失不能推断成功或失败。

当前 ManagementClient（0.5.0）仅接受 Apps 协议；0.1 的 Runtime 直连接口已移除。不要把
base_url 指向 Runtime 的 18080 端口。

## 示例、测试与打包

```bash
# 安装后直接运行，不设置 PYTHONPATH
python examples/manage.py --types
python examples/manage.py
python examples/manage.py --write app.Source.IN --value 42
python examples/manage.py --trigger app.Source.REQ

python -m unittest discover -s tests -v
python -m pip install build
python -m build .
```

离线测试只启动 loopback 模拟 Apps，不访问实际服务。wheel 包含可导入的 management_sdk；
源码包同时携带 README、示例和测试。当前独立安装与 loopback 协议验证范围见[验证说明](verification.md)。
