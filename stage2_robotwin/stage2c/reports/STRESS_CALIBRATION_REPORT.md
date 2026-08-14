# Stage 2C Stress Calibration Report

## DONE
Completed 96/96 cells across all 23 preregistered non-clean candidates with C0 and C13.

## KEY RESULT
Decision: `DIAGNOSTIC_STRESSES_FROZEN_WITH_ELIGIBILITY_FAILURE`.
`donor_release_advance_steps` is measured in 250 Hz tape/physics steps (4 ms each); `receiver_friction` is a multiplicative scale on the original gripper material.

| frozen stress | source | eligible | base success | max disturbance / clean | improvable |
|---|---|---|---:|---:|---|
| S1_hidden_authority_mismatch | hidden_authority_gamma_0p8 | no | 1 | 1.552 | no |
| S2_premature_release_risk | donor_release_advance_steps_10 | no | 1 | 1.422 | yes |
| S3_contact_quality_degradation | receiver_friction_0p5 | no | 1 | 1.53 | yes |

## LIMITATION
Calibration uses only seeds 0 and 1; a frozen diagnostic fallback is labeled ineligible when the preregistered stress rule is not met.

## NEXT
Evaluate the frozen values without changing them on held-out seeds.
