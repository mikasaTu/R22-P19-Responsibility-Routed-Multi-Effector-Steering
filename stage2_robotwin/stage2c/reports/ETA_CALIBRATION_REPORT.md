# Stage 2C Eta Calibration Report

## DONE
Completed 4/4 calibration seed/profile cells before the held-out local gate.

## KEY RESULT
Recommended eta=0.25 under the frozen selection rule `closest_to_0p125_median_correction_among_0p05_to_0p20_feasible_candidates`.
The formal local and closed-loop configuration was generated before held-out evaluation and changes only eta plus explicit lineage metadata.

| eta | eligible | median correction ratio | target movement |
|---:|---|---:|---:|
| 0.25 | yes | 0.1592 | 0.002223 |
| 0.5 | yes | 0.1592 | 0.002668 |
| 0.75 | yes | 0.1592 | 0.002668 |
| 1.0 | yes | 0.1592 | 0.002668 |

## LIMITATION
Only calibration seeds 0 and 1 selected eta; held-out local-gate results were not used to retune it.

## NEXT
Keep the frozen eta unchanged throughout the stress and closed-loop matrix.
