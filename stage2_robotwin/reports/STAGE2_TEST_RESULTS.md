# R22-P19 Stage 2 verification receipts

Date: 2026-08-13

Host: dev14

Acceptance flag: `accepted=false`

## Test outcome

The final pre-publication code checks passed:

| Check | Result |
| --- | --- |
| Full repository test suite | `22 passed in 1.40s` |
| Stage 2 test suite alone | `19 passed in 2.94s` |
| Python bytecode compilation | PASS |
| Shell syntax for repository launch scripts | PASS |
| `git diff --check` | PASS |

The Stage 2 tests cover event ordering, invalid release detection, the 14-D
action contract, LR/L/R/ZERO neutral masking, measured-qpos neutral state,
snapshot restore semantics, gain/delay scheduling, geometric direction
commands, unknown-profile fail-closed behavior, Shapley reconstruction,
three-way decomposition, tie-aware analysis, per-horizon reporting, and the
independent intervention-validity gate.

## Artifact integrity

The pre-publication artifact audit passed:

| Artifact check | Result |
| --- | --- |
| JSON | 84 files parsed |
| JSONL | 14 files, 6,896 rows parsed |
| Parquet | 20 files, 96,049 rows, 3,553,813 numeric scalars; all finite |
| Media | 20 MP4 files / 3,951 frames and 26 PNG files decoded |
| Secret scan | 0 high-confidence findings |
| Symbolic links | 0 |
| Largest file | 16,379,165 bytes, below GitHub's 100 MiB limit |

The media decode check is structural. The selected ten E0--E6 montages also
received the separate manual visual audit recorded in
[`SMOKE_REPORT.md`](SMOKE_REPORT.md).

## Runtime and evidence boundary

Tests ran with the frozen dev14 environment at
`/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python`.
RoboTwin simulation artifacts use RoboTwin commit
`266f3aadf505a4f7fe9af0faa41a20f5f47cd123` and the `mplib_screw` planner.

Passing these checks verifies code and artifact integrity only. It does not
upgrade the one-episode diagnostic pilot to a formal Stage 2A result. No ACT
training/inference or PAI job was run.
