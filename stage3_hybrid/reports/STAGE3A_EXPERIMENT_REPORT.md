# 实验报告

R22-P19B Stage3A / step7 — Hybrid Takeover Mode Upper-Bound and Identifiability Pilot

## Final decision

`NO_INFORMATIVE_FAILURE_SPACE` (`accepted=false`).

The full permitted calibration program is complete: 14 single-factor
conditions (336 cells) plus six frozen two-factor fallbacks (144 cells), for
480/480 fresh-process RoboTwin branches and zero runtime failures. There were
no PAI jobs, no ACT/pi0.5/VLA training, no responsibility estimator, no
snapshot restore, and no change to any Stage2 negative decision.

## Frozen setup

- benchmark: RoboTwin `handover_block`
- RoboTwin commit: `266f3aadf505a4f7fe9af0faa41a20f5f47cd123`
- planner: `mplib_screw`
- seeds: calibration `[0,1]`; held-out `[2,3,5,6,7,8,9,10]` remained untouched
- modes: M0 base, M1/M2 early 100/50, M3/M4 delay 50/100, M5 abort-hold
- repeats: 2; episode is the only inference unit
- decision point: `max(E3+25,E4-100)`

## Integrity and tests

All 24 Stage3A tests passed (including all 12 mandatory named contracts); all 64 historical Stage2 pytest tests
passed. Both runtime audits passed every check: fresh process/scene, replay
from step 0, no snapshot, receiver hash invariance, prefix hash invariance,
M0 no-op, exact mode activation, `accepted=false`, and `pai_job_created=false`.
Success/drop labels agreed across both repeats in all 240 paired cells.

## Calibration result

No stress satisfied all four eligibility clauses. Across 20 conditions:

- 14 had base/oracle success `1.0/1.0` and gain 0;
- 5 had `0.0/0.0`, gain 0, disagreement 0;
- 1 had `0.0/0.0`, gain 0, disagreement 0.5.

Thus none had base success in `[0.30,0.80]`, and no candidate-set oracle
improved success by 0.15. The allowed two-factor fallback did not repair this.

## Mode result and mechanism

M1-M4 changed the donor command and residual-contact timing, but matched M0's
success in every one of 80 paired groups: zero rescues and zero harms. M5 was
strictly harmful: zero rescues, 56 harms, 5% drop, larger slip/jerk, and a mean
0.02338 m final-position shift on base-successful groups. The candidate set can
make the trajectory worse, but it did not expose an outcome-improving takeover
mode. Detailed code-level causality is in `MECHANISM_REVERSE_EXPLANATION.md`.

## Gate consequences and evidence boundary

The registered final vocabulary therefore requires
`NO_INFORMATIVE_FAILURE_SPACE`. The held-out Stage3A-1 matrix and Stage3A-2
ranker are prohibited because calibration did not freeze at least two eligible
stresses. This is a scientific gate stop, not a compute failure. The maximum
defensible claim is: the six-mode implementation is real and identifiable,
but this calibration space does not contain a beneficial discrete-mode upper
bound. It supplies no evidence for deployable routing, learned ranking,
responsibility allocation, policy improvement, or novelty.
