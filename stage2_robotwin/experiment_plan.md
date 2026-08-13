# R22-P19 Stage 2 execution contract

## Proposition

In a real bimanual RoboTwin handover, simulator counterfactual effects can
identify which arm currently has causal authority over the shared object.  A
later responsibility-conserving operator may transfer command authority while
preserving the base action's object-level effect.

## Evidence order

1. Ten `handover_block` expert smoke episodes with E0--E6 event audit,
   videos, time-aligned traces, and snapshot replay.
2. Oracle signal audit on real bimanual tasks and authority swaps.
3. ACT only after the signal audit; PAI is not used for Stage 2A.

The prior single-arm LIBERO result remains preliminary evidence and cannot
block or establish the original bimanual claim.  Oracle simulator results are
privileged and are not deployability evidence.  `accepted=false` throughout
this stage.

## Dynamic status vocabulary

Signal results use `SIGNAL_STRONG`, `SIGNAL_PARTIAL`,
`SIGNAL_NEEDS_THREE_WAY`, or `SIGNAL_WEAK`.  Signal, operator, policy
compatibility, specificity, and deployability are reported separately; no
single historical threshold permanently terminates the project.
