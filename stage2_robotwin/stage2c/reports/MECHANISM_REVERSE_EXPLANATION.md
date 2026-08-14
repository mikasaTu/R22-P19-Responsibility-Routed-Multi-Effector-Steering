# Stage 2C Mechanism Reverse Explanation

This document explains observed gains and losses from the executed code; it does not propose a new idea.

## 1. Why the replay floor changed
Stage 2B restored explicit rigid/articulation state into the same long-lived scene, but SAPIEN exposes no PhysX solver warm-start cache. The estimator therefore changed hidden solver history even when the final action was identical. Stage 2C copies explicit state into a second SAPIEN scene and performs every oracle branch there. Nothing is restored into the main scene, which causally removes oracle-induced warm-start contamination.

## 2. Why the old operator was near-null
The old KKT objective adds `ridge_lambda * ||a-a_base||²` with the fixed value 0.05 to a contribution residual whose scale is set by small physical gains. The regularizer dominates that residual and selects an action near the base. The new 1D operator instead moves only along `[b_R,-b_L]`, an exact nullspace of total effect, and limits the move with a relative trust region rather than another absolute ridge.

## 3. Why the new operator helped or hurt
The local gate decision was `RESPONSIBILITY_NOT_CAUSAL` with median correction ratio 0.1733. When correct responsibility beats swapped/shuffled, the gain is attributable to the direction of the nullspace transfer. When it does not, conservation, guard behavior, or generic action smoothing is sufficient to explain the change. Contact/support fallback and relative clipping can reduce effect; direct scaling can change total task effect and thereby trade success against jerk/slip.

The hidden-profile intervention is also not a scalar actuator attenuation: gamma interpolates expert and object-follower commands. The direct audit measured an absolute parallel attenuation rate of 0.6176 and a follower-above-expert rate of 0.4853. Thus a reversed hidden-authority contrast can arise from the actual follower command geometry, not from a label swap.

Across the complete matrix, C13's median episode-level correction ratio was 0, with a mean >5% active rate of 0.3126. Its solver statuses were `{"CONTACT_RETENTION_DEGENERATE_GAIN_BASE_FALLBACK": 75, "DEGENERATE_GAIN_BASE_FALLBACK": 941, "NULLSPACE_APPLIED": 186, "NULLSPACE_CLIPPED": 330}` and safety clips were `{"CONTACT_RETENTION": 75, "DEGENERATE_GAIN": 1016, "RELATIVE_TRUST_REGION": 330}`. These counts separate true nullspace transfer from degenerate-gain/contact fallbacks and trust-region clipping.
Direct scaling C5 does not conserve total task effect; its matrix-wide median episode correction ratio was 0.8813. Any C5 gain or loss is therefore a total-command change, not evidence for responsibility-preserving transfer.
C13's release guard blocked 698/13440 donor-open request steps. A C13-C4 or C13-C6 difference can therefore mix signed/stateful routing with guard behavior and must be read against C12.

## 4. Closed-loop falsification
Correct responsibility beat swapped and shuffled in 0/3 stresses; full routing beat conservation only in 0/3. Therefore the evidence maps to `RESPONSIBILITY_MECHANISM_NOT_SUPPORTED`, not to an unqualified idea-success claim.

## Evidence boundary
All statements concern RoboTwin `handover_block` with a privileged simulator oracle. `accepted=false`; deployability is not claimed.
