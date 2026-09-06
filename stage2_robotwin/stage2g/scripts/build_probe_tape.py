"""Freeze one nominal active replay and build offline frequency pair tapes."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from typing import Any
import numpy as np

REPO_ROOT=Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2d.scripts.run_capacity_audit import _active_item, _drive
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2b.operator.local_effect_gain import _arm_model
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block
from stage2_robotwin.stage2g.probe.tape import (
    ACTIVE_COMMON_AMPLITUDE_M, DEFAULT_FREQUENCY_PAIRS_HZ, PROBE_AMPLITUDES_M,
    FrozenNominalTape, build_frequency_pair, cartesian_offset_to_joint_delta,
)

def _runtime_git(root: Path) -> dict[str, Any]:
    head=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    status=subprocess.check_output(["git","-C",str(root),"status","--porcelain"],text=True)
    diff=subprocess.check_output(["git","-C",str(root),"diff","--binary"])
    return {"head":head,"dirty":bool(status.strip()),"status_porcelain":status.splitlines(),"dirty_diff_sha256":hashlib.sha256(diff).hexdigest()}

def _source_sha(root: Path) -> str:
    payload=bytearray(b"r22p19.stage2g.probe.source.v1\0")
    for path in sorted(root.rglob("*.py")):
        if "results" in path.parts or ".git" in path.parts: continue
        payload.extend(str(path.relative_to(root)).encode()); payload.extend(b"\0"); payload.extend(path.read_bytes()); payload.extend(b"\0")
    return hashlib.sha256(payload).hexdigest()

def _jacobian(task, side: str):
    _, model, qpos, link_index, move_indices, root_rotation = _arm_model(task, side)
    model.compute_forward_kinematics(qpos)
    jacobian=np.asarray(model.compute_single_link_jacobian(qpos,link_index,local=False),dtype=np.float64)[:,move_indices]
    return jacobian, np.asarray(root_rotation,dtype=np.float64)

def _gripper(value):
    return np.asarray(value if value is not None else (np.nan,np.nan),dtype=np.float64)

def freeze_nominal(robotwin_root: Path, tape_path: Path, meta_path: Path, output: Path, *, active_amplitude_m: float = ACTIVE_COMMON_AMPLITUDE_M):
    meta=json.loads(meta_path.read_text(encoding="utf-8")); tape=ExpertTape.load(tape_path)
    if output.exists() or output.with_suffix(".json").exists(): raise FileExistsError("nominal output already exists")
    seed=int(meta["seed"]); episode=int(meta["episode"])
    if seed not in (0,1): raise ValueError("only calibration seeds 0,1 are allowed")
    actual=hashlib.sha256(tape_path.read_bytes()).hexdigest()
    if meta.get("tape_sha256") and actual != meta["tape_sha256"]: raise ValueError("source tape sha256 mismatch")
    events={k:int(v) for k,v in meta["events"].items()}
    task=None; records=[]; active_offsets=[]; audits={"left":[],"right":[]}; jac={"left":[],"right":[]}; rots={"left":[],"right":[]}
    try:
        task, kwargs=build_handover_block(str(robotwin_root),planner="mplib_screw")
        task.setup_demo(now_ep_num=episode,seed=seed,**kwargs)
        frame=ObjectTaskFrame.from_task(task)
        e=np.asarray(frame.e_perp,dtype=np.float64)
        for i in range(len(tape)):
            raw=tape.item(i); step=int(raw["step"])
            nominal, active_offset=_active_item(task,raw,step,events,frame,float(active_amplitude_m))
            for side in ("left","right"):
                j,r=_jacobian(task,side); jac[side].append(j); rots[side].append(r)
                # Freeze the exact Stage2D command; diagnose its actual joint delta.
                # Do not substitute a separately rounded Cartesian mapping for it.
                delta=np.asarray(nominal[side+"_position"])-np.asarray(raw[side+"_position"])
                predicted=r@(j@delta)[:3]
                audits[side].append({"predicted_world_translation_m":predicted.tolist(),
                                    "clip_scale":1.0 if np.max(np.abs(delta))<0.12-1e-10 else 0.0,
                                    "clip_scale_semantics":"boundary_indicator_for_exact_Stage2D_command"})
            records.append(nominal)
            active_offsets.append(float(active_offset))
            _drive(task,nominal)
        def stack(side,key): return np.asarray([row[key] for row in records],dtype=np.float64)
        payload=FrozenNominalTape(
            step=np.asarray([row["step"] for row in records],dtype=np.int64),
            left_position=stack("left","left_position"),left_velocity=stack("left","left_velocity"),
            right_position=stack("right","right_position"),right_velocity=stack("right","right_velocity"),
            left_gripper=np.asarray([_gripper(row["left_gripper"]) for row in records]),
            right_gripper=np.asarray([_gripper(row["right_gripper"]) for row in records]),
            left_jacobian=np.asarray(jac["left"]),right_jacobian=np.asarray(jac["right"]),
            left_root_rotation=np.asarray(rots["left"]),right_root_rotation=np.asarray(rots["right"]),
            active_offset_m=np.asarray(active_offsets,dtype=np.float64),
            left_raw_position=np.asarray([tape.left_position[i] for i in range(len(tape))]),
            right_raw_position=np.asarray([tape.right_position[i] for i in range(len(tape))]),
            left_nominal_actual_offset_world=np.asarray([a["predicted_world_translation_m"] for a in audits["left"]]),
            right_nominal_actual_offset_world=np.asarray([a["predicted_world_translation_m"] for a in audits["right"]]),
            left_nominal_clip_scale=np.asarray([a["clip_scale"] for a in audits["left"]]),
            right_nominal_clip_scale=np.asarray([a["clip_scale"] for a in audits["right"]]),
            e_perp_world=e,physics_hz=250.0)
        output.parent.mkdir(parents=True,exist_ok=True); nominal_sha=payload.save(output)
        receipt={"schema":"r22p19.stage2g.frozen_nominal.v1","status":"COMPLETE","seed":seed,"episode":episode,"events":events,"physics_hz":250.0,"planner":"mplib_screw","active_amplitude_m":float(active_amplitude_m),"axis":"e_perp","source_tape":str(tape_path),"source_tape_sha256":actual,"nominal_npz_sha256":nominal_sha,"command_count":len(payload),"live_jacobian_used":True,"single_nominal_active_replay":True,"mapping_audit":{"left":audits["left"],"right":audits["right"]},"runtime_git":_runtime_git(robotwin_root),"source_code_sha256":_source_sha(REPO_ROOT),"accepted":False,"pai_job_created":False}
        output.with_suffix(".json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        return payload,receipt
    finally:
        if task is not None:
            try: task.close_env(clear_cache=True)
            except Exception: pass

def _label(value): return str(value).replace(".","p").replace("-","m")
def build_pairs(nominal, nominal_receipt, output_dir: Path, *, amplitudes=PROBE_AMPLITUDES_M, frequency_pairs=DEFAULT_FREQUENCY_PAIRS_HZ):
    output_dir.mkdir(parents=True,exist_ok=True); out=[]
    for fleft,fright in frequency_pairs:
        for amplitude in amplitudes:
            pair,receipt=build_frequency_pair(nominal,frequency_left_hz=fleft,frequency_right_hz=fright,amplitude_m=amplitude,e3=int(nominal_receipt["events"]["E3"]),e5=int(nominal_receipt["events"]["E5"]))
            name=f"pair__fL_{_label(fleft)}__fR_{_label(fright)}__A_{_label(amplitude)}"
            path=output_dir/(name+".npz")
            if path.exists() or path.with_suffix(".json").exists():raise FileExistsError("pair outputs are immutable")
            pair_sha=pair.save(path)
            left_audit=receipt.pop("left_mapping_audit")
            right_audit=receipt.pop("right_mapping_audit")
            receipt["mapping_audit_summary"]={
                "left_min_clip_scale":float(min(x["clip_scale"] for x in left_audit)),
                "right_min_clip_scale":float(min(x["clip_scale"] for x in right_audit)),
                "left_max_predicted_error_m":float(max(np.linalg.norm(np.asarray(x["predicted_world_translation_m"])-np.asarray(x["requested_world_translation_m"])) for x in left_audit)),
                "right_max_predicted_error_m":float(max(np.linalg.norm(np.asarray(x["predicted_world_translation_m"])-np.asarray(x["requested_world_translation_m"])) for x in right_audit)),
            }
            receipt.update({"source_nominal_npz_sha256":nominal_receipt["nominal_npz_sha256"],"npz_sha256":pair_sha,"source_tape_sha256":nominal_receipt["source_tape_sha256"],"source_tape":nominal_receipt["source_tape"],"runtime_git":nominal_receipt["runtime_git"],"source_code_sha256":nominal_receipt["source_code_sha256"],"seed":nominal_receipt["seed"],"episode":nominal_receipt["episode"],"events":nominal_receipt["events"]})
            path.with_suffix(".json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8"); out.append(path)
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--robotwin-root",type=Path,required=True); p.add_argument("--tape",type=Path,required=True); p.add_argument("--meta",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--seed",type=int,required=True); p.add_argument("--active-amplitude-m",type=float,default=ACTIVE_COMMON_AMPLITUDE_M)
    p.add_argument("--frequency-pair",action="append",default=[]); p.add_argument("--amplitude",action="append",type=float,default=[])
    args=p.parse_args()
    if args.seed not in (0,1): raise SystemExit("only calibration seeds 0,1 are allowed")
    if int(json.loads(args.meta.read_text())["seed"])!=args.seed:raise ValueError("CLI/meta seed mismatch")
    if args.output_dir.exists():raise FileExistsError("output directory must be new")
    pairs=DEFAULT_FREQUENCY_PAIRS_HZ if not args.frequency_pair else tuple(tuple(float(x) for x in value.split(",")) for value in args.frequency_pair)
    amplitudes=tuple(args.amplitude) if args.amplitude else PROBE_AMPLITUDES_M
    nominal_path=args.output_dir/f"nominal__seed_{args.seed:04d}.npz"
    nominal,receipt=freeze_nominal(args.robotwin_root,args.tape,args.meta,nominal_path,active_amplitude_m=args.active_amplitude_m)
    build_pairs(nominal,receipt,args.output_dir,amplitudes=amplitudes,frequency_pairs=pairs)
    print(json.dumps({"nominal":str(nominal_path),"pair_count":len(pairs)*len(amplitudes),"status":"COMPLETE","accepted":False,"pai_job_created":False},sort_keys=True))
if __name__=="__main__": raise SystemExit(main())
