# Case 0003 — UL7 auto root / OS identity resolution hardening

Date: 2026-08-18 Asia/Taipei

This change removes avoidable manual environment setup from the first REAL UL7 run without introducing guessed paths or guessed OS identities.

## OpenWorker node inventory

`GET /v1/node/status` now reports `inventory.roots` for configured local authorities:

- `OPENWORKER_ROOT`
- `GO_TOOL_ROOT`
- `TERRAIN_ROOT`
- `SCENEX_ROOT`
- `ENGINEERING_OS_ROOT`
- `OPENWORKER_REVIEW_DRIVE_ROOT`

A root is `available=true` only when the configured path exists and is a directory. The controller must not invent a checkout path when inventory does not provide one.

Relevant commits:

- `ec6b73684761602408ab22d866a63c4603591a54` — initial validated authority roots
- `953bd5857fa1d86621f063cf28313469843ff31d` — inventory root tests
- `a0bcc556962c3bc30f1192231a089ee40f7c629a` — Drive review sync root added

## Case 0003 auto continuation wrapper

New canonical convenience entrypoint:

`scripts/case0003_local_continue_auto.ps1`

Resolution precedence for code/runtime roots is:

```text
explicit parameter
→ OpenWorker node inventory
→ process environment
→ fail closed
```

The wrapper does not duplicate physical gates. After resolving authorities it delegates to `case0003_local_continue.ps1`, so the established v8 stage gates and duplicate suppression remain authoritative.

Relevant commits:

- `529c3a3524f34be228c353c264488711aa6474d6` — inventory-first wrapper
- `aa80388b27e4d39bb2cfa1adb5ebe02387c9bcb9` — Drive review root resolution

## Engineering OS identity

`ENGINEERING_OS_PROJECT_ID` and `ENGINEERING_OS_JOB_ID` no longer need to be manually repeated for Case 0003 when the persisted OpenWorker JobBinding exists.

The wrapper reads:

`<workspace>/.openworker/job-binding.json`

and requires:

- schema `openworker.job-binding.v1`
- `assigned_host` equals `DESKTOP-UL7V2VV`
- bound workspace equals the current canonical workspace
- non-empty persisted `project_id` / `job_id`

Explicit OS IDs remain allowed only when they exactly equal JobBinding. Mismatch fails closed.

Commit:

- `40f9c22c0afae431940dce3b62a762aada51410c`
- regression tests: `33155f43b3f2ea5e2919d85f41a1c3816672931f`

## REAL acceptance boundary

This hardening does not change acceptance state. It only reduces setup friction and prevents identity/path drift before the UL7 REAL run.

Case 0003 is still not globally ACCEPTED. GEO remains the only accepted business artifact until fresh Street View, Orthophoto, Terrain AOI, Consumer, Blender, SceneX, Engineering OS, Drive review and reviewed-delivery gates are physically passed.
