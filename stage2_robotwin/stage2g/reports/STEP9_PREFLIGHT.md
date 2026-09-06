# Step9 / Stage 2G preflight — Authority Probe & Grip-Force Authority

Date: 2026-09-07 (Asia/Shanghai)

Status: **PREFLIGHT_COMPLETE_AWAITING_USER_CONFIRMATION**
Recommendation: **A = 0.008 m**, pending the mandatory delivery checkpoint.
Evidence boundary: privileged RoboTwin calibration diagnostic; **accepted=false; pai_job_created=false**.

## DONE

The original Feishu idea was read and the user plan copied exactly into the new
实验规划 / step9 node. A readback verified all 117 nonempty source lines.
An 实验报告 child was created beneath step9.

The preregistration was committed before simulation at a188a12. It preserves all
I1-I5/A1-A5 numeric gates, seeds 0/1 only, no held-out data, the P1-before-P2
dependency, the mandatory delivery checkpoint, and the void Stage2F matrix.
The enumerated Stage I allocation is 24 cells (8+4+4+6+2), despite the plan's
approximate “30”; Stage II remains 48 conditional cells.

Implemented the dual-frequency probe, frozen nominal/pair tapes, K4 opening
fallback, authority FFT/coherence, six-dimensional wrench decomposition, and
bitwise effect comparison. Final Step9 tests: **31 passed**. Full Stage2
regression: **123 passed**, with two existing SciPy bound-clipping warnings.
After the five smoke cells, independent review added exact process/output
ownership and nominal/episode bindings, plus a unit-tested Stage I-C
high-stiffness constant-target control. These checks and the locked control have
not been used to claim a Stage I result.

One nominal seed-0 Stage2D active replay froze 5,154 commands with common
e_perp amplitude 0.015 m. Six probe tapes were generated offline: two frequency
pairs times three amplitudes. All had zero clipping; no condition replay used
a live Jacobian or restored the main scene.

Completed **five fresh-process smoke cells**: two identical 5 mm repeat cells,
then one cell per 3/5/8 mm amplitude. Every cell used the same calibration
seed 0, gamma 1, left soft-arm label and (fL,fR)=(1,2.5) Hz.
Amplitude launch order was randomized with seed 22019, after the exact
repeatability check passed. At most two dev14 GPUs were used concurrently.
No PAI, training, ACT, pi0.5, learned estimator, closed-loop or held-out run occurred.

## KEY RESULT

| Probe amplitude | Task success | Dual-contact fraction | SNR at fL | SNR at fR | Smoke eligible |
|---|---:|---:|---:|---:|---|
| 0.003 m | 1 | 0.969965 | 15.4544 | 5.2156 | no |
| 0.005 m | 1 | 0.967314 | 18.2265 | 6.3437 | no |
| 0.008 m | 1 | 0.969965 | 38.1617 | 11.8767 | yes |

The preregistered rule chooses the smallest candidate with both SNRs >=10,
dual contact >=0.95 and task success. Only **8 mm** qualifies. This is an
amplitude-smoke recommendation, not an I1-I5 result or a validated authority
measurement.

The two 5 mm repeats used different PIDs and had the identical complete-effect
SHA256:

1459aa008da231e8b1d2936ad71baff87936b7a5d52c58b11aa5ffe2ff65a224

The hash includes full window object position/quaternion, linear/angular
velocity, per-side impulse and force/torque, contact counts, dual-contact flags,
input offsets, projected displacement and task success, with no rounding.
The separate 5 mm amplitude cell also matched that hash. The repeated pair tape
SHA256 is 47ecb4cdaa04ad9321c5897a99a37a3bf6626e7136e203ad99c7e9243cffe5a6.

| Amplitude | Unvalidated spectral a_left | Mean internal-wrench diagnostic ratio | Coherence L / R |
|---|---:|---:|---:|
| 3 mm | 0.747673 | 0.341007 | 0.7014 / 0.4373 |
| 5 mm | 0.741813 | 0.335673 | 0.7202 / 0.4365 |
| 8 mm | 0.762649 | 0.338082 | 0.7344 / 0.5186 |

Each smoke condition has **one independent episode**. Repeated deterministic
replay is not another independent episode. Episode-level 95% CIs are therefore
not estimated. The later frozen inference contract remains 10,000 bootstrap
resamples, seed 22019, episode as inference unit.

## WHAT WAS FALSIFIED / MECHANISM REVERSE EXPLANATION

The 3 mm and 5 mm candidates do not make both frequency peaks exceed the frozen
noise threshold, even though contact and success survive. Increasing amplitude
to 8 mm raises both measured peaks enough to satisfy this smoke rule. The
input-to-joint map has no clipping, and its predicted Cartesian vector error
is below 6.7e-17 m; thus this threshold difference is not explained by the
configured joint clip. The realized contact dynamics and unequal frequency
response remain candidate mechanisms, not confirmed causal attribution.

At 3/5/8 mm the left displacement peaks are 0.522/0.916/1.993 mm, while right
frequency peaks are 0.176/0.319/0.620 mm. Net and internal gripper-wrench norms
both grow with amplitude; the diagnostic internal ratio stays near 0.34.
Larger absolute loading is therefore not evidence of transferred authority.
The unequal peaks could reflect frequency response rather than effector
responsibility. Only the still-unrun swapped-frequency, single-arm and
ground-truth controls can distinguish them.

