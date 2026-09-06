import pytest
from collections import Counter
from stage2_robotwin.stage2g.scripts.matrix import stage_i,stage_ii

def test_stage_i_all_independent_conditions():
    rows=stage_i()
    assert len(rows)==24
    assert Counter(x["group"] for x in rows)=={"I-A":8,"I-B":4,"I-C":4,"I-D":6,"I-E":2}
    assert {x["seed"] for x in rows}=={0,1}
    assert rows==stage_i()
    assert rows!=stage_i(seed=1)
    assert all(x["accepted"] is False and x["pai_job_created"] is False for x in rows)
def test_p2_requires_instrument_and_frozen_candidate():
    for passed in [False,None,0,1]:
        with pytest.raises(ValueError):
            stage_ii(instrument_passed=passed,amplitude_m=.005)
    with pytest.raises(ValueError):
        stage_ii(instrument_passed=True,amplitude_m=.006)
    rows=stage_ii(instrument_passed=True,amplitude_m=.005)
    assert len(rows)==48
    assert len({(x["seed"],x["soft_arm"],x["gamma"],x["repeat"]) for x in rows})==48
