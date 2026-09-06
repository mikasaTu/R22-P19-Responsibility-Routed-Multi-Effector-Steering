import numpy as np
import pytest
from types import SimpleNamespace
from stage2_robotwin.stage2g.intervention.arm_lock import apply
class Joint:
    def __init__(self):self.v=(100.,20.,float(np.finfo(np.float32).max),"force")
    def get_stiffness(self):return self.v[0]
    def get_damping(self):return self.v[1]
    def get_force_limit(self):return self.v[2]
    def get_drive_mode(self):return self.v[3]
    def set_drive_properties(self,*v):self.v=v
def test_lock_is_constant_and_restores_exception():
    j=Joint();task=SimpleNamespace(robot=SimpleNamespace(left_arm_joints=[j],get_left_arm_real_jointState=lambda:[.2,0.]))
    old=j.v
    with pytest.raises(ValueError):
        with apply(task,"left") as h:
            assert j.v==(10000.,200.,old[2],old[3])
            assert h.position.tolist()==[.2]
            raise ValueError("body failure")
    assert j.v==old and h.restoration_exact
