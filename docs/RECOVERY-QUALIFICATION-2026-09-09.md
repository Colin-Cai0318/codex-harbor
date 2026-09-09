# Recovery qualification

## Confirmed locally

- The PC booted at 08:22 Hong Kong time on September 9. Harbor was absent and
  port 8765 refused connections. Its durable T008 task remained in RETRY_WAIT.
- Installed the current user's `CodexHarbor-Daemon` Windows task: interactive
  logon, limited privileges, hidden process, no execution time limit. Its wrapper
  checks daemon exit codes and allows three restarts one minute apart on failure.
  Starting it loads the existing database.
  This does not run before login or while the computer is off.
- A live two-process test against an idle test conversation rejected the second
  writer even after that second connection requested unsubscribe (`notLoaded`).
  After the owner exited, a successor resumed the identical Thread ID. Full turn
  history and cwd were unchanged. No model turn was started.
- Reproduce using `uv run python tools/writer_handoff_probe.py --thread-id <idle-test-thread> --output .harbor/handoff.json`.
  Use a disposable idle test thread; the probe temporarily loads it.

## Linux lab diagnosis and fix

The completed legacy T006 had no origin_thread_id or conversation_mode. Its new
root thread therefore did not inherit the original Linux lab conversation.
Completed history is retained; changing an ID cannot combine those histories.

The original conversation also started in a parent directory above the Git
repository. Recovery registration previously required that cwd itself be inside
Git. The recovery API now accepts an explicit `repository` within that workspace.
It validates the path relationship, keeps conversation_cwd and origin_thread_id,
and uses the selected Git root for acceptance checks and checkpoints. Worker
resume and turn calls still use the original conversation cwd. Unrelated
repositories are rejected. Existing clients that omit repository keep their
previous behavior.

## Remaining external conditions

Desktop-owned writer handoff is not automatic: the owning client must release
the conversation, such as by exiting after its work finishes. Harbor cannot
unsubscribe another connection. T008 is still bound to the original conversation
and waits for that release. The dashboard now explains this and shows next retry.
See [official App Server documentation](https://learn.chatgpt.com/docs/app-server#unsubscribe-from-a-loaded-thread).

The live account snapshot had primary quota available (17% used), so a real
primary-exhaustion to native Reserve to primary-reset sequence was not exercised.
No quota was deliberately exhausted, no reset credit used, and no Reserve turn
sent in this qualification. Fault-injection tests cover quota detection,
single-use Reserve failure/success, persistence, and original model/thread
restoration; they do not establish the real service's exhausted-quota behavior.

Windows task registration and manual launch are verified. The initial Task
Scheduler failure-restart setting did not restart the manually launched task in
the crash test, so retries moved into the wrapper. Killing the idle daemon then
produced a logged nonzero exit, a new listener process after the one-minute delay,
and the unchanged T008 thread/attempt/status from SQLite. An actual subsequent
reboot/logon remains to be observed. The wrapper stops retrying after three
failures; logs remain available for diagnosing a persistent startup problem.

Validation: the full 161-test Ubuntu/Windows, Python 3.11/3.13 CI matrix passed
for the API/worker/dashboard changes. The wrapper revision was verified by the
live process-crash test above. Ruff and compilation also passed.
