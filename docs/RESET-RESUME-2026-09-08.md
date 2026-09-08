# Explicit reset recovery

The previous recovery watch interpreted a completed acknowledgement turn as
completed work. It cancelled a requested reset recovery before it ran. It also
accepted the temporary Reserve model as the recovery task's business model.

`POST /api/recovery-watches` now supports two distinct triggers:

- `on_failure` (existing default): pre-create at the usage threshold, release only
  after a quota failure, and cancel on normal completion.
- `after_reset`: immediately persist one task with the verified `resume_after`
  timestamp. Completed acknowledgement turns do not cancel it. The scheduler
  requires the recorded boundary to pass, fresh available primary quota, no
  reported unavailable window, and a terminal latest conversation turn before
  handing it off. Pool pause/freeze and same-thread writer contention still apply.

`resume_after` requires a timezone. It records the observed boundary rather than
being advanced to the provider's next window after a restart. Cancellation is
durable, registration is idempotent, and changing trigger mode requires explicit
cancellation of the existing watch. Old databases migrate to `on_failure`.

Recovery registration rejects `gpt-reserve`: Reserve remains a bounded checkpoint
helper; the task uses the user's confirmed main model and effort. Hidden model
loading remains available to internal runtime consumers.

Tests cover acknowledgement completion, restart, an active desktop turn, missing
quota, unavailable weekly quota, a future boundary, repeated scheduler ticks,
same-thread/main-model preservation, explicit cancellation and API validation.
This establishes the tested scheduling contract, not a guarantee about server
quota accounting or complete production coverage. The prior 85.95% result was
overall coverage with branch measurement enabled, not branch-only coverage.

Local validation: 159 tests passed; branch-aware overall coverage 85.84%; Ruff,
compileall, source/wheel builds and skill validation passed. The existing local
database was backed up and passed integrity checking before migration. The live
API accepted and persisted an `after_reset` watch with the original conversation
and main model. Actual delayed execution is still pending; registration alone is
not evidence of successful automatic continuation.
