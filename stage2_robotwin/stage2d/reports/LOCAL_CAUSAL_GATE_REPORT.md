# Stage 2D local causal gate report

## Protocol

The audit used five seeds, five active-overlap states per seed, nine methods
(`L0`--`L8`), and four actual SAPIEN branches (`LR`, `L`, `R`, `ZERO`). This is
225 method-state evaluations and 900 independently restored branches. The
object-effect decomposition, rather than commanded allocation, defines measured
receiver contribution.

## Result

Decision: **`LOCAL_NO_GO`**.

For the full correct mechanism (`L3`), mean contribution movement was -0.206788,
so its absolute movement and swapped-opposite-direction checks passed. It failed:

- desired-target MAE: 0.161462 (gate <= 0.15);
- net-effect relative error: 0.251339 (gate <= 0.10);
- correct better than shuffled/time-shifted: false;
- actual joint-action modification ratio: 0.791057 (gate <= 0.30).

Contact retention was 1.0 and the orthogonal-differential proxy was 9.82e-06,
but those passes do not rescue causal specificity. `L3` and `L5` were identical
because the frozen capacity/state traces collapsed to the same target path.

The internal-force variant (`L8`) retained movement (-0.181450), but still failed
target MAE (0.147270 under its own summary context), net error (0.205910),
specificity, and action-modification requirements.

## Evidence boundary

This is a same-state, privileged-simulator branch audit. It measures local object
effects but is neither a learned-policy result nor a deployable closed loop.
