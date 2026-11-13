# SDK 验证

当前源码为 0.5.0，不提供 API 凭据参数和认证头；运行上下文、未知结果与不重试约束保留。提供固定实例批量拓扑规划、单 Runtime 提交，以及经 Apps 协调已部署 SYS 的跨 Runtime 提交和显式恢复。

| 项目 | 最近验证 |
| --- | --- |
| 日期与环境 | 2026-11-08，Linux / Python 3.12，当前 wheel 安装到仓库外临时虚拟环境 |
| 协议测试 | 2026-11-09 复核，24 项通过，包含批量候选身份、只读规划超时、未知写入与不可逆恢复拒绝 |
| wheel SHA-256 | `c31a877cd8547e123ac5be29d8c99fec348bbab1adaa5dc5326c086ad4e3e92f` |
| Apps HTTP 集成 | 已安装 SDK 经真实 Apps/Runtime 完成生成工程的 Data 驱动替换、Event/Data 批量断开和恢复，revision 为 2/3/4；C++/Python 进程身份及状态保持，最终进程释放 |
| 跨 Runtime HTTP 消费 | 同一已安装 0.5.0 包经 Apps HTTP 完成 Dev C++ 和 Release Python Worker 双 Runtime 的 TCP→UDP 改线、扇出、安装回执丢失后的撤销及提交后继续；两端 fence epoch 不同，固定业务实例、Worker PID/出生身份和状态保持，并验证全部远端组移除/重建；typed cleanup 后在测试 Runtime 退出前确认 Worker 释放。该包的 Python 文件与当前源码摘要一致 |
| 发布与系统安装 | wheel 仅在本地验证，未上传包索引；系统原有 Management SDK 包未更新 |

## 验证边界

协议测试通过 loopback 模拟服务检查客户端协议与独立分发。另一次集成使用私有 mount/IPC/network namespace、模拟 OCI/cgroup 和真实生成节点/Python Worker，经公共 Apps HTTP 调用；客户端包不导入 Apps/Runtime 私有模块。集成所用 Python 文件与最终 wheel 的文件摘要一致。

集成覆盖单端成功提交和状态读回，以及同 ABI Event/WITH 的双 Runtime 协调与故障恢复；SDK 0.22 / Release 的 4KiB Python Worker 工程也经安装后的独立客户端验证五批事务、字节读回和清理。使用隔离 namespace、真实 socket 与模拟 OCI/cgroup；不是日常已安装服务的跨端业务、物理多设备、第三设备独立 Data、现场设备动作或性能验收。未知结果不自动重发；公共接口用法见[使用说明](usage.md)。

使用前核对实际导入版本，确认与上述验证记录对应。
