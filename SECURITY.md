# Security / 安全说明

Codex Harbor is a local, single-user development tool. Its API can submit coding
tasks and run configured acceptance commands with the local user's permissions.
The daemon enforces loopback binding (`127.0.0.1`, `localhost`, or `::1`). HTTP
requests require a local Host header, and browser mutations must originate from
the same origin. This protects local controls from cross-site form requests and
DNS rebinding; it does not authenticate other local processes.
The API has no authentication or multi-user
authorization; do not expose the daemon directly to a public network.

Codex Harbor 面向本机单用户开发。API 可以提交开发任务，并以本机用户权限执行
配置的验收命令。daemon 强制仅监听回环地址，HTTP 请求校验本机 Host，浏览器修改
请求必须同源，以防止跨站表单控制和 DNS 重绑定。本机其他进程仍被视为可信；当前没有身份认证和多用户
权限隔离，不适合将 daemon 直接暴露到公网。公开 GitHub 源码不等于部署公网服务。

Only import task definitions and acceptance commands that you trust. Keep local
databases, credentials, recovery envelopes and conversation transcripts out of
Git. Review patches and generated commands before applying them to sensitive projects.

只导入可信的任务定义和验收命令。数据库、凭据、恢复文件、对话记录不应提交到 Git。
在敏感项目中使用前，请检查生成的代码和命令。

For vulnerabilities, use GitHub private vulnerability reporting if available.
Do not put credentials or private conversation content in public issues. General
bugs can be reported with sanitized reproduction steps, OS/Python versions and
the relevant Harbor commit.

发现漏洞时优先使用 GitHub 私密漏洞报告入口（如已启用）。公开 Issue 中不要包含
凭据或私有对话内容；普通问题请提供脱敏后的复现步骤、系统/Python 版本及提交号。
