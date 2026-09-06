import hashlib, json
from pathlib import Path
import numpy as np
import pytest

from stage2_robotwin.stage2g.probe.tape import (
    FrozenNominalTape, ProbePairTape, build_frequency_pair,
    cartesian_offset_to_joint_delta, load_pair_with_sidecar,
)

def make_nominal(n=100):
    step=np.arange(n,dtype=np.int64)
    eye=np.broadcast_to(np.eye(6,dtype=np.float64),(n,6,6)).copy()
    rot=np.broadcast_to(np.eye(3,dtype=np.float64),(n,3,3)).copy()
    zeros=np.zeros((n,6),dtype=np.float64)
    gripper=np.full((n,2),np.nan,dtype=np.float64)
    return FrozenNominalTape(
        step=step,left_position=zeros.copy(),left_velocity=zeros.copy(),
        right_position=zeros.copy(),right_velocity=zeros.copy(),
        left_gripper=gripper.copy(),right_gripper=gripper.copy(),
        left_jacobian=eye.copy(),right_jacobian=eye.copy(),
        left_root_rotation=rot.copy(),right_root_rotation=rot.copy(),
        active_offset_m=np.zeros(n),left_raw_position=zeros.copy(),right_raw_position=zeros.copy(),
        left_nominal_actual_offset_world=np.zeros((n,3)),right_nominal_actual_offset_world=np.zeros((n,3)),
        left_nominal_clip_scale=np.ones(n),right_nominal_clip_scale=np.ones(n),
        e_perp_world=np.asarray([0.,1.,0.]),physics_hz=250.0)

def test_mapping_audits_real_cartesian_and_clip():
    delta,audit=cartesian_offset_to_joint_delta(np.eye(6),np.eye(3),[0,1,0],0.003)
    assert np.array_equal(delta,np.asarray([0.,.003,0,0,0,0]))
    assert audit["clipped"] is False
    assert np.allclose(audit["predicted_world_translation_m"],[0,.003,0])
    _,clipped=cartesian_offset_to_joint_delta(np.eye(6),np.eye(3),[0,1,0],0.2,max_joint_delta_rad=.05)
    assert clipped["clipped"] is True and clipped["joint_delta_max_abs_rad"] == pytest.approx(.05)

def test_pair_is_deterministic_and_has_two_frequency_offsets(tmp_path):
    nominal=make_nominal()
    pair1,meta1=build_frequency_pair(nominal,frequency_left_hz=1.,frequency_right_hz=2.5,amplitude_m=.005,e3=20,e5=80)
    pair2,meta2=build_frequency_pair(nominal,frequency_left_hz=1.,frequency_right_hz=2.5,amplitude_m=.005,e3=20,e5=80)
    p1=tmp_path/"a.npz"; p2=tmp_path/"b.npz"
    assert pair1.save(p1)==pair2.save(p2)
    assert np.array_equal(pair1.left_position,pair2.left_position)
    assert np.max(np.abs(pair1.left_probe_offset_m)) <= .005 + 1e-12
    assert np.max(np.abs(pair1.right_probe_offset_m)) <= .005 + 1e-12
    assert np.all(pair1.left_probe_offset_m[:20] == 0) and np.all(pair1.left_probe_offset_m[81:] == 0)
    assert meta1["live_jacobian_used"] is False and meta2["offline_from_frozen_nominal"] is True

def test_pair_sidecar_strict_hash_and_load(tmp_path):
    nominal=make_nominal()
    pair,meta=build_frequency_pair(nominal,frequency_left_hz=1.,frequency_right_hz=2.5,amplitude_m=.003,e3=20,e5=80)
    path=tmp_path/"pair.npz"; sha=pair.save(path)
    meta.update({"npz_sha256":sha,"seed":0,"source_tape_sha256":"tape","source_nominal_npz_sha256":"nominal"})
    path.with_suffix(".json").write_text(json.dumps(meta))
    loaded,loaded_meta=load_pair_with_sidecar(path)
    assert np.array_equal(loaded.left_position,pair.left_position) and loaded_meta["npz_sha256"]==sha
    path.write_bytes(path.read_bytes()+b"x")
    with pytest.raises(ValueError,match="sha256"):
        load_pair_with_sidecar(path)

def test_instrument_modes_are_distinct_and_locked_side_is_zero():
    nominal=make_nominal()
    pair,_=build_frequency_pair(nominal,frequency_left_hz=1.,frequency_right_hz=2.5,amplitude_m=.003,e3=20,e5=80)
    dual_l,dual_r=pair.offsets_for("dual")
    sl_l,sl_r=pair.offsets_for("single-left")
    sr_l,sr_r=pair.offsets_for("single-right")
    ll,lr=pair.offsets_for("locked-left")
    assert np.array_equal(sl_l,dual_l) and np.all(sl_r==0)
    assert np.all(sr_l==0) and np.array_equal(sr_r,dual_r)
    assert np.all(ll==0) and np.array_equal(lr,dual_r)

def test_runner_source_has_no_live_jacobian_or_snapshot_restore():
    source=Path(__file__).parents[1]/"scripts"/"run_probe_cell.py"
    text=source.read_text()
    for forbidden in ("compute_single_link_jacobian","_arm_model","cartesian_offset_to_joint_delta","SapienSnapshot"):
        assert forbidden not in text

def test_full_trace_bytes_hash_excludes_metadata_and_detects_drift():
    from scripts.run_probe_cell import _trace_hash
    payload={"object_xyz":np.zeros((4,3)),"object_velocity":np.ones((4,3)),"left_wrench":np.zeros((4,6)),"right_wrench":np.ones((4,6)),"dual_contact":np.ones(4,dtype=bool)}
    first=_trace_hash(payload); second=_trace_hash({k:v.copy() for k,v in payload.items()})
    assert first==second
    payload["object_xyz"][0,0]=np.nextafter(0.,1.)
    assert first!=_trace_hash(payload)
