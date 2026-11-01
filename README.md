# Management SDK

Management SDK 是同步 Python 客户端，通过 Apps HTTP 查询和管理当前运行的工业应用。
你只需要实例、类型与端口名称；Apps 会解析应用、部署和修订身份。

要求 Python 3.9+，运行时仅依赖标准库。本仓库可以独立使用，无需复制平台源码或原生动态库。

## 安装

本文的多 Runtime 与功能块生命周期接口需要 0.3.0。以下命令获取对应开发分支；也可使用包含该版本的检出或分发包。在 SDK 根目录执行安装：

```bash
git clone --branch feat/iec61499-multidevice https://github.com/BintaoYu/management-sdk.git
cd management-sdk
python -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Windows 使用 `.venv\Scripts\activate` 激活环境。也可以在已有平台根目录执行
`python -m pip install ./management-sdk`，或安装收到的 wheel 文件。

## 第一次调用

管理员需先启动 Apps / Runtime 并部署、激活应用。SDK 默认连接 Apps 的 `8080` 端口：

```python
from management_sdk import ManagementClient

client = ManagementClient("http://127.0.0.1:8080", timeout=10)
print(client.list_instances())
print(client.get_connections())
print(client.get_status())
```

0.4.0起不再提供API凭据参数。本机回环调用无需认证材料，按Apps服务所属管理员访问；SDK只保留Runtime/激活上下文校验和请求关联，未知修改不重发。远端浏览器仍按自己的登录会话访问。

目标是所选 Runtime 实际激活的唯一应用；前端正在编辑的工程不会改变目标。
没有运行应用返回 `MG_NO_CURRENT`，有多个候选返回 `MG_MULTIPLE_CURRENT`。
类型库查询在无运行应用时仍可使用。

多个设备时，先用 `client.list_runtimes()` 查看 Apps 已配置的静态目录，再显式选择目标：

```python
client = ManagementClient("http://127.0.0.1:8080", runtime_id="right")
print(client.list_instances())
```

所选 Runtime 上仍需有唯一运行应用。切换设备时创建新客户端，重新获取会话上下文；SDK 不直接连接 Runtime 数据面。

## 参数与事件

以下引用应替换为 `list_instances()` 查询到的实际实例和端口：

```python
value = client.read_parameter("app.Source.IN")
client.write_parameter("app.Source.IN", 42)
receipt = client.trigger_event("app.Source.REQ")
print(receipt["accepted"], receipt["request_id"])
```

参数赋值不会触发事件。事件回执表示接纳，handler 完成及下游效果需要另行读回。
连接增删、类型查询、参数类型和执行确认方式见[完整使用说明](docs/usage.md)。

## 处理错误

```python
from management_sdk import ManagementError

try:
    client.trigger_event("app.Source.REQ")
except ManagementError as error:
    print(error.code, error.request_id, error.details)
    if error.outcome_unknown:
        print("先查询状态，确认原操作结果")
```

修改操作超时不会自动取消或重发。会话、激活或当前应用变化后，新建客户端并重新查询，再明确决定新操作。
完整错误字段和恢复方式见[错误与会话](docs/usage.md#错误会话变化与超时)。

## 示例与验证

以下命令在 SDK 根目录执行，安装后无需设置 `PYTHONPATH`：

```bash
python examples/manage.py --types
python examples/manage.py
python examples/manage.py --write app.Source.IN --value 42
python examples/manage.py --trigger app.Source.REQ
python -m unittest discover -s tests -v
```

测试使用 loopback 模拟 Apps。打包与实机验证记录见[验证说明](docs/verification.md)，
公共调用与错误语义见[使用说明](docs/usage.md)。
