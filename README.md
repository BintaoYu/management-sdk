# Management SDK

轻量、同步的 Python 客户端，通过 **Apps HTTP → Softbus → Runtime → 容器执行器**
管理当前运行应用。Apps 自动解析唯一运行应用；第三方只需功能块类型名、实例及端口引用，
不需要填写应用、部署、修订或请求 ID。Python 3.9+，运行时仅依赖标准库。

## 安装与最短调用

本 SDK 是独立公开仓库，也作为平台的 `management-sdk/` 子模块使用。独立使用时：

```bash
git clone https://github.com/BintaoYu/management-sdk.git
cd management-sdk
python -m pip install .
```

整个 `management-sdk` 目录可复制给第三方，无需仓库的其他目录、配置或本地动态库。

```bash
python -m venv .venv
. .venv/bin/activate  # Windows：.venv\Scripts\activate
python -m pip install ./management-sdk
# 或安装收到的 wheel
python -m pip install management_sdk-0.2.0-py3-none-any.whl
```

```python
from management_sdk import ManagementClient

client = ManagementClient()  # Apps 默认 http://127.0.0.1:8080，timeout=10 秒
print(client.list_instances())
print(client.get_connections())
```

实际地址及超时可指定：`ManagementClient("http://apps.example:8080", timeout=5)`。
由平台管理员先启动 Apps/Runtime 并部署、运行应用；SDK 不负责工程构建或部署。
Apps 当前约定同一时间只有一个应用运行，没有运行应用返回 MG_NO_CURRENT；
多个候选返回 MG_MULTIPLE_CURRENT，不挑选任意工程。前端正在编辑的工程不决定操作目标。

SDK 内部获取 Apps 的 CSRF token 和不透明的运行上下文；变更使用现有 Host/Origin/CSRF
访问控制。Apps 仍使用现有 RuntimeClient 的 Softbus 传输执行管理命令。
默认 HTTP 是明文，远程使用管理员提供的受保护入口。客户端不使用环境 HTTP 代理，
不跟随重定向，实例供顺序调用。

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
event_ports 与 data_ports。实际引用以 name/端口查询结果为准，如 `app.Source.IN`。
库定义描述可用参数；旧程序若未编译对应读写回调，实际参数访问会返回明确的 Runtime 错误，
须由管理员用匹配原生 SDK 重建。

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

运行应用、激活或 Runtime/Apps 会话变化时，返回 MG_SESSION_CHANGED、RD017 或 csrf_rejected。
旧客户端不会自动刷新后重放命令；请新建 ManagementClient、重新查询实例，再明确决定新操作。
客户端超时不取消已接纳工作，**不自动重发连接变更、参数写入或事件**。异常的 request_id 可与
get_status 中有界 commands / 事件接纳记录关联；记录缺失不能推断成功或失败。

0.2 的 ManagementClient 仅接受 Apps 协议；0.1 的 Runtime 直连接口已移除。不要把
base_url 指向 Runtime 的 18080 端口。

## 示例、测试与打包

```bash
# 安装后直接运行，不设置 PYTHONPATH
python management-sdk/examples/manage.py --types
python management-sdk/examples/manage.py
python management-sdk/examples/manage.py --write app.Source.IN --value 42
python management-sdk/examples/manage.py --trigger app.Source.REQ

python -m unittest discover -s management-sdk/tests -v
python -m pip install build
python -m build management-sdk
```

离线测试只启动 loopback 模拟 Apps，不访问实际服务。wheel 包含可导入的 management_sdk；
源码包同时携带 README、示例和测试。独立安装与纯软件实机验证见[验证说明](docs/verification.md)。
