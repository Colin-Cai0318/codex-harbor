# Codex Harbor 桌面版

桌面版使用 PySide6 / Qt WebEngine，在独立窗口中提供任务中心、恢复保护、工作空间、运行记录和偏好设置。继续使用原有本机 API 和 SQLite 数据，不迁移任务或对话。原创 SVG 标志采用船锚造型：米白锚身、松绿底色与浅鼠尾草绿描边；固定配色在浅色和深色背景中保持一致，避免依赖系统主题导致托盘图标变色或不可见。Windows ICO 由该矢量源生成，包含 16–256 像素的七种尺寸。

## 运行

Windows 构建产物位于 `dist/CodexHarbor/CodexHarbor.exe`。双击即可启动，不需要安装 Python；整个 `CodexHarbor` 目录必须一同保留。执行任务仍需要本机安装并登录 Codex CLI，以及 Git。

源码启动：

```powershell
uv sync --extra desktop --extra dev
uv run --extra desktop harbor-desktop
```

指定配置或直接收起到托盘：

```powershell
uv run --extra desktop harbor-desktop --config "E:\my harbor\config.toml" --background
```

已有服务使用该虚拟环境时，Windows 可能拒绝替换正在运行的 `harbor.exe`。可另建环境，无需中断已有任务：

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.harbor/desktop-venv'
uv sync --extra desktop --extra dev --extra bundle
uv run --extra desktop harbor-desktop
```

## 操作

- **任务中心**：创建或续接 Codex 项目对话，查看状态、模型、验收和事件，重试或取消任务；`Ctrl+K` 聚焦任务搜索。
- **恢复保护**：查看已登记保护、取消尚未交接的保护，或填写原 Thread ID、模型、推理等级和目标来登记。
- **工作空间**：查看和登记 Git 仓库。Codex 项目选择继续使用 Codex 本身的 Project 数据。
- **运行记录**：展开查看最近 100 条事件，手动刷新获取新记录。
- **偏好设置**：设置最大并行数、周额度冻结、周重置消息和储备摘要；右上角切换中英文和明暗主题。
- **后台运行**：关闭窗口后隐藏到系统托盘，调度继续。单击托盘图标重新显示窗口，右键可暂停、恢复、冻结、打开日志所在数据目录、设置 Windows 登录后启动或退出。
- **单实例**：同一数据目录再次启动时唤起已有窗口，不再启动一份桌面调度器。
- **退出**：本应用启动的服务会保存状态并停止；独立启动的已有服务不受影响。停止服务前显示确认，以免误中断运行任务。

没有系统托盘的平台会保留普通窗口行为，关闭时进入退出流程。自动启动开关仅支持 Windows 当前用户，不需要管理员权限。默认不开启；自动启动只在用户登录后发生。

桌面程序会识别并连接已有 Harbor 服务，包括尚未提供 health 接口的兼容版本；界面资源随桌面应用加载。若端口由其他程序占用，显示连接问题，不覆盖该程序。已有后端缺少新 API 时，相应页面会明确显示错误。

配置和日志位于 `%LOCALAPPDATA%\CodexHarbor`，或 `HARBOR_DATA_DIR` / 配置指定的数据目录。无控制台启动时，输出写入 `logs/desktop.log`。服务启动失败时可查看错误、打开日志目录并重新连接。未改变现有 CLI、YAML 任务组和插件入口。

## 构建

```powershell
uv sync --extra desktop --extra bundle --extra dev
uv run --extra desktop --extra bundle python tools/build_desktop.py
```

产物是包含 Python 和 Qt 运行库的 Windows 目录式应用，体积包含浏览器内核。原始图标为 `src/codex_harbor/assets/harbor.svg`；构建生成 `build/desktop/harbor.ico`。目前没有签名安装器、自动更新服务或跨平台发布包。

## 验证

```powershell
uv run --extra dev pytest -q
uv run --extra desktop python tools/verify_desktop.py
uv run --extra desktop python tools/verify_packaged_desktop.py
```

第二条命令使用独立临时数据库、模拟 API 和真实 Qt/WebEngine，验证五个页面、无横向溢出、托盘隐藏恢复和设置页重新进入，并生成 `.harbor/desktop-qa/` 截图。它不执行 Codex 模型回合，不证明真实额度重置、Windows 重启恢复或长期运行结果。原生窗口代码由该独立 GUI 测试覆盖，不计入无图形环境的 pytest 行覆盖率。

第三条命令运行实际 EXE，在临时 API 上验证打包界面、兼容旧服务和本机 API 写入。测试仅为该进程开启回环 DevTools 端口，并在结束时停止测试进程。正常启动不会启用该端口。

2026-09-10 本机验证：167 项全量测试通过，包含分支的总体覆盖率为 86.00%，其中包括 Windows 自启动注册表模拟测试。真实 GUI 验证包含五个页面、托盘隐藏恢复、设置导航、设置持久化和单实例唤起；打包 EXE 的三项检查通过。船锚图标已检查浅色、深色背景与 16–48 像素显示效果；运行 `python tools/render_icon_preview.py` 可重新生成 README 预览。测试使用独立数据，不触发真实模型任务。

构建脚本排除了误从 Poppler 等 PATH 目录收集的 `icuuc.dll`，让 Qt 使用 Windows 系统 ICU；本机曾复现同名 DLL 导致 QtCore 导入失败，修复后 EXE 验证通过。启动前的异常写入 `%LOCALAPPDATA%\CodexHarbor\logs\desktop-startup.log`。

交互参考：[CC Switch 托盘与界面说明](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/1-getting-started/1.3-interface.md)。桌面生命周期使用 [Qt QSystemTrayIcon](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html)，本地页面使用 [Qt QWebEngineView](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineWidgets/QWebEngineView.html)。
