# Management SDK

独立、同步的 Python HTTP 客户端，用于管理**已经运行的 Runtime 中已部署的应用**。
Python 3.9+，运行时仅用标准库，不需要本地 Softbus 库、工程文件或其他仓库目录。
服务端需支持 `runtime-api/1` 与 `iec61499-management-json/1`。

## 安装与连接

整个 `Management-SDK` 目录可以复制给第三方。使用普通安装，无需设置 `PYTHONPATH`：

```bash
python -m venv .venv
# Linux/macOS；Windows 使用 .venv\Scripts\activate
. .venv/bin/activate
python -m pip install ./Management-SDK
# 或直接安装收到的 wheel
python -m pip install management_sdk-0.1.0-py3-none-any.whl
```

SDK 不负责启动 Runtime、编译功能块或部署工程。请由平台管理员先准备软件应用，
告知服务地址和访问 token（若启用了鉴权）。Runtime 默认监听 `http://127.0.0.1:18080`，
默认 HTTP 是明文；远程访问应使用管理员提供的受保护入口。

```python
from management_sdk import ManagementClient

client = ManagementClient()  # 默认 timeout=10 秒
# client = ManagementClient("https://runtime.example", token="...", timeout=5)
print(client.list_applications())
print(client.list_connection_deployments())
```

结果是服务端 `result` 字典，不附加复杂对象模型。第一次请求自动获取 capabilities
并固定 `runtime_session_id`；后续请求携带 `X-Runtime-Session`。客户端供顺序调用。
SDK 禁用环境 HTTP 代理且不跟随重定向，`base_url` 应直接指向服务入口。

## 明确选择应用、实例与端口

从上面的查询结果中明确选择 `application_id` 和属于它的 `connection_deployment_id`。
每个操作都要求身份参数，SDK 不会从多个对象中静默挑选一个。
以下 `app_id`、`conn_id`、端口和变量引用应替换为查询到的实际值。

```python
app_id = "demo"            # 使用查询结果中的 application_id
conn_id = "demo-conn1"     # 使用查询结果中的 connection_deployment_id
application = client.get_application(app_id)
print(application)        # function_blocks/ports：事件方向；metadata.data_fields：WITH 字段；inputs：声明输入
print(client.query_function_blocks(app_id))  # FBList：实例、类型、Resource、host_state
print(client.query_parameters(app_id, container="control"))  # Parameters：Reference/Type/Direction
print(client.query_connections(app_id, conn_id))              # 当前连接与 revision
print(client.get_connection_deployment(conn_id))              # 含 Event/Data network_binding
print(client.get_status(app_id))
print(client.get_execution_state(app_id))                     # 实际拓扑、修订、Agent 执行观察
```

`QUERY FB` 的 host_state 来自容器观察，不代表独立的功能块生命周期。
参数通配查询必须指定 owning container；具体参数引用可由服务端解析所属容器。
完整端口引用可能带应用网络前缀，例如 `app.Source.REQ`，必须按查询结果使用。
`query_connections` 的 `Connections` 是 Source/Destination 列表，类型及 Data 信息可查
连接部署的 `network_binding`。`get_execution_state` 的 topology 可能为 null（尚未激活、
观察缺失或过期等），不能把旧配置视为正在运行的连接。

## 增删 Event / Data 连接

连接增删只作用于**已有编译实例和端口**，不会创建功能块。调用者指定连接部署，
并选用 `connection_type="Event"`（默认）或 `"Data"`：

```python
topology = client.query_connections(app_id, conn_id)
removed = client.delete_connection(
    app_id, conn_id, "app.Source.CNF", "app.Sink.REQ",
    expected_revision=topology["revision"],
)
created = client.create_connection(
    app_id, conn_id, "app.Source.CNF", "app.Sink.REQ",
    expected_revision=removed["revision"],
)
print(created["revision"], created["saved"])

# 另一个 Data 连接示例：先根据实际拓扑确认该连接存在
# removed = client.delete_connection(app_id, conn_id, "app.Source.Value", "app.Sink.X",
#                                    connection_type="Data")
# created = client.create_connection(app_id, conn_id, "app.Source.Value", "app.Sink.X",
#                                    connection_type="Data", expected_revision=removed["revision"])
```

不传 `expected_revision` 时，每次变更前通过 QUERY 读取**指定应用和连接部署**的已确认修订，
不缓存猜测值。读与写之间仍可能发生竞争；`RD721` 会直接抛出，不刷新修订后自动重试。
传入显式修订可保护调用者此前观察的拓扑。连接操作同步完成，返回实际 `saved.applied`、
`saved.receipts` 及新 `revision`；未激活的配置修改可能 `applied=false`，不能解释为已作用于 Agent。
拓扑恢复通过新的增删操作实现，修订会继续增长，不能回退旧修订号。
跨容器连线是此平台的扩展；编译 ABI、单驱动、不可变版本占用和容量限制由 Runtime 校验。

## 参数赋值与事件触发

