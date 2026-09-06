"""Stage I-C constant-target high-stiffness calibration control."""
from contextlib import contextmanager
from dataclasses import dataclass,field
import numpy as np
from stage2_robotwin.stage2f.intervention.common import snapshot_drive_properties,drive_properties_equal

@dataclass
class ArmLock:
    side: str
    position: np.ndarray
    stiffness_multiplier: float=100.
    maximum_joint_drift_rad: float=0.
    restoration_exact: bool=False
    def observe(self,task):
        measured=np.asarray(getattr(task.robot,"get_"+self.side+"_arm_real_jointState")()[:-1])
        self.maximum_joint_drift_rad=max(self.maximum_joint_drift_rad,float(np.max(np.abs(measured-self.position))))
    def receipt(self):
        return dict(side=self.side,constant_target=self.position.tolist(),stiffness_multiplier=self.stiffness_multiplier,
                    damping_multiplier=float(np.sqrt(self.stiffness_multiplier)),
                    maximum_joint_drift_rad=self.maximum_joint_drift_rad,restoration_exact=self.restoration_exact,
                    physical_lock_is_high_stiffness_servo_not_kinematic_weld=True)
@contextmanager
def apply(task,side):
    if side not in ("left","right"):raise ValueError("unknown locked side")
    joints=list(getattr(task.robot,side+"_arm_joints"))
    old=snapshot_drive_properties(joints)
    if not old or any(v[0]<=0 or not np.isfinite(v[:3]).all() for v in old):raise ValueError("lock needs finite positive nominal stiffness")
    q=np.asarray(getattr(task.robot,"get_"+side+"_arm_real_jointState")()[:-1],dtype=np.float64).copy()
    if q.shape!=(len(joints),) or not np.isfinite(q).all():raise ValueError("invalid measured arm position")
    h=ArmLock(side,q)
    try:
        for joint,v in zip(joints,old):joint.set_drive_properties(v[0]*100,v[1]*10,v[2],v[3])
        yield h
    finally:
        errors=[]
        for joint,v in zip(joints,old):
            try:joint.set_drive_properties(*v)
            except Exception as exc:errors.append(str(exc))
        h.restoration_exact=drive_properties_equal(old,snapshot_drive_properties(joints))
        if errors or not h.restoration_exact:raise RuntimeError("arm lock restoration failed: "+"; ".join(errors))
