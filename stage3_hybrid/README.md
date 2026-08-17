# Stage3A hybrid takeover routing validation

This directory is an additive, preregistered validation package. It does not
modify or supersede any Stage2 result. `accepted` remains false in every
artifact. The experiment uses six fixed donor arm+velocity+gripper time-warp
modes, exact receiver-command invariance, fresh-process full-prefix replay, and
episode-level decisions.

The frozen contract is under `preregistration/`. Run the mandatory tests before
any matrix. `run_matrix.py` executes at most two simulator workers and persists
launch order, cell receipts and completion state. `audit.py` fails closed on
receiver/prefix hash drift, snapshot use, base non-noop, or activation drift.
`analyze.py` refuses missing cells and evaluates the calibration eligibility
gate. No PAI job or model training is permitted in Stage3A.

