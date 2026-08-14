# Stage 2D-B/C active task and takeover capacity report

## DONE

Actual RoboTwin/SAPIEN expert tapes were replayed in fresh main scenes.  Donor-fade
branches used a disjoint oracle scene, explicit same-state restore, five fade levels,
held grippers, and 4D outcome channels.  No snapshot was restored into the main scene.

## KEY RESULT

- Original handover overlap: moving fraction 17.5%, mean speed 1.44 mm/s; active gate
  failed.
- 15 mm continuous reference: 10/10 active windows valid, 10/10 task success, mean
  moving fraction 81.24%, speed 5.77 mm/s, dual-contact fraction 95.25%.
- At horizon 50, clean plus 16 stress candidates produced 146/146 capable labels;
  capacity AUROC was undefined and no stress was eligible.
- At horizon 200, the strongest seven calibration conditions produced only 1/70
  failure.  Composite capacity AUROC was 0.478; translation 0.804, support 0.848,
  phase 0.906.  No candidate met the frozen 30%--80% capable eligibility interval.

## WHAT WAS FALSIFIED

The original task is not sufficiently active.  More importantly, the frozen composite
capacity score does not outperform simple phase on the first independent held-out
donor-zero outcome and does not create calibratable positive/negative stress support.

## LIMITATION

The chosen T1 gain=0.4, T2 acceleration-high, and T3 COM=30 mm conditions are marked
`INELIGIBLE_STRESS_OVERRIDE`.  They are run only because the user required downstream
completion after failed gates; none may count toward ORACLE_V2 support.

## NEXT

Run all local/closed-loop controls and preserve negative/ineligible lineage.

