# Stage 2D-A analytic operator report

## DONE

The frozen 4D linear testbed ran A0--A7 on 256 fixed seeds on both the local CPU
environment and dev14.  Dev14 tests: 6 passed; two SLSQP bound-clipping warnings are
retained.  The result file is `results/analytic/analytic_results_dev14.json`.

## KEY RESULT

- A4 correct external target: desired MAE 0.013723, net relative error 0.001347,
  feasibility 100%, action modification 0.5877.
- A5 swapped: desired MAE 0.603740; A6 random: 0.338311.
- A7 internal term: internal proxy 0.010580 versus A4 0.018867, with MAE worsening
  from 0.013723 to 0.015256.
- A3 self-target: mean absolute contribution movement 0.000791.
- All seven literal analytic gates passed.

## WHAT WAS FALSIFIED

Self-targeting current contribution does not initiate a desired transfer in this
system.  Reversing the target reverses the allocation direction.  The internal term's
gain is directly caused by its explicit orthogonal-differential penalty and trades
against target tracking.

## LIMITATION

Both independent reviewers block a V2 or novelty interpretation.  The initial test
uses perfect known gains, an exact feasible base, a target structurally aligned with
the evaluation metric, and no contact dynamics.  A0/A1 are identical.  Correct beats
random in 252/256 cases; A7 internal is no worse than A1 in 253/256; A4 max MAE is
0.17763.  This is therefore recorded as `PARTIAL_ANALYTIC_ALLOCATOR_GO`, not evidence
that takeover-capacity target provenance is correct.

## NEXT

Execute actual same-state donor-fade and active RoboTwin audits without using this
synthetic result to pre-accept the downstream mechanism.

