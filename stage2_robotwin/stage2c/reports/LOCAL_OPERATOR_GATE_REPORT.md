# Stage 2C Local Operator Gate Report

## DONE
Completed 10/10 seed/profile cells; analyzed 1800 method-state-horizon rows.

## KEY RESULT
Decision: `RESPONSIBILITY_NOT_CAUSAL`.
Median correction ratio=0.1733; >5% active rate=0.85; correct target movement=0; swapped movement=0.

| criterion | pass |
|---|---|
| active_correction_over_5pct_rate_at_least_30pct | yes |
| angular_or_slip_effect_exceeds_null_floor | yes |
| conservation_only_not_same_shift | no |
| contact_and_height_not_degraded | yes |
| correct_moves_responsibility_at_least_0p15 | no |
| median_action_correction_between_5_and_20pct | yes |
| predicted_total_effect_error_below_5pct | yes |
| realized_intervention_exceeds_3x_null_floor | yes |
| realized_total_effect_deviation_below_10pct | yes |
| swap_reverses_direction | no |

## LIMITATION
Short H=10/20 branches test local causality, not task success.

## NEXT
The full downstream matrix was executed under the user's explicit protocol override regardless of this gate.
