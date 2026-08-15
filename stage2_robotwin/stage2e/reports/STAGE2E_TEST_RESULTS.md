# Stage 2E Test Results

- Stage 2E unit tests on dev14: `5 passed`.
- Combined Stage-2/2B/2C/2D/2E regression on dev14: `64 passed, 2 warnings`
  in 7.61 s. Both warnings are existing Stage2D SciPy bound-clipping warnings.
- Formal physical matrix: `120/120 COMPLETE`, `0 FAILED`.
- Fresh-process/fresh-scene contract: true for every cell.
- Receiver command: one SHA-256 per seed/channel group across all fades/repeats.
- Duplicate relative error: `0.0` for every fade in every group.
- PAI jobs: `0`.

Fresh-clone verification is recorded separately after publication and is not implied
by the figures above.

