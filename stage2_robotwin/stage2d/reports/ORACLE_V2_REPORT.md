# Stage 2D oracle-v2 formal report

## Final decision

**`ORACLE_V2_NOT_SUPPORTED`** (`accepted=false`, policy gate `BLOCK`).

All requested downstream diagnostics were completed after the failed calibration
and local gates. The retained matrix has 320/320 fresh-process cells and zero
runtime failures: 5 seeds x 4 conditions x 16 methods.

## Closed-loop comparisons

| condition | C13 full vs C0 base | C13 full vs C12 conservation | C8 correct vs swapped/shuffled/shifted |
|---|---:|---:|---:|
| clean | -80 pp | -80 pp | 0 / 0 / 0 pp |
| T1 receiver gain 0.4 | -60 pp | -60 pp | 0 / 0 / 0 pp |
| T2 active amplitude 25 mm | -80 pp | -80 pp | 0 / 0 / 0 pp |
| T3 COM shift 30 mm | -80 pp | -80 pp | 0 / 0 / 0 pp |

T1--T3 are explicitly `INELIGIBLE_STRESS_OVERRIDE`; no calibrated stress met
the preregistered 30%--80% capable range. They are retained only because the
user required completing every experiment after gate failure.

C13 reduced the internal-force proxy from about 0.245 to 0.124--0.128, yet task
success fell to 1/5 clean, 2/5 T1, 1/5 T2, and 1/5 T3. C14 success was 1/5,
3/5, 2/5, and 1/5 respectively; its internal-suppression delta relative to C13
was +3.69e-05, +7.22e-04, +2.01e-04, and -1.04e-05. Thus the proxy improvement
does not constitute takeover or task improvement.

The actual-current V1 replay (`C5`) was rerun for all 20 condition-seed cells.
It completed without runtime failure and succeeded 5/5 in every condition. Its
trajectory RMSE was 0.00401, 0.01140, 0.00466, and 0.00408 m for clean/T1/T2/T3,
with about 0.0402 rad mean action modification.

## Why the full mechanism loses

The capacity trace is sparse and the desired-responsibility state begins at 0.1
with a 0.08-per-update slew limit. The receiver target therefore remains below
the 0.5 release threshold during relevant donor-open requests. In the first
retained C13 smoke, all 420 donor-open requests were blocked and mean target was
0.329. This temporal mismatch preserves overlap/internal-load suppression but
prevents the donor-release transition and increases trajectory error. It follows
from the frozen state-update and release-guard code, not a new hypothesis.

## Scientific boundary

The analytic allocator is only a synthetic target-tracking sanity check; both
novelty reviewers rejected full-mechanism identifiability. Capacity calibration
had no eligible stress, the local causal gate failed, closed-loop target controls
were non-specific, and the full mechanism reduced task success. No ACT, pi0.5,
Diffusion, learned estimator, PAI job, real-robot run, or deployable policy result
was produced.
