---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/EEM5w0qfNiTcgsk3dHzcvr8cnLg
wiki_node_token: EEM5w0qfNiTcgsk3dHzcvr8cnLg
document_token: A0ovdPzT1ooYWsxGCM3c8qKcn8g
revision_id: 8
exported_at_utc: 2026-09-02T13:58:43+00:00
source_content_sha256: c49891f9bcfbad8fd333ea75ac30604d1dcedd5ce4534d800d99eb9b8ad3ca97
---

# R22-P19 Stage 2F / Feishu Step8 Preflight

Date: 2026-09-02

Task: RoboTwin `handover_block`, planner `mplib_screw`, physics 250 Hz

Evidence boundary: privileged calibration diagnostic, `accepted=false`

Checkpoint decision: **`PREFLIGHT_READY_AWAITING_USER_CONFIRMATION`**

PAI jobs created: **0**

The repository filename retains the plan's frozen `STEP7_PREFLIGHT.md` spelling.  
The corresponding Feishu hierarchy is `实验规划 / step8 / 实验报告`.

## DONE

- Froze `preregistration/EXPERIMENT_CONTRACT.yaml` before the valid smoke. It  
contains all numeric G1-G6 thresholds, calibration-only seeds `[0,1]`, held-out  
prohibition, 144+10 matrix, episode bootstrap contract, decision labels, and the  
mandatory delivery-1 stop.
- Implemented K1 drive compliance by reusing `AuthorityProfile` and  
`authority_override`, K2 force-limit-only scaling, and the unchanged existing  
`SoftExpertAuthorityProfile` as K3 defect control. Every module exports the same  
`apply(task, soft_arm, gamma)` interface.
- Added exact restoration receipts because `SapienSnapshot` does not include  
stiffness, damping, force limit, or drive mode.
- Passed 28 Stage2F unit tests after independent review hardening, including  
matrix completeness, null fail-closed, cross-gamma receiver drift, active-tape  
lineage, production-schema adaptation, and oracle-alignment tests.
- Ran the two authorized fresh-process smoke cells in parallel on two dev14 A800s:  
seed 0, K1, left soft arm, gamma 1.0 and 0.2. Each completed 17 sampled states,  
68 LR/L/R/ZERO branches, and 1,360 oracle physics steps.
- Both main cells replayed from episode start and were never snapshot-restored.  
At each sampled state the main state was captured read-only and copied into a  
disjoint oracle; all 17 main/oracle dynamic-state SHA-256 pairs matched exactly.

## KEY RESULT

Both valid smoke cells completed and retained task success. All six soft-arm joints  
were modified at gamma 0.2, while gamma 1.0 was an exact no-op. Main and oracle drive  
properties were restored exactly after both cells.

| Metric | gamma 1.0 | gamma 0.2 |
|-|-|-|
| usable sampled states | 17 | 17 |
| wall time (s) | 65.5981 | 65.6080 |
| task success | 1 | 1 |
| dual-contact fraction | 0.969081 | 0.980565 |
| donor contact duration (steps) | 1120 | 1132 |
| donor contact present at E5 | 0 | 1 |
| soft parallel impulse integral | 0.457319 | 0.789784 |
| soft vertical impulse integral | 0.178013 | 0.274690 |
| soft parallel impulse share mean | 0.455355 | 0.450525 |
| mean object speed (m/s) | 0.009732 | 0.010726 |
| peak object speed (m/s) | 0.097171 | 0.178047 |

The same frozen active-reference SHA-256 was used in both cells:  
`f1621b9e5497e8f909845315dd9674395fae37c6e3baad6eaa958c26b384d6e1`.  
The canonical non-soft receiver command hash was byte-identical:  
`e993d484b262a809f3ce5ea91c0d98794c4344fb66a8b4a813695fb2a7a7ee1a`.

The median valid cell wall time was 65.603 s. A serial single-GPU extrapolation is  
2.624 h for the 144 main cells and 2.806 h for all 154 cells. This estimate excludes  
launch jitter, queueing, and any failure reruns.

The two-point smoke is not a gate evaluation. In particular, the gamma 0.2 parallel  
impulse integral was 1.727 times gamma 1.0. Correctly aligned mean `rho_soft`  
at H=5/10/20 was `[0.2324, 0.2107, 0.2214]` at gamma 1.0 and  
`[0.4129, 0.5373, 0.4890]` at gamma 0.2. The nominal gamma 1.0 donor contact was  
absent at E5, so it would fail the frozen per-cell `donor_contact_not_early`  
predicate. These are diagnostic observations only; six gamma  
levels, both seeds/arms, two repeats, null floors, and episode bootstrap are required  
before G1-G6 can be adjudicated. With one episode per smoke condition, a 95% episode  
CI is not estimable and is deliberately not fabricated.

