# R22-P19 Stage 2B-II oracle operator pilot

Date: 2026-08-14

Task: RoboTwin `handover_block`

Decision: **`SIGNAL_VALID_OPERATOR_WEAK`**

Acceptance: `accepted=false`

## Experiment contract

The pilot used the five held-out Stage 2B-I episodes (`2,3,5,6,7`), one clean
condition, and three frozen one-factor stress conditions:

- receiver gain `0.7`;
- receiver delay `2` control steps;
- receiver friction scale `0.7`.

All 12 methods (`B0`--`B11`) used the same per-episode expert low-level tape,
same in-memory E2 SAPIEN snapshot, seed, condition, and 250 Hz control rate.
Method order was rotated by episode and condition. Estimator branches were run
for every method. The matrix is complete: **240/240 unique replays**.

The full method `B11` combines three-way oracle responsibility, exact 1-D
effect conservation, and the separate release guard. The operator changes only
the horizontal task-direction component; rotations, other translations, and
gripper commands follow the expert except when the release guard blocks an open
request.

## Task outcomes and stress validity

All 240 replays completed successfully with no drop or premature release.
Consequently the requested 40%--80% stressed base-success calibration was not
met. Binary task outcomes are at ceiling and cannot establish operator benefit.

The final slip metric is contact-masked: separation after donor release is not
counted as slip. The earlier `pilot-v2-metrics-complete` attempt is retained and
explicitly marked `INVALID_METRIC`; it is excluded from inference.

## Primary paired result

For the three stress conditions pooled at the episode level, positive values
below mean the comparator is lower/better than B11; equivalently, negative
values mean B11 is better. The table reports `B11 - comparator`:

| Comparator | Angular velocity | Linear jerk | Contact-masked slip |
| --- | ---: | ---: | ---: |
| B0 base | -0.2091 `[-0.6718, 0.2537]` | +0.0616 `[-0.8389, 0.8272]` | +0.000104 `[-0.000088, 0.000350]` |
| B5 conservation only | -0.3489 `[-0.5979, -0.1000]` | -0.6255 `[-1.6510, 0.4000]` | +0.000060 `[-0.000079, 0.000224]` |
| B8 shuffled responsibility | -0.0670 `[-0.5188, 0.3203]` | +0.4551 `[-0.2329, 1.1131]` | +0.000076 `[-0.000102, 0.000310]` |
| B9 correct responsibility + operator null | -0.3518 `[-0.7271, -0.1269]` | -0.1223 `[-1.1757, 0.7584]` | +0.000106 `[-0.000045, 0.000319]` |

Intervals are 10,000-repetition paired episode-bootstrap 95% CIs with `n=5`.
B11 did not improve all three primary disturbance metrics over B0 in every
stress condition, and it beat all phase/distance/force heuristics on all three
metrics in **0/3** stress conditions. The preregistered operator-positive and
specificity criteria therefore fail.

## Conservation, activation, and cost

- B11 minimum solver feasible rate: **1.0000**.
- B11 maximum mean absolute effect-conservation error:
  **1.24e-21 m**.
- B11 median action correction: approximately zero
  (`5.42e-20 m`); P95: **1.95e-6 m**.
- B11 correction exceeded 1 micrometre on **11.73%** of logged steps.
- B11 joint-support mode: **75/23,124** logged steps (0.324%).
- B11 release blocks: **25/5,200** open requests (0.481%).
- Extra simulator work: **89,856** branch rollouts / **449,280** physics
  steps; estimator wall time 305.7 s, solver wall time 93.1 s, replay wall time
  890.5 s.

## Why apparent increases/decreases are not a mechanism win

The code-first reverse explanation is documented in
`MECHANISM_REVERSE_EXPLANATION.md`. The decisive observations are:

1. The KKT ridge `lambda=0.05` is **268.36 times** the median squared local
   gain (`1.863e-4`). Together with exact effect conservation, this makes the
   continuous operator numerically near-null; P95 corrections are only about
   0.19% of the median base-action magnitude.
2. B0 and B9 execute identical commands and identical oracle branch schedules,
   yet their episode differences reach 0.6235 rad/s angular velocity, 2.3277
   linear-jerk units, and 0.000610 m slip. SAPIEN snapshots do not expose the
   PhysX solver warm-start cache, so this is an empirical hidden-state replay
   floor larger than most routed effects.
3. Joint-mode and release-guard activations are sparse, so their ablations are
   almost identical over most of the trajectory.
4. The stress conditions did not lower base success, leaving binary metrics at
   ceiling.

Thus isolated apparent benefits (for example lower angular velocity relative
to B5/B9) and degradations cannot be assigned causally to responsibility
routing under this pilot.

## Decision and next-stage gate

The result is `SIGNAL_VALID_OPERATOR_WEAK`:

- signal validity: `MULTISEED_SIGNAL_SUPPORTED` under the contact-aware probe;
- operator validity: `WEAK_NOT_DEMONSTRATED`;
- specificity: `NOT_DEMONSTRATED`;
- policy compatibility: `NOT_TESTED`;
- deployability: `NOT_TESTED_SIMULATOR_ORACLE_ONLY`;
- ACT: `SKIPPED_BY_ORACLE_OPERATOR_GATE`;
- PAI job created: `false`.

Per the frozen plan, this result does not authorize ACT, a responsibility
network, Diffusion Policy, or pi0.5 training. It is not a broad negative result
for the underlying idea: this concrete near-null 1-D operator and weak stress
pilot did not show control improvement.

Primary evidence:

- `results/oracle_operator/pilot-v3-contact-slip/pilot_results.json`
- `results/oracle_operator/pilot-v3-contact-slip/operator_metrics.json`
- `results/oracle_operator/pilot-v3-contact-slip/operator_logs/`
- `results/oracle_operator/pilot-v3-contact-slip/raw_replays/`
- `results/oracle_operator/pilot-v3-contact-slip/paired_improvement.png`
