# Recovery blocked by an existing writer

The live scheduled task triggered at its recorded boundary. At inspection it had
482 failed `thread/resume` attempts, all reporting `already has an active writer`,
with no recorded turn IDs. There were no Reserve checkpoint attempts, and weekly
ping was disabled. These records do not attribute the account's 13% weekly usage
to the scheduled task. Account quota snapshots are not per-task billing records.

The prior worker retried writer contention every minute indefinitely. Consecutive
writer errors now wait 1, 2, 4, 8, 16, then at most 30 minutes. History survives
worker restarts. Contention still preserves the original thread and does not
consume the business failure budget. Another error breaks the contention streak.

After a runtime failure, the worker now atomically refreshes `recovery.json` with
the persisted task state, current attempt, original thread, main model and bounded
error text. Previously the file could keep saying `starting turn` without a reason.
If the file cannot be updated, the database retains the task and error, and an
explicit checkpoint-write failure event is recorded.

Quota failures continue to enter `WAIT_QUOTA` through code. A registered watch can
use one opt-in Reserve summary turn when the original turn fails for quota and no
recovery task exists. Existing tasks use their durable context without another
Reserve call. Reserve also requires the original writer lock; it cannot force a
handoff. No native Reserve inference was requested during this investigation.

Validation: 34 focused worker/recovery/Reserve tests passed, including repeated
writer contention through the delay cap, no model turn or fork during contention,
and persisted quota-stop metadata. Ruff and compilation passed. Actual ownership
handoff from the desktop and live Reserve use remain unverified.
