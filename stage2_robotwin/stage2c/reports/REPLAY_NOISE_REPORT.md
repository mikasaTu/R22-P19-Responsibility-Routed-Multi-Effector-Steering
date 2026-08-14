# Stage 2C Fresh-Prefix Replay Noise Report

## DONE
Completed 100/100 independent seed × condition × method × replicate processes.

## KEY RESULT
Exact-null within numerical tolerance: yes.
The oracle branches ran in a separate SAPIEN scene, so branch restore never wrote the main replay scene.

| metric | fresh P95 | old P95 | 3x gate |
|---|---:|---:|---:|
| donor_residual_influence_impulse_sum | 0 | NA | 0 |
| final_object_displacement_m | 0 | NA | 0 |
| min_object_height_m | 0 | 0.0001837 | 0 |
| peak_object_angular_velocity | 0 | 1.215 | 0 |
| peak_object_linear_jerk | 0 | 5.766 | 0 |
| peak_relative_slip_m | 0 | 0.001291 | 0 |

## LIMITATION
Fresh-prefix equality establishes a replay floor; it does not validate the responsibility mechanism.

## NEXT
Use the metric-specific 3×P95 floor in local and closed-loop effect claims.
