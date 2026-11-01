# Management SDK 使用说明

先按[README](../README.md)安装并连接 Apps。本文补充类型、连接、参数、事件、错误和打包约定。
代码中的引用必须替换为实例查询返回的实际名称。Shell 命令均在 SDK 仓库根目录执行。

## 连接与调用边界

`ManagementClient()` 默认连接 Apps `http://127.0.0.1:8080`，等待预算为 10 秒；
可显式设置 `ManagementClient(base_url, timeout=5)`；本机非浏览器调用无需凭据，按Apps服务所属管理员处理。SDK内部仅获取运行上下文，不请求或传递认证材料。
客户端不使用环境 HTTP 代理，不跟随重定向；同一实例按顺序调用。

`list_runtimes()` 返回 Apps 静态设备目录；`ManagementClient(..., runtime_id="right")` 将所有请求及会话绑定到该目标。
不提供目标时沿用工程默认 Runtime；默认端点存在歧义时明确拒绝。SDK 不将操作广播到所有设备。

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

## 参数读写与事件触发

```python
before = client.read_parameter("app.Source.IN")  # 直接得到值
client.write_parameter("app.Source.IN", 42)
receipt = client.trigger_event("app.Source.REQ")
print(receipt["accepted"], receipt["request_id"])
```

**参数赋值不会触发事件。** 读写直接使用 JSON 布尔、整数、有限实数及固定长度数组，不做
字符串/数字或布尔/整数转换。WRITE 必须实际 Operation 成功才返回 completed=true；
HTTP 200 中嵌套的 failed/partial/running 不会被包装成成功。

`trigger_event(reference)` 只触发已声明输入事件，返回**接纳结果**；accepted=true 不代表执行
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

运行应用、激活或 Runtime/Apps 会话变化时，返回 MG_SESSION_CHANGED、RD017 或 csrf_rejected。
旧客户端不会自动刷新后重放命令；请新建 ManagementClient、重新查询实例，再明确决定新操作。
若当前应用校验后、实际执行前发生重新激活，Runtime以RD529拒绝本次旧身份请求，参数和事件不会转交给新activation。
客户端超时不取消已接纳工作，**不自动重发连接变更、参数写入或事件**。异常的 request_id 可与
get_status 中有界 commands / 事件接纳记录关联；记录缺失不能推断成功或失败。

当前 ManagementClient（0.3.0）仅接受 Apps 协议；0.1 的 Runtime 直连接口已移除。不要把
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
源码包同时携带 README、示例和测试。独立安装与纯软件实机验证见[验证说明](verification.md)。
