# Hypothesis-Code Conformance Report

Decision: **`CONFORMANCE_NO_GO`** (`accepted=false`).

The audit passed only the checks that can truthfully be satisfied by the frozen
immediate scope: operator-null no action change, withdrawal method receipt consistency,
and method-name-to-code-path consistency.

It failed five mandatory checks:

- the same actual 4D allocator is not called in local and closed-loop paths;
- conservation-only is not the same allocator with `lambda_target=0`;
- the internal method does not execute a nonzero true-wrench objective;
- the real Stage 2C V1 baseline is not wired into this comparison;
- release-only continuous arm-unchanged execution is absent from the full mechanism.

These paths were not mocked because the immediate Stage 2E plan explicitly prohibited
implementing allocator/state-machine/closed-loop work before withdrawal validity. The
subsequent physical matrix was completed only as a diagnostic continuation under the
user's explicit instruction not to stop remaining experiments after a failed gate. It
does not change this decision.

