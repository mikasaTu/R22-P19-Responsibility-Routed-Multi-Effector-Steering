"""Stage 2G frozen nominal and offline dual-frequency probe tapes."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np

PHYSICS_HZ = 250.0
ACTIVE_COMMON_AMPLITUDE_M = 0.015
PROBE_AMPLITUDES_M = (0.003, 0.005, 0.008)
DEFAULT_FREQUENCY_PAIRS_HZ = ((1.0, 2.5), (2.5, 1.0))
MAX_JOINT_DELTA_RAD = 0.12

def _f64(x): return np.ascontiguousarray(np.asarray(x, dtype=np.float64))
def _sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _save(path, payload):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f: np.savez_compressed(f, **payload)
    return _sha(path)
def _load(path):
    with np.load(Path(path), allow_pickle=False) as d: return {k: np.asarray(d[k]).copy() for k in d.files}
def _rot(x):
    x = _f64(x)
    if x.shape != (3,3) or not np.allclose(x.T @ x, np.eye(3), atol=1e-8): raise ValueError("root rotation must be orthonormal [3,3]")
    return x
def _check_cmd(step, arrays):
    step = np.asarray(step, dtype=np.int64)
    if step.ndim != 1 or not np.array_equal(step, np.arange(len(step))): raise ValueError("steps must be contiguous from zero")
    n = len(step)
    for i, a in enumerate(arrays):
        shape = (n,6) if i < 4 else (n,2)
        if a.shape != shape: raise ValueError(f"command field {i} expected {shape}, got {a.shape}")
        if i < 4 and not np.all(np.isfinite(a)): raise ValueError("command has non-finite value")
        if i >= 4 and np.any(np.isinf(a)): raise ValueError("gripper has infinite value")

def cartesian_offset_to_joint_delta(jacobian: Sequence[Sequence[float]], root_rotation: Sequence[Sequence[float]], e_perp_world: Sequence[float], offset_m: float, *, max_joint_delta_rad: float = MAX_JOINT_DELTA_RAD):
    """Pure mapping of a frozen Jacobian and a Cartesian e_perp offset."""
    j, r, e = _f64(jacobian), _rot(root_rotation), _f64(e_perp_world).reshape(-1)
    if j.ndim != 2 or j.shape[0] != 6: raise ValueError("jacobian must be [6,J]")
    if e.shape != (3,) or np.linalg.norm(e) <= 1e-12: raise ValueError("e_perp_world must be nonzero [3]")
    if not np.isfinite(offset_m) or max_joint_delta_rad <= 0: raise ValueError("invalid offset or clip bound")
    e /= np.linalg.norm(e); root_e = r.T @ e
    desired = np.r_[root_e * float(offset_m), np.zeros(3)]
    raw = np.linalg.pinv(j, rcond=1e-4) @ desired
    peak = float(np.max(np.abs(raw), initial=0.0)); scale = min(1.0, max_joint_delta_rad/peak) if peak else 1.0
    delta = np.ascontiguousarray(raw * scale, dtype=np.float64)
    pred_root, pred_world, req_world = j @ delta, r @ (j @ delta)[:3], e * float(offset_m)
    pnorm, rnorm = float(np.linalg.norm(pred_world)), abs(float(offset_m))
    return delta, {
        "requested_offset_m": float(offset_m), "requested_world_translation_m": req_world.tolist(),
        "root_direction": root_e.tolist(), "raw_joint_delta_rad": raw.tolist(), "joint_delta_rad": delta.tolist(),
        "raw_joint_delta_max_abs_rad": peak, "joint_delta_max_abs_rad": float(np.max(np.abs(delta), initial=0.0)),
        "clip_scale": float(scale), "clipped": bool(scale < 1.0),
        "predicted_root_translation_m": pred_root[:3].tolist(), "predicted_world_translation_m": pred_world.tolist(),
        "predicted_offset_m": pnorm,
        "predicted_direction_cosine": float(pred_world @ req_world/(pnorm*rnorm)) if pnorm > 1e-12 and rnorm > 1e-12 else 0.0,
        "jacobian_condition_number": float(np.linalg.cond(j)),
    }

@dataclass(frozen=True)
class FrozenNominalTape:
    step: np.ndarray; left_position: np.ndarray; left_velocity: np.ndarray; right_position: np.ndarray; right_velocity: np.ndarray
    left_gripper: np.ndarray; right_gripper: np.ndarray; left_jacobian: np.ndarray; right_jacobian: np.ndarray
    left_root_rotation: np.ndarray; right_root_rotation: np.ndarray; active_offset_m: np.ndarray
    left_raw_position: np.ndarray; right_raw_position: np.ndarray
    left_nominal_actual_offset_world: np.ndarray; right_nominal_actual_offset_world: np.ndarray
    left_nominal_clip_scale: np.ndarray; right_nominal_clip_scale: np.ndarray
    e_perp_world: np.ndarray; physics_hz: float = PHYSICS_HZ
    def __post_init__(self):
        step = np.asarray(self.step, dtype=np.int64)
        arrays = [_f64(getattr(self, n)) for n in ("left_position","left_velocity","right_position","right_velocity","left_gripper","right_gripper")]
        _check_cmd(step, arrays); n = len(step)
        for side in ("left","right"):
            j, r = _f64(getattr(self,side+"_jacobian")), _f64(getattr(self,side+"_root_rotation"))
            if j.ndim != 3 or j.shape[0] != n or j.shape[1] != 6 or not np.all(np.isfinite(j)): raise ValueError("invalid frozen Jacobian")
            if r.shape != (n,3,3): raise ValueError("invalid frozen root rotations")
            for row in r: _rot(row)
        for name in ("active_offset_m","left_nominal_clip_scale","right_nominal_clip_scale"):
            v=_f64(getattr(self,name))
            if v.shape!=(n,) or not np.all(np.isfinite(v)): raise ValueError(f"invalid {name}")
        for name in ("left_raw_position","right_raw_position"):
            v=_f64(getattr(self,name))
            if v.shape!=(n,6) or not np.all(np.isfinite(v)): raise ValueError(f"invalid {name}")
        for name in ("left_nominal_actual_offset_world","right_nominal_actual_offset_world"):
            v=_f64(getattr(self,name))
            if v.shape!=(n,3) or not np.all(np.isfinite(v)): raise ValueError(f"invalid {name}")
        e=_f64(self.e_perp_world).reshape(-1)
        if e.shape!=(3,) or np.linalg.norm(e)<=1e-12: raise ValueError("invalid e_perp_world")
    def __len__(self): return len(self.step)
    def item(self,i):
        if i<0 or i>=len(self): raise IndexError(i)
        out={"step":int(self.step[i])}
        for side in ("left","right"):
            out[side+"_position"]=getattr(self,side+"_position")[i].copy()
            out[side+"_velocity"]=getattr(self,side+"_velocity")[i].copy()
            g=getattr(self,side+"_gripper")[i]; out[side+"_gripper"]=None if np.isnan(g).all() else tuple(float(x) for x in g)
        return out
    def arrays(self):
        names=("step","left_position","left_velocity","right_position","right_velocity","left_gripper","right_gripper","left_jacobian","right_jacobian","left_root_rotation","right_root_rotation","active_offset_m","left_raw_position","right_raw_position","left_nominal_actual_offset_world","right_nominal_actual_offset_world","left_nominal_clip_scale","right_nominal_clip_scale","e_perp_world")
        return {n:np.asarray(getattr(self,n),dtype=np.int64 if n=="step" else np.float64) for n in names}
    def save(self,path): return _save(path,self.arrays())
    @classmethod
    def load(cls,path):
        v=_load(path); names=("step","left_position","left_velocity","right_position","right_velocity","left_gripper","right_gripper","left_jacobian","right_jacobian","left_root_rotation","right_root_rotation","active_offset_m","left_raw_position","right_raw_position","left_nominal_actual_offset_world","right_nominal_actual_offset_world","left_nominal_clip_scale","right_nominal_clip_scale","e_perp_world")
        missing=set(names)-set(v)
        if missing: raise ValueError(f"nominal tape missing fields: {sorted(missing)}")
        return cls(**{n:v[n] for n in names})

@dataclass(frozen=True)
class ProbePairTape:
    step: np.ndarray; left_position: np.ndarray; left_velocity: np.ndarray; right_position: np.ndarray; right_velocity: np.ndarray
    left_gripper: np.ndarray; right_gripper: np.ndarray; left_nominal_position: np.ndarray; right_nominal_position: np.ndarray
    left_probe_offset_m: np.ndarray; right_probe_offset_m: np.ndarray; left_applied_offset_world: np.ndarray; right_applied_offset_world: np.ndarray
    left_jacobian: np.ndarray; right_jacobian: np.ndarray; left_root_rotation: np.ndarray; right_root_rotation: np.ndarray; e_perp_world: np.ndarray
    frequency_left_hz: float; frequency_right_hz: float; amplitude_m: float; physics_hz: float = PHYSICS_HZ
    def __post_init__(self):
        step=np.asarray(self.step,dtype=np.int64); arrays=[_f64(getattr(self,n)) for n in ("left_position","left_velocity","right_position","right_velocity","left_gripper","right_gripper")]
        _check_cmd(step,arrays); n=len(step)
        for side in ("left","right"):
            p,o,a,j,r=(_f64(getattr(self,side+"_"+x)) for x in ("nominal_position","probe_offset_m","applied_offset_world","jacobian","root_rotation"))
            if p.shape!=(n,6) or o.shape!=(n,) or a.shape!=(n,3) or j.ndim!=3 or j.shape[0]!=n or j.shape[1]!=6 or r.shape!=(n,3,3): raise ValueError("invalid pair field shape")
            if not np.all(np.isfinite(p)) or not np.all(np.isfinite(o)) or not np.all(np.isfinite(a)) or not np.all(np.isfinite(j)): raise ValueError("non-finite pair field")
            for row in r: _rot(row)
        if _f64(self.e_perp_world).reshape(-1).shape!=(3,): raise ValueError("invalid pair e_perp_world")
        if self.amplitude_m<=0 or self.frequency_left_hz<=0 or self.frequency_right_hz<=0: raise ValueError("frequency/amplitude must be positive")
    def __len__(self): return len(self.step)
    def arrays(self):
        names=("step","left_position","left_velocity","right_position","right_velocity","left_gripper","right_gripper","left_nominal_position","right_nominal_position","left_probe_offset_m","right_probe_offset_m","left_applied_offset_world","right_applied_offset_world","left_jacobian","right_jacobian","left_root_rotation","right_root_rotation","e_perp_world")
        return {n:np.asarray(getattr(self,n),dtype=np.int64 if n=="step" else np.float64) for n in names}
    def save(self,path): return _save(path,self.arrays())
    @classmethod
    def load(cls,path,metadata):
        v=_load(path); names=("step","left_position","left_velocity","right_position","right_velocity","left_gripper","right_gripper","left_nominal_position","right_nominal_position","left_probe_offset_m","right_probe_offset_m","left_applied_offset_world","right_applied_offset_world","left_jacobian","right_jacobian","left_root_rotation","right_root_rotation","e_perp_world")
        missing=set(names)-set(v)
        if missing: raise ValueError(f"pair tape missing fields: {sorted(missing)}")
        return cls(**{n:v[n] for n in names},frequency_left_hz=float(metadata["frequency_left_hz"]),frequency_right_hz=float(metadata["frequency_right_hz"]),amplitude_m=float(metadata["amplitude_m"]),physics_hz=float(metadata.get("physics_hz",PHYSICS_HZ)))
    def offsets_for(self,instrument):
        valid={"dual","single-left","single-right","none","same-frequency","locked-left","locked-right"}
        if instrument not in valid: raise ValueError(f"unknown instrument mode {instrument}")
        l,r=self.left_probe_offset_m.copy(),self.right_probe_offset_m.copy()
        if instrument == "single-left": r.fill(0)
        elif instrument == "single-right": l.fill(0)
        elif instrument == "locked-left": l.fill(0)
        elif instrument == "locked-right": r.fill(0)
        elif instrument=="none": l.fill(0); r.fill(0)
        elif instrument=="same-frequency" and not np.isclose(self.frequency_left_hz,self.frequency_right_hz): raise ValueError("same-frequency requires equal frequencies")
        return l,r

def build_frequency_pair(nominal: FrozenNominalTape, *, frequency_left_hz: float, frequency_right_hz: float, amplitude_m: float, e3: int, e5: int, max_joint_delta_rad: float = MAX_JOINT_DELTA_RAD):
    if frequency_left_hz<=0 or frequency_right_hz<=0 or amplitude_m<=0: raise ValueError("frequency/amplitude must be positive")
    if e3<0 or e5<e3 or e5>=len(nominal): raise ValueError("active window outside nominal tape")
    step=np.asarray(nominal.step,dtype=np.int64); active=(step>=e3)&(step<=e5); t=(step.astype(np.float64)-e3)/nominal.physics_hz
    lo=np.where(active,amplitude_m*np.sin(2*np.pi*frequency_left_hz*t),0.0); ro=np.where(active,amplitude_m*np.sin(2*np.pi*frequency_right_hz*t),0.0)
    lp,rp=_f64(nominal.left_position).copy(),_f64(nominal.right_position).copy(); la,ra=np.zeros((len(nominal),3)),np.zeros((len(nominal),3)); alog,arog=[],[]
    for i in range(len(nominal)):
        ld,al=cartesian_offset_to_joint_delta(nominal.left_jacobian[i],nominal.left_root_rotation[i],nominal.e_perp_world,float(lo[i]),max_joint_delta_rad=max_joint_delta_rad)
        rd,ar=cartesian_offset_to_joint_delta(nominal.right_jacobian[i],nominal.right_root_rotation[i],nominal.e_perp_world,float(ro[i]),max_joint_delta_rad=max_joint_delta_rad)
        lp[i]+=ld;rp[i]+=rd;la[i]=al["predicted_world_translation_m"];ra[i]=ar["predicted_world_translation_m"];alog.append(al);arog.append(ar)
    pair=ProbePairTape(step=nominal.step.copy(),left_position=lp,left_velocity=nominal.left_velocity.copy(),right_position=rp,right_velocity=nominal.right_velocity.copy(),left_gripper=nominal.left_gripper.copy(),right_gripper=nominal.right_gripper.copy(),left_nominal_position=nominal.left_position.copy(),right_nominal_position=nominal.right_position.copy(),left_probe_offset_m=lo,right_probe_offset_m=ro,left_applied_offset_world=la,right_applied_offset_world=ra,left_jacobian=nominal.left_jacobian.copy(),right_jacobian=nominal.right_jacobian.copy(),left_root_rotation=nominal.left_root_rotation.copy(),right_root_rotation=nominal.right_root_rotation.copy(),e_perp_world=nominal.e_perp_world.copy(),frequency_left_hz=float(frequency_left_hz),frequency_right_hz=float(frequency_right_hz),amplitude_m=float(amplitude_m),physics_hz=float(nominal.physics_hz))
    receipt={"schema":"r22p19.stage2g.probe_pair_tape.v1","status":"COMPLETE","frequency_left_hz":float(frequency_left_hz),"frequency_right_hz":float(frequency_right_hz),"amplitude_m":float(amplitude_m),"physics_hz":float(nominal.physics_hz),"event_window":{"E3":int(e3),"E5":int(e5)},"axis":"e_perp","offline_from_frozen_nominal":True,"live_jacobian_used":False,"max_joint_delta_rad":float(max_joint_delta_rad),"left_clip_count":sum(bool(x["clipped"]) for x in alog),"right_clip_count":sum(bool(x["clipped"]) for x in arog),"left_mapping_audit":alog,"right_mapping_audit":arog,"accepted":False,"pai_job_created":False}
    return pair,receipt

def load_pair_with_sidecar(path: Path | str):
    target=Path(path); meta=json.loads(target.with_suffix(".json").read_text(encoding="utf-8"))
    required={"schema","status","npz_sha256","seed","physics_hz","source_tape_sha256","source_nominal_npz_sha256"}
    missing=required-set(meta)
    if missing: raise ValueError(f"pair sidecar missing fields: {sorted(missing)}")
    if meta["schema"]!="r22p19.stage2g.probe_pair_tape.v1" or meta["status"]!="COMPLETE": raise ValueError("pair sidecar is not COMPLETE")
    if int(meta["seed"]) not in (0,1): raise ValueError("pair sidecar seed is not calibration seed")
    if float(meta["physics_hz"])!=250.0: raise ValueError("pair physics_hz must be exactly 250")
    if meta["npz_sha256"]!=_sha(target): raise ValueError("probe pair npz sha256 mismatch")
    return ProbePairTape.load(target,meta),meta