## WHAT WAS FALSIFIED

The first implementation generated `_active_item` from each knob-affected live state.  
Although K1 never directly touched the non-soft arm target, the state-dependent live  
Jacobian changed that arm's active-reference command across gamma. Its two receiver  
hashes differed, violating G6. Those results are preserved under  
`preflight-smoke-invalid-live-jacobian-v1` and classified  
`INVALID_RECEIVER_COMMAND_DRIFT_NOT_USED`.

The corrected implementation first replays the nominal episode once and freezes the  
entire active-reference command tape. Every gamma reads the same bytes, while only the  
soft-arm actuator properties differ. The valid rerun produced equal receiver hashes.  
This code-first probe falsified the assumption that "the intervention only edits the  
soft arm" was sufficient to establish receiver-command isolation; command generation  
itself also had to be frozen.

Independent code review then found that the v2 oracle had remained at episode start,  
so its all-zero `rho_*` values were invalid even though its main-scene physical trace  
was valid. v2 is now machine-classified `INVALID_COUNTERFACTUAL_START_STATE_NOT_USED`.  
A first lockstep repair was also rejected after PhysX's unexposed warm-start state  
caused divergence after one branch rollout. The final v7 implementation instead  
copies each current main sampled state into a separate oracle, verifies exact dynamic  
state hashes, and never writes restored state into main. The resulting nonzero rho  
values demonstrate why the old zeros could not be interpreted as a mechanism result.

The valid K1 pair also shows why a lower drive gain is not automatically a lower  
contact impulse. K1 scales both stiffness and damping. At gamma 0.2 the donor remained  
in contact for 12 more steps and peak object speed increased by 83.2%; the reduced  
damping and altered closed-chain trajectory can therefore increase accumulated  
impulse even though the actuator gains are lower. This is a code-and-trace-grounded  
mechanism hypothesis, not a confirmed full-matrix conclusion and not a new idea.  
The aligned counterfactual pair moves in the same adverse direction: lower gamma  
raises mean `rho_soft` rather than attenuating it. This is consistent with the code  
path in which K1 scales damping together with stiffness while leaving the commanded  
target unchanged; responsibility is estimated from realized branch outcomes, so  
more oscillatory/longer contact can increase attributed physical effect. Two points  
from one calibration episode cannot establish monotonicity or causality across the  
registered matrix.

## LIMITATION

- Only the two explicitly authorized delivery-1 smoke cells ran. K2, K3, seed 1,  
right-soft-arm, remaining gamma levels, repeats, and ten null cells are unexecuted.
- No G1-G6 result or `AUTHORITY_KNOB_*` scientific decision is reported yet.
- Failed/invalid hardening attempts v1-v5 are retained with explicit dispositions.  
v6 first validated the cross-scene method; v7 reran the same two cells after final  
non-physical schema/lineage hardening and is the canonical published lineage.
- Both v7 cells record the same Stage2F source SHA-256:  
`1d310217545c6f2378edc6efa85eefe6aefe19cb4cd44d4299057ba0c48a25fe`.
- The alignment fingerprint covers articulation generalized/root state, box pose and  
twist, and normalized gripper bookkeeping. SAPIEN does not expose PhysX solver  
warm-start caches, so exact hidden-state identity cannot be claimed; this remains  
a simulator-oracle boundary even though all explicit sampled-state hashes match.
- The RoboTwin runtime is commit  
`266f3aadf505a4f7fe9af0faa41a20f5f47cd123` with an existing dirty optional-cuRobo  
import patch; its binary diff hash is  
`972f85496f52227c41c48a81ca7cb1921ad4f5add446893aea9cfe1495d0e0b2`.
- Missing optional cuRobo/pytorch3d imports were logged, but `mplib_screw` executed and  
both cells completed. This does not validate cuRobo.
- These are simulator contact impulses, not calibrated force measurements or a  
deployable estimator/policy result.

## NEXT

Stop at the mandatory delivery checkpoint. After explicit user confirmation, run all  
144 main cells and all 10 frozen null cells without stopping merely because an  
individual gate fails. Then calculate episode-level 10,000-repetition bootstrap CIs  
with seed 22019, evaluate G1-G6, write `AUTHORITY_KNOB_DECISION.json`, reverse-explain  
all improvements/degradations from the executed code, update the same Feishu report,  
and publish the delivery-2 artifacts. No PAI, ACT, pi0.5, learned estimator, held-out  
seed, closed-loop run, task substitution, or substrate change is authorized.
