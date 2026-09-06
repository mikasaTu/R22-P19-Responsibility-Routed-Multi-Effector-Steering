import pytest
from stage2_robotwin.stage2g.scripts.preflight_gates import amplitude_selection
def rows():
    return [dict(amplitude_m=a,spectral_snr=[10.,11.],dual_contact_fraction=.95,task_success=True) for a in [.003,.005,.008]]
def test_smallest_eligible_and_fail_closed():
    assert amplitude_selection(rows(),repeat_bitwise_passed=True)["recommended_amplitude_m"]==.003
    r=rows();r[0]["spectral_snr"]=[9.99,11]
    assert amplitude_selection(r,repeat_bitwise_passed=True)["recommended_amplitude_m"]==.005
    for x in r:x["task_success"]=False
    assert amplitude_selection(r,repeat_bitwise_passed=True)["recommended_amplitude_m"] is None
    assert amplitude_selection(rows(),repeat_bitwise_passed=False)["status"]=="REPEATABILITY_BLOCKED"
def test_nonfinite_or_incomplete_cannot_pass():
    r=rows()
    for x in r:x["spectral_snr"]=[float("nan"),float("inf")]
    assert amplitude_selection(r,repeat_bitwise_passed=True)["eligible_amplitudes_m"]==[]
    with pytest.raises(ValueError):amplitude_selection(r[:2],repeat_bitwise_passed=True)
