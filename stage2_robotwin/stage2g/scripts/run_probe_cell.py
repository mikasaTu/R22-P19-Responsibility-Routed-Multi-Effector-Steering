"""Fresh-process Step9 replay. No Jacobian generation or snapshot restoration."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, time, traceback
from pathlib import Path
from contextlib import ExitStack
import numpy as np
from stage2_robotwin.stage2g.probe.dual_frequency import load_pair_with_sidecar
from stage2_robotwin.stage2f.intervention.common import canonical_command_sha256
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block
from stage2_robotwin.wrappers.counterfactual_brancher import object_state

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x") as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write("\n")

def physical_contacts(task):
    obj=int(task.box.actor.per_scene_id)
    ids={s:{int(j[0].child_link.entity.per_scene_id) for j in getattr(task.robot,s+"_gripper")} for s in ("left","right")}
    if ids["left"] & ids["right"]:
        raise RuntimeError("left/right gripper entity IDs overlap")
    center=np.asarray(object_state(task)["pose"][:3],dtype=np.float64)
    impulses={s:np.zeros(6) for s in ids}; counts={s:0 for s in ids}
    for c in task.scene.get_contacts():
        a,b=c.bodies[0].entity,c.bodies[1].entity
        if int(a.per_scene_id)==obj: other,sign=b,1.
        elif int(b.per_scene_id)==obj: other,sign=a,-1.
        else:continue
        side=next((s for s in ids if int(other.per_scene_id) in ids[s]),None)
        if side is None:continue
        for point in c.points:
            imp=sign*np.asarray(point.impulse,dtype=np.float64)
            impulses[side][:3]+=imp
            impulses[side][3:]+=np.cross(np.asarray(point.position)-center,imp)
            counts[side]+=1
    return impulses,counts

def effects_hash(arrays):
    h=hashlib.sha256(b"r22p19.stage2g.full_effect.v1\0")
    for key in sorted(arrays):
        a=np.ascontiguousarray(arrays[key])
        if a.dtype.kind in "f" and not np.isfinite(a).all():
            raise ValueError("nonfinite effect array "+key)
        h.update(key.encode()+b"\0"+str(a.shape).encode()+b"\0"+a.dtype.str.encode()+b"\0")
        h.update(a.tobytes())
    return h.hexdigest()

def source_identity():
    root=Path(__file__).resolve().parents[3]
    files={str(p.relative_to(root)):sha(p) for p in sorted((root/"stage2_robotwin").rglob("*.py"))}
    return {"git_head":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),
            "python_source_sha256":hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
            "file_hashes":files}

def run(args):
    output=Path(args.output)
    if output.exists() or output.with_suffix(".trace.npz").exists():
        raise FileExistsError("cell output is immutable")
    if args.seed not in (0,1) or not 0<=args.gamma<=1:
        raise ValueError("calibration seeds 0,1 and gamma [0,1] only")
    pair,sidecar=load_pair_with_sidecar(args.pair_tape)
    meta=json.loads(Path(args.meta).read_text())
    if meta["seed"]!=args.seed or sha(args.source_tape)!=meta["tape_sha256"]:
        raise ValueError("source tape/seed binding failed")
    if sidecar.get("seed")!=args.seed or sidecar.get("source_tape_sha256")!=meta["tape_sha256"]:
        raise ValueError("frozen pair source/seed binding failed")
    events={k:int(v) for k,v in meta["events"].items()}
    if sidecar.get("event_window")!={"E3":events["E3"],"E5":events["E5"]}:
        raise ValueError("frozen probe event binding failed")
    if pair.physics_hz!=250:
        raise ValueError("physics contract changed")
    if args.mode=="same-frequency" and pair.frequency_left_hz!=pair.frequency_right_hz:
        raise ValueError("same-frequency needs its independently frozen equal-frequency tape")
    task=None;stack=ExitStack();handle=None;started=time.perf_counter();records=[];commands=[]
    try:
        task,kw=build_handover_block(str(args.robotwin_root),planner="mplib_screw")
        task.setup_demo(now_ep_num=int(meta["episode"]),seed=args.seed,**kw)
        frame=ObjectTaskFrame.from_task(task)
        if not np.allclose(frame.e_perp,pair.e_perp_world,atol=1e-12,rtol=0):
            raise ValueError("frozen task frame differs")
        if abs(float(task.scene.get_timestep())-1/250)>1e-8:
            raise ValueError("actual physics timestep is not 250 Hz")
        for i in range(len(pair)):
            step=int(pair.step[i]);active=events["E3"]<=step<=events["E5"]
            if step==events["E3"] and not args.without_grip:
                from stage2_robotwin.stage2g.intervention.grip_force import apply
                handle=stack.enter_context(apply(task,args.soft_arm,args.gamma))
            command={}; offsets={}
            for side in ("left","right"):
                enabled=args.mode in ("dual","same-frequency") or args.mode=="single-"+side
                pos=getattr(pair,side+"_position" if enabled else side+"_nominal_position")[i].copy()
                vel=getattr(pair,side+"_velocity")[i].copy()
                raw=getattr(pair,side+"_gripper")[i]
                grip=None if np.isnan(raw).all() else tuple(float(v) for v in raw)
                if handle is not None and active:grip=handle.route_gripper(side,grip)
                command.update({side+"_position":pos,side+"_velocity":vel,side+"_gripper":grip})
                task.robot.set_arm_joints(pos,vel,side)
                if grip is not None:task.robot.set_gripper(grip[0],side,grip[1])
                offsets[side]=float(getattr(pair,side+"_probe_offset_m")[i]) if enabled else 0.
            task.scene.step()
            if active:
                st=object_state(task); imp,counts=physical_contacts(task)
                records.append(dict(step=step,object_position=np.asarray(st["pose"][:3]).copy(),
                                    object_velocity=np.asarray(st["linear_velocity"]).copy(),
                                    object_quaternion=np.asarray(st["pose"][3:]).copy(),
                                    object_angular_velocity=np.asarray(st["angular_velocity"]).copy(),
                                    left_impulse_wrench=imp["left"],right_impulse_wrench=imp["right"],
                                    contact_counts=np.asarray([counts["left"],counts["right"]],dtype=np.int64),
                                    input_offsets=np.asarray([offsets["left"],offsets["right"]])))
                commands.append(command)
            if step==events["E5"]:
                stack.close()
        success=bool(task.check_success() and task.plan_success)
        arrays={key:np.asarray([r[key] for r in records]) for key in records[0]}
        arrays["task_success"]=np.asarray([success],dtype=np.bool_)
        arrays["left_wrench"]=arrays["left_impulse_wrench"]*250
        arrays["right_wrench"]=arrays["right_impulse_wrench"]*250
        arrays["object_e_perp"]=arrays["object_position"]@np.asarray(pair.e_perp_world)
        dual=np.all(arrays["contact_counts"]>0,axis=1)
        arrays["dual_contact"]=dual
        if len(records)!=events["E5"]-events["E3"]+1:raise RuntimeError("incomplete window")
        trace=output.with_suffix(".trace.npz");trace.parent.mkdir(parents=True,exist_ok=True)
        with trace.open("xb") as f:np.savez_compressed(f,**arrays)
        owner=trace.stat()
        if (owner.st_uid,owner.st_gid)!=(2254,2254):raise RuntimeError("wrong trace owner")
        result=dict(schema="r22p19.stage2g.probe_cell.v1",status="COMPLETE",seed=args.seed,episode=meta["episode"],
                    repeat=args.repeat,mode=args.mode,amplitude_m=pair.amplitude_m,gamma=args.gamma,soft_arm=args.soft_arm,
                    frequency_left_hz=pair.frequency_left_hz,frequency_right_hz=pair.frequency_right_hz,
                    events=events,physics_hz=250,dt_s=1/250,source_tape_sha256=meta["tape_sha256"],
                    probe_tape_sha256=sha(args.pair_tape),sidecar_sha256=sha(Path(args.pair_tape).with_suffix(".json")),
                    trace_path=str(trace),trace_sha256=sha(trace),effect_vector_sha256=effects_hash(arrays),
                    effect_vector_fields=sorted(arrays),effect_vector_definition="all_complete_window_scientific_arrays_and_task_success_no_rounding",
                    task_success=success,dual_contact_fraction=float(dual.mean()),window_samples=len(records),
                    left_command_sha256=canonical_command_sha256(commands,"left"),
                    right_command_sha256=canonical_command_sha256(commands,"right"),
                    grip_receipt=handle.receipt() if handle else None,without_grip=args.without_grip,
                    fresh_process=True,pid=os.getpid(),main_scene_restored=False,live_jacobian_used=False,
                    accepted=False,pai_job_created=False,uid=os.getuid(),gid=os.getgid(),trace_owner=[owner.st_uid,owner.st_gid],
                    source_identity=source_identity(),runtime_root=str(args.robotwin_root),wall_time_s=time.perf_counter()-started)
        save_json(output,result);print(json.dumps({k:result[k] for k in ("status","amplitude_m","effect_vector_sha256","task_success","dual_contact_fraction")}),flush=True)
        return result
    finally:
        stack.close()
        if task is not None:task.close_env(clear_cache=True)

def main():
    p=argparse.ArgumentParser()
    for key in ("robotwin-root","pair-tape","source-tape","meta","output"):p.add_argument("--"+key,type=Path,required=True)
    p.add_argument("--seed",type=int,choices=(0,1),required=True)
    p.add_argument("--repeat",type=int,default=0)
    p.add_argument("--mode",choices=("dual","single-left","single-right","none","same-frequency"),default="dual")
    p.add_argument("--gamma",type=float,default=1.)
    p.add_argument("--soft-arm",choices=("left","right"),default="left")
    p.add_argument("--without-grip",action="store_true")
    a=p.parse_args()
    try:run(a)
    except BaseException as exc:
        path=Path(a.output).with_suffix(".failure.json")
        if not path.exists():save_json(path,dict(status="FAILED",error=str(exc),traceback=traceback.format_exc(),accepted=False,pai_job_created=False))
        raise
if __name__=="__main__":main()
