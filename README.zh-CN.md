<div align="center">

# ⚓ Codex Harbor（代码港）

### 面向 Codex 的持久化任务编排器

将 Codex 会话变成可持久化、可调度的开发任务，并提供 Git worktree 隔离、
配额感知执行以及跨进程恢复能力。

[![CI](https://github.com/Colin-Cai0318/codex-harbor/actions/workflows/ci.yml/badge.svg)](https://github.com/Colin-Cai0318/codex-harbor/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-v0.1%20MVP-orange)](#项目状态)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20WSL-555)](#环境要求)

[English](README.md) · **简体中文**

</div>

---

Codex Harbor 是构建在 Codex App Server 之上的本地优先控制平面。它使用
SQLite 保存调度状态、使用 Git worktree 隔离代码改动，并通过恢复信封确保
任务身份不依赖某个终端、Worker、Codex 进程或 Desktop 侧边栏。

> [!IMPORTANT]
> Codex Harbor 当前为 MVP。Windows Native 仍处于 Beta 阶段；升级 Codex CLI
> 后，应重新验证真实配额行为。

## 目录

- [为什么需要 Codex Harbor？](#为什么需要-codex-harbor)
- [系统架构](#系统架构)
- [核心能力](#核心能力)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [YAML 任务文件](#yaml-任务文件)
- [CLI 命令参考](#cli-命令参考)
- [Codex 插件](#codex-插件)
- [持久化与恢复](#持久化与恢复)
- [开发与验证](#开发与验证)
- [安全边界](#安全边界)
- [项目状态](#项目状态)

## 为什么需要 Codex Harbor？

普通的交互式 Codex 会话依赖正在运行的客户端。Harbor 为长时间、多仓库开发
任务提供了独立且持久的生命周期：

| 需求 | Harbor 的处理方式 |
|---|---|
| 跨进程恢复 | 在 SQLite/WAL 中保存任务、Attempt、Codex Thread、Worker、配额和事件 |
| 安全并行 | 事务式领取任务，每个任务使用独立 Git worktree |
| 保证执行顺序 | 支持依赖关系、优先级 + FIFO 以及互斥组 |
| 应对配额暂停 | 任务状态机与资源池状态机分离，支持等待、排空、冻结和恢复 |
| 明确 Agent 配置 | 动态校验模型与推理等级能力，绝不静默降级 |
| 验证完成质量 | 执行验收命令，并可将失败结果交给后续 Turn 继续修复 |

## 系统架构

```mermaid
flowchart LR
    U[开发者 / Codex] --> CLI[CLI]
    U --> UI[本地 Dashboard]
    U --> PL[Codex 插件]
    UI --> API[回环 API<br/>127.0.0.1:8765]
    PL --> API
    CLI --> D[Harbor Daemon]
    API --> D
    D --> S[调度器 + 资源池控制器]
    S --> W[Worker 池]
    W --> AS[Codex App Server]
    W --> WT[每任务独立 Git worktree]
    D --> DB[(SQLite / WAL)]
    W --> DB
```

Daemon 统一管理一个 App Server 进程。模型和推理等级配置始终归属于具体任务，
不会通过 Worker 在任务之间泄漏全局 Agent 状态。

## 核心能力

### 持久化调度

- 持久化保存仓库、任务、依赖、Attempt、Thread、Worker、配额、资源池和事件。
- 通过事务领取任务，并按优先级/FIFO 排序。
- 支持依赖门禁、互斥组、并行 Worker、有限重试和验收失败后的后续 Turn。
- 提供 `WAIT_QUOTA`、`RETRY_WAIT`、`BLOCKED` 等任务状态，以及
  `DRAINING`、`FROZEN` 等独立资源池状态。

### 原生 Codex 集成

- 实现 App Server 初始化以及持久化 Thread/Turn 操作。
- 支持创建、读取、恢复和 Fork Codex Thread，不依赖内部 rollout JSONL 格式。
- 动态读取模型列表并验证所选推理等级是否受支持。
- 通过当前 App Server 协议读取结构化账户配额。

### 隔离、恢复与可观测性

- 在 Harbor 管理的 Git worktree 中创建 `harbor/<task-id>` 分支。
- 支持本地 Linux、Windows Native 和 WSL 执行后端。
- 保存恢复信封，并根据心跳识别失联 Worker。
- 持久化任务历史和命令输出前，对 Authorization、API Key、Cookie 和密码脱敏。
- 提供仅监听回环地址的 FastAPI 服务，以及支持白天/黑夜主题的卡片式生命周期
  Dashboard。

## 环境要求

- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)
- Git
- 已安装并完成登录的 Codex CLI

Harbor 当前面向 Windows Native、Linux Native 和 WSL2。Windows Native 仍为
Beta；完整验证边界请参阅[项目状态](#项目状态)。

## 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/Colin-Cai0318/codex-harbor.git
cd codex-harbor
uv sync --extra dev
```

### 2. 初始化并检查运行环境

```bash
uv run harbor init
uv run harbor doctor
```

### 3. 注册仓库并创建任务

Harbor 只会操作显式注册过的 Git 仓库。

```powershell
uv run harbor repo add E:\path\to\project

uv run harbor task add `
  --repo E:\path\to\project `
  --title "新增解析器" `
  --prompt "实现解析器并保持现有行为不变" `
  --reasoning high `
  --accept "pytest -q"
```

### 4. 启动 Harbor

```bash
uv run harbor daemon
```

浏览器打开 <http://127.0.0.1:8765> 使用 Dashboard；也可以在另一个终端查看
同一份持久化状态：

```bash
uv run harbor ps
uv run harbor task show T001
uv run harbor history T001
```

## 配置说明

初始化配置结构可参考 [`config.example.toml`](config.example.toml)。关键默认值
有意保持保守：

| 配置项 | 默认值 | 用途 |
|---|---:|---|
| `harbor.bind` | `127.0.0.1` | Dashboard 与 API 仅监听本机回环地址 |
| `harbor.port` | `8765` | 本地 Dashboard/API 端口 |
| `scheduler.max_workers` | `3` | 最大并行 Worker 数量 |
| `quota.provider` | `codex` | 读取 Codex 账户的结构化配额 |
| `quota.freeze_on_weekly_reset` | `true` | 周配额重置时先排空既有任务再冻结资源池 |
| `codex.approval_policy` | `never` | 防止无人值守 Worker 卡在审批提示上 |
| `codex.sandbox` | `workspace-write` | 将 Agent 写入限制在任务工作区 |

测试另一套 Harbor 实例时，可使用独立数据目录：

```powershell
$env:HARBOR_DATA_DIR = 'D:\harbor-data'
uv run harbor init
```

## YAML 任务文件

任务既可以逐个创建，也可以从 YAML 导入：

```bash
uv run harbor task import docs/task-example.yaml
```

```yaml
id: T001
title: 新增 watchdog 解析器
repository:
  path: /absolute/path/to/repository
execution:
  backend: local
agent:
  model: null
  reasoning_effort: high
priority: 50
depends_on: []
exclusive_group: watchdog-parser
prompt: 实现解析器并保持现有行为不变。
acceptance:
  commands:
    - pytest tests/watchdog -q
max_attempts: 5
```

优先级数字越小越先执行；相同优先级按 FIFO 排序。

## CLI 命令参考

| 命令 | 用途 |
|---|---|
| `harbor init` | 创建数据目录、数据库和默认配置 |
| `harbor repo add\|list` | 注册或列出可用 Git 仓库 |
| `harbor task add\|import\|list\|show` | 创建和查看任务 |
| `harbor task config` | 调整任务的模型或推理等级 |
| `harbor task retry\|cancel\|cleanup` | 管理任务生命周期和 Harbor worktree |
| `harbor ps` | 查看资源池、Worker 和活动任务 |
| `harbor quota` | 查看最近一次持久化的配额窗口 |
| `harbor pause\|freeze\|resume` | 控制资源池任务准入 |
| `harbor run` | 运行调度器，直到当前工作稳定 |
| `harbor daemon` | 持续运行调度器与本地 Dashboard |
| `harbor logs TASK` | 查看持久化任务输出 |
| `harbor history TASK` | 查看任务事件时间线 |
| `harbor doctor` | 检查 Python、Git、SQLite、Codex、模型、配额和执行后端 |

使用 `uv run harbor <command> --help` 查看完整参数。

## Codex 插件

仓库在 [`integrations/plugins/codex-harbor`](integrations/plugins/codex-harbor)
中提供了已验证的开发版插件。其 `harbor-tasks` Skill 允许 Codex 通过本机回环
API 查看和管理任务池，并与 CLI、Dashboard 共享同一调度器和安全边界。

插件同时提供 [API 参考](integrations/plugins/codex-harbor/skills/harbor-tasks/references/api.md)
和[无第三方依赖的辅助脚本](integrations/plugins/codex-harbor/skills/harbor-tasks/scripts/harbor_api.py)。

## 持久化与恢复

Harbor 将 SQLite 作为控制平面的事实来源，将 Codex Thread 作为持久化执行上下文。
Phase 0 验证程序会启动 App Server 并完成一个 Turn，停止该进程，再用另一个进程
恢复同一 Thread、读取历史记录并完成第二个 Turn：

```bash
uv run python tools/app_server_poc.py --workspace .
```

本机验证数据写入 `.codex-harbor-poc/state.json`，并由 Git 忽略。

## 开发与验证

```bash
uv run pytest -q
uv run pytest --cov=codex_harbor --cov-report=term-missing
uv run python -m compileall -q src tools tests
uv run harbor doctor
```

CI 矩阵覆盖 Ubuntu、Windows 与 Python 3.11、3.13。确定性测试使用 Fake Runtime
和 Fake Quota Provider；App Server 恢复程序是真实集成验证门槛。

- [实现映射](docs/IMPLEMENTATION.md)
- [验证记录](docs/VALIDATION.md)
- [任务示例](docs/task-example.yaml)

## 安全边界

> [!WARNING]
> Harbor 不会自动合并任务分支，也不会自动删除成功任务的 worktree。清理始终需要
> 显式执行。

- 控制平面的事实来源是 SQLite，而不是聊天历史。
- 任务状态与资源池状态相互独立。
- 配额耗尽属于等待状态，不计为失败 Attempt。
- 模型能力不受支持时会阻塞任务，不会偷偷更换模型或推理等级。
- Codex 身份认证仍由 Codex 管理；Harbor 不保存其凭据。
- `task cleanup` 会校验已注册 Git Root，只删除指定的 Harbor worktree，并保留分支。
- API 默认仅监听回环地址，绝不会默认绑定 `0.0.0.0`。

## 项目状态

Codex Harbor v0.1 是可运行的 MVP。自动化测试、真实双进程 App Server 恢复、
真实隔离 worktree 任务以及回环 API 已在 Windows Native 上验证通过。

以下项目仍属于发布资格验证范围，当前不宣称已完整验证：真实 5 小时/周配额耗尽
周期、破坏性进程终止与宿主机重启、Linux/WSL 长时间运行，以及 Windows 服务
打包。精确证据请参阅[验证记录](docs/VALIDATION.md)。

## 许可证

本项目基于 [Apache License 2.0](LICENSE) 发布。
