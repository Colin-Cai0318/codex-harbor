# Security / 安全说明

Codex Harbor is a local, single-user development tool. Its API can submit coding
tasks and run configured acceptance commands with the local user's permissions.
Keep the default `127.0.0.1` binding. The API has no authentication or multi-user
authorization; do not expose the daemon directly to a public network.

Codex Harbor 面向本机单用户开发。API 可以提交开发任务，并以本机用户权限执行
配置的验收命令。请保留默认的 `127.0.0.1` 监听地址；当前没有身份认证和多用户
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
