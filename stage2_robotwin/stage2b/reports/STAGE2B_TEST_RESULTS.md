# R22-P19 Stage 2B verification receipts

Date: 2026-08-14

Host: dev14

Acceptance: `accepted=false`

## Code checks

| Check | Result |
| --- | --- |
| Stage 2 + Stage 2B unit suite | `37 passed in 4.89s` |
| Stage 2B bytecode compilation | PASS |
| `git diff --check` before publication | PASS |
| Held-out signal analysis reproduction | exact SHA-256 match |
| Operator analysis reproduction | exact SHA-256 match |

The independently regenerated held-out signal metrics matched the retained
file at SHA-256
`4973be4026034a23501236db82c17af60f1c385a32995338785abfd240bf3f30`.
The independently regenerated operator metrics matched at
`75b2ee06b7210ad5c1770ddf2d24e2a1186e75c1d8a6e0e5416625dd8b0df87d`.

## Artifact checks

The bounded Stage 2B subtree passed structural parsing and decode checks:

| Artifact | Parsed/decoded result |
| --- | ---: |
| JSON (pre-report result set) | 28 files |
| JSON/JSONL.GZ logs | 523 files / 596,320 rows |
| NPZ | 526 files / 14,426,336 numeric scalars |
| Parquet | 9 files / 42,883 rows / 428,830 numeric scalars |
| PNG | 3 files |
| MP4 | 21 files / 4,130 decoded frames |
| Symbolic links | 0 |
| High-confidence secret patterns | 0 |
| Largest file | 2,123,101 bytes |

The persisted expert-tape schema intentionally encodes “no new gripper
command on this physics step” as a pair `[NaN, NaN]`. Exactly 62,840 scalar
NaN sentinels were found, always paired and only in `left_gripper` or
`right_gripper` arrays under `expert_tapes/`. Replays consumed the original
in-memory `None` values, not those serialized sentinels. All other numeric NPZ
arrays and all scanned numeric Parquet values were finite.

## Evidence boundary

These checks establish code, analysis reproducibility, and artifact integrity.
They do not change the scientific decision `SIGNAL_VALID_OPERATOR_WEAK`, do
not turn simulator-oracle evidence into a deployable estimator, and do not
authorize ACT/PAI training.