```python
before = client.read_parameter(app_id, "app.Source.IN")
print(before["Parameter"]["Value"])
written = client.write_parameter(app_id, "app.Source.IN", 42)
print(written["operation"]["state"], written["operation"]["result"])
receipt = client.trigger_event(app_id, "app.Source.REQ")
print(receipt["accepted"], receipt.get("admission"))
```

**参数赋值不会触发事件。** WRITE Parameter 接受 JSON 布尔、整数、有限实数及固定长度数组，
不做字符串/数字或布尔/整数转换。需要调用单独的 `trigger_event` 才触发已声明输入。
即使 HTTP 200、`ok=true`，SDK 仍检查嵌套 Operation 的 state，失败、partial 或未完成均抛错；
成功返回完整字典，保留 operation_id 和实际结果。旧生成程序可能返回 `RD724`，需管理员
用匹配的原生 SDK 重建程序。

`trigger_event` 返回的是**接纳回执**，`accepted=true` 不表示执行完成。
拒绝会抛出 `ManagementError`，保留 `accepted=false`、Reason、refusal_reason 等详情。
使用 `get_execution_state(app_id)` 查看 Agent 的 `event_admissions` / `event_executions`，
按回执 ID → admission.sequence，并核对同一 Agent/activation 的执行记录。
执行状态与接纳状态分别保留；单个输入 handler 完成也不证明整条下游链完成。
两类历史各最多 64 条，记录过期或缺失表示结果未知，不能推断成功。

可选 `payload: bytes` 会自动 Base64 编码为 `Connection.payload_base64`。
这是**平台事件载荷扩展**，必须匹配编译端口 ABI；它不是 IEC 61499 Parameter WRITE。
不传 payload 时使用平台对该输入的默认/WITH 快照行为：

```python
# 仅在管理员已确认端口 ABI 时使用显式字节载荷
# receipt = client.trigger_event(app_id, "app.Source.REQ", payload=b"\x2a\x00\x00\x00")
```

## 错误、超时与会话变化

```python
from management_sdk import ManagementError

request_id = client.new_request_id()  # 在变更前保存 ID，便于超时后核对
try:
    result = client.create_connection(
        app_id, conn_id, "app.Source.CNF", "app.Other.REQ", request_id=request_id,
    )
except ManagementError as error:
    print(error.http_status, error.code, error.request_id, error.details)
    if error.outcome_unknown:
        # 不重发连接命令，只在原会话内查询原请求
        outcome = client.get_request_result(request_id)
        print(outcome)  # complete/result/error；complete=false 表示仍未完成
```

统一异常字段为 `http_status`、`code`、`request_id`、`details`、`response`（完整响应）
和 `outcome_unknown`。服务器有错误码时原样保留；客户端错误使用 `SDK_TIMEOUT`、
`SDK_TRANSPORT`、`SDK_PROTOCOL`、`SDK_EVENT_REJECTED` 等。事件拒绝没有服务端错误码时，
使用 SDK_EVENT_REJECTED，服务端 Reason 等仍保存在 details 中。失败的 Operation 也保留完整记录。
参数类型、地址等客户端入参错误使用 Python 的 ValueError/TypeError。

网络失败或超时不取消服务端已接纳工作，**不自动重发任何变更或事件**。
自动生成的 ID 也可从异常 `request_id` 取回。连接请求可以通过 `get_request_result` 查询；
完成记录有界（最多 256 个完成结果及 128 个在途请求），过期返回 RD010。
查询结果中的 `error` 由调用者检查，查询本身不重新执行命令。
参数 WRITE 可用已知 `operation_id` 调用 `get_operation`，或查看 execution-state 的 commands；
事件通过上述接纳/执行观察核对，不能用连接请求表承诺事件结果。
请求 ID 不保证事件恰好一次；切勿因未观察到完成而自动再次触发。

收到 RD017 表示 Runtime 会话结束或变化。旧客户端保持原身份并抛错，不自动获取新身份
或重放旧命令。创建新的 ManagementClient、重新查询部署身份后，由调用者决定新操作。

## 示例、测试与打包

```bash
# 安装后运行；默认只查询，不修改任何应用
python Management-SDK/examples/manage.py
python Management-SDK/examples/manage.py --application YOUR_APP --container YOUR_CONTAINER
# 显式赋值或注入，端口与变量来自查询
python Management-SDK/examples/manage.py --application YOUR_APP --write YOUR_FB.IN --value 42
python Management-SDK/examples/manage.py --application YOUR_APP --trigger YOUR_FB.REQ

# 离线测试：仅启动 loopback 模拟 HTTP 服务器
python -m unittest discover -s Management-SDK/tests -v
# 在独立目录内构建 wheel 和源码包
python -m pip install build
python -m build Management-SDK
```

目录自身包含源码、示例与测试；wheel 包含可直接导入的 management_sdk，源码包同时携带示例和测试。
实际安装和实机验证结果见 [验证说明](docs/verification.md)。
