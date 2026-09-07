---
name: harbor-auto-resume
description: 当用户说“自动恢复当前任务”“额度恢复后继续当前对话”或要求在 5h 额度耗尽后自动续接时，向本机 Codex Harbor 登记原对话恢复保护。保留原 Thread ID、原工作区和主模型；不用于普通新建任务。
---

# 自动恢复当前任务

用户提出自动恢复即授权登记本次任务的保护。立即登记，不要等到主模型已经无法调用工具。Harbor 在后台监测 5h 用量，默认达到 95% 时创建 task；只有确认原轮次因额度失败，且额度恢复后才运行。登记和创建 task 都是本地数据库操作，不需要模型推理，也不会消耗 Luna 储备额度。

使用本技能目录下的 `scripts/auto_resume.py`。Python 可用 `python`、`py`，或 Harbor 仓库内的 `uv run python`。从当前上下文取得主模型和 reasoning effort；写入 UTF-8 JSON 文件：

```json
{
  "title": "恢复当前任务",
  "prompt": "继续本对话尚未完成的目标。先核对最新消息、工作区和已完成结果，再完成剩余工作；遵守本对话的约束和授权范围，不重复已完成操作。",
  "model": "实际主模型名称",
  "reasoning_effort": "实际推理等级",
  "threshold": 95,
  "acceptance_commands": []
}
```

在 prompt 中补充本次任务的具体目标、剩余工作和验收条件，不复制整段对话。不要臆造验收成功。运行：

```text
python <本技能目录>/scripts/auto_resume.py arm --file <UTF-8-JSON文件>
python <本技能目录>/scripts/auto_resume.py list
```

脚本优先读取 `CODEX_THREAD_ID`，其次 `CODEX_SESSION_ID`；没有这些值时，仅使用已确认的原 Thread ID 作为 `--thread-id`。不能按标题、当前目录或最新一条记录猜测对话。API 会只读核实对话和 Git 工作区。相同对话重复登记返回同一个有效保护记录。

登记失败要报告具体原因，修复后重试；不能把失败说成已启用。若本机 Harbor 未运行，用户的自动恢复请求允许启动已安装的 Harbor 服务；核实实际安装路径，并在 Windows 隐藏窗口启动。不要安装未知程序或覆盖既有配置。回读列表，核实保护 ID、Thread ID、主模型和状态。

额度已经耗尽时，仍优先登记。新版 Codex 的 **Luna Reserve** 使用独立模型标识 `gpt-reserve`，不是普通的 `gpt-5.6-luna`。本机可通过 `model/list` 的 `includeHidden: true` 验证它支持 `xhigh`；储备可用性来自 `account/rateLimits/read` 中 `limitName: gpt-reserve` 的独立 bucket。

用户要求允许储备兜底时，启用并回读持久设置：

```text
python <本技能目录>/scripts/auto_resume.py settings --allow-luna-reserve true
python <本技能目录>/scripts/auto_resume.py settings
```

`allow_luna_reserve` 开启后，若原轮次已经因 5h 额度失败且尚无恢复 task，Harbor 在**同一原对话**最多执行一轮 `gpt-reserve / xhigh`，只提取续接摘要并补建 task。已有 task 时不消耗储备。储备不可用、被桌面写入锁占用或补写失败时，仍用已登记信息直接创建 task，不另开对话。每次保护最多尝试一轮储备，不能无限重试消耗额度。恢复 task 保存原主模型和推理等级，等主额度恢复后才执行业务工作。

不要把普通 Luna 的调用成功说成已使用储备。不要修改服务端功能开关、充值、购买重置或扩大账户额度。用户的授权是使用已有的 Luna Reserve。未要求储备兜底时保留现有设置；可用上述 settings 命令设为 false 禁用。

原对话正常完成会自动解除保护；登记后需要取消时运行：

```text
python <本技能目录>/scripts/auto_resume.py cancel <保护ID>
```

Harbor 执行期间会临时持有对话写入权，结束、失败或等待额度时关闭 worker 的 App Server。若桌面端仍持有写入权，Harbor 等待并重试相同 Thread ID，不会强制夺取或改用新对话。保护依赖本机 Harbor 运行；本机关闭期间不会执行，重启服务后继续检查已持久化的登记。
