import numpy as np
import pytest
from stage2_robotwin.stage2g.scripts.run_probe_cell import effects_hash

def test_full_trace_repeat_hash_detects_one_ulp_and_contact_change():
    baseline={"object_position":np.zeros((10,3),dtype=np.float64),"contact_counts":np.ones((10,2),dtype=np.int64)}
    assert effects_hash(baseline)==effects_hash({k:v.copy() for k,v in baseline.items()})
    altered={k:v.copy() for k,v in baseline.items()}
    altered["object_position"][7,2]=np.nextafter(0.,1.)
    assert effects_hash(baseline)!=effects_hash(altered)
    altered={k:v.copy() for k,v in baseline.items()}
    altered["contact_counts"][7,1]=0
    assert effects_hash(baseline)!=effects_hash(altered)
def test_full_trace_rejects_nonfinite_and_shape_collision():
    with pytest.raises(ValueError):effects_hash({"p":np.array([np.nan])})
    assert effects_hash({"p":np.zeros((2,3))})!=effects_hash({"p":np.zeros((3,2))})
