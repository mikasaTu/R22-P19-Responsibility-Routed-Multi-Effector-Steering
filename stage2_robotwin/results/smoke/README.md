# RoboTwin smoke result lineage

All bounded development receipts are retained. Only `final-10` is the selected
smoke result; the earlier directories document integration failures and the
snapshot/restore correction path.

| Run | Attempts | Valid successes | Outcome |
| --- | ---: | ---: | --- |
| `integration-v1` | 3 | 0 | MPLib adapter called the unavailable `plan_batch` API |
| `integration-v2` | 3 | 0 | Move adapter forwarded a `None` target pose |
| `integration-v3` | 1 | 0 | Reproduced the same missing-target fail-closed path |
| `integration-screw-v1` | 1 | 0 | Snapshot bytes were incorrectly converted to a NumPy array before `unpack_poses` |
| `integration-screw-v2` | 1 | 1 | Event chain succeeded, but replay diverged: pose `0.001294`, linear velocity `0.038723`, angular velocity `0.657179` |
| `integration-screw-v3` | 1 | 1 | Corrected state restore; H=10 replay differences were all zero |
| `final-10` | 11 | 10 | Selected smoke: ten event-valid successes and zero replay difference; seed 4 retained as a planner failure |

The `10/11` final-run yield is a deterministic seed-search receipt, not an
unbiased task success-rate estimate. Raw attempts, logs, traces, and videos are
stored inside their corresponding run directories. Curves, event montages,
manual visual decisions, and aggregate trace metrics for the selected run are
under `smoke_assets/`.

See [`../../reports/SMOKE_REPORT.md`](../../reports/SMOKE_REPORT.md) for the
frozen runtime contract, exact episode table, visual audit, and evidence
boundary.