K4 is explicitly a **normalized gripper target-opening intervention**, not a
calibrated force multiplier: u -> gamma*u+(1-gamma)*1.0, through the actual
RoboTwin API. The wrapper omits a finite drive force limit; scaling FLT_MAX or
URDF effort would not establish controlled grip force. K4 changes only the
soft gripper path, leaves receiver commands and arm properties unchanged,
and uses an exact finally restoration for gamma<1. Gamma=1 performs no write
and preserves the body's normal gripper evolution. No non-nominal K4 physical
sweep has run, so no grip-authority improvement or degradation is claimed.

The fixed Stage2F audit premises are retained. Its old K1 scaled both K and D
by gamma, so zeta scales by sqrt(gamma); gamma=.2 gives 0.4472 of nominal
damping ratio, consistent with the observed higher peak velocity and impulse.
K1 is not reused by Step9. Any future reuse must scale stiffness by gamma
and damping by sqrt(gamma).

The historical Stage2F traces omit signed per-side 3D impulses, torques and
contact positions. Their requested delta-w internal fraction is
**NOT_RECOVERABLE_FROM_STORED_TRACES**. The scalar impulse increase of 1.727x
and almost unchanged scalar share do not determine that fraction. Original
traces and negative conclusions are preserved; no number is invented and the
void 144+10 matrix was not executed.

## LIMITATION

- Stage I and Stage II are **unrun**. I2/I3/I4 and aggregate I5 are not adjudicated;
  no AUTHORITY_PROBE_INVALID/SUPPORTED scientific verdict is inferred from smoke.
- Only seed 0 was simulated; seed 1 inputs were read and hash-verified, not
  executed. Two frequency pairs were frozen but only (1,2.5) Hz was replayed.
- The E3..E5 window has 1,132 samples = 4.528 s. Native FFT resolution is
  0.220848 Hz; requested peaks are sampled at 1.10424 and 2.42933 Hz.
  A matching off-bin synthetic test has maximum ratio error 0.01964 (<0.02).
  This calibration test does not bound error on nonlinear physical signals.
- Noise is the median of 13 native bins in 0.3-5 Hz after excluding Hann
  mainlobes +/-2 native bins. Coherence uses seven overlapping 256-sample
  segments; resolution is 0.9765625 Hz, observed bins 0.97656/2.92969 Hz.
  It is coarse diagnostic evidence, not an additional gate.
- Wrenches are signed simulator contact impulses divided by dt=1/250, with
  moments about the object origin/center used by this task. w_ext is the net
  contribution of the two grippers, not gravity or all environmental contacts.
  A raw 6D norm mixes force and torque dimensions and is only a diagnostic;
  it is not a calibrated physical percentage.
- Original pair sidecars have a diagnostic label error: max_predicted_error
  subtracted a signed requested offset from an unsigned norm. Commands are
  unaffected. Original frozen bytes are preserved; MAPPING_AUDIT_CORRECTION.json
  supplies the correct vector-error calculation. The future builder is fixed.
- The locked control is a high-stiffness servo, not a kinematic weld; its
  eventual physical joint drift must be read from the runtime receipt.
- A5 comparison to NaturalResponsibilityEstimator belongs to conditional
  Stage II and has not been run. There is no new idea or substrate proposal.

## PROVENANCE / VALIDATION

Smoke execution source: **2cddb2b** (full commit in each cell source_identity).
Nominal freezer was integrated at 42cd2a0. Each smoke records an exact file-hash
manifest of all Stage2 Python source. Post-smoke checks and the Stage I-C
control are separately committed and have unit-test evidence only.

RoboTwin runtime:
266f3aadf505a4f7fe9af0faa41a20f5f47cd123,
with the pre-existing optional-CuRobo import patch, diff SHA256
972f85496f52227c41c48a81ca7cb1921ad4f5add446893aea9cfe1495d0e0b2.
The executed planner remained mplib_screw. Optional CuRobo/pytorch3d messages
were logged but do not represent a planner switch.

All five real processes, JSON files and trace files were live-verified as
UID/GID **2254:2254**. All source-tape, nominal-tape, episode and seed bindings
passed direct readback. See LIVE_ARTIFACT_VALIDATION.json.

Persistent run:
 /mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/R22-P19/stage2g/delivery1-20260907-v1

The repository includes original frozen tapes/sidecars, five trace+result pairs,
the decision, source plan, Feishu source/readback, code, tests and corrections.
Prior results roots were not overwritten.

## NEXT

Stop at the user attachment's mandatory checkpoint:
“停下，输出 stage2g/reports/STEP9_PREFLIGHT.md，等我确认”.

After confirmation, freeze 8 mm for Stage I, prepare seed-1 and same-frequency
control tapes without changing gates, and execute every one of the 24
independent instrument cells even if an individual instrument test fails.
Only if every I1-I5 gate passes may the 48-cell Stage II matrix be evaluated.
The Stage2F 144+10 matrix remains void. PAI remains prohibited by this plan.
