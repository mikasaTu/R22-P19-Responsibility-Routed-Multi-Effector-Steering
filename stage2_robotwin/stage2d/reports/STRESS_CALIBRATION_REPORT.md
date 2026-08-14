# Stress calibration report

The complete first scan covered receiver gain 0.8/0.6/0.4, delay 4/8/12/16,
friction 0.7/0.5/0.3/0.2, COM shift 10/20/30 mm, and low/high active reference.
All 96 stress states at horizon 50 were capable.  A second horizon-200 scan covered
the strongest single and two-factor conditions; gain=0.4 yielded 90% capable and all
others 100%.  Therefore zero stresses are formally eligible.

The downstream labels T1/T2/T3 are diagnostic overrides only:

- T1: receiver gain 0.4 (capability mismatch)
- T2: active amplitude 25 mm (reference acceleration proxy)
- T3: COM shift 30 mm (contact/rotation degradation)

Decision: `NO_ELIGIBLE_STRESS / CONTINUE_BY_USER_OVERRIDE`.

