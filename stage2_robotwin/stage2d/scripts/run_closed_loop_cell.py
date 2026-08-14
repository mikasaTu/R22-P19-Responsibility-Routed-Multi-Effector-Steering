"""One fresh-process active-handover closed-loop diagnostic cell."""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import time
import numpy as np
import yaml

from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import task_direction_joint_delta
from stage2_robotwin.stage2c.replay.fresh_prefix_runner import ConditionOverride
from stage2_robotwin.stage2d.capacity.channel_capacity import score_channels
from stage2_robotwin.stage2d.operator.desired_responsibility_state import DesiredResponsibilityState
from stage2_robotwin.stage2d.operator.robotwin_effect import task_effect_joint_delta
from stage2_robotwin.stage2d.scripts.run_capacity_audit import _active_item
from stage2_robotwin.responsibility.oracle_brancher import _contact_impulses
from stage2_robotwin.wrappers.counterfactual_brancher import gripper_object_contacts, object_state
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n")


def _capacity_trace(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    receiver_index = 0 if data["receiver"] == "left" else 1
    state = DesiredResponsibilityState(max_slew=0.08)
    rows = []
    for item in data["states"]:
        outcomes = item["rollout"]["outcomes"]
        full = outcomes["1.0"]
        capacity = float(np.mean([score_channels(full, outcomes[str(level)], receiver_index).full
                                  for level in (0.75, 0.5, 0.25)]))
        phase = float(item["normalized_phase"])
        rows.append({"phase": phase, "capacity": capacity,
                     "target": state.update(capacity, phase, True)})
    return rows


def _nearest(trace, phase, key):
    return float(min(trace, key=lambda x: abs(x["phase"]-phase))[key])


def _receiver_target(method, phase, contacts, impulses, correct, shuffled, shifted):
    if method in {"C0", "C4", "C6", "C12", "C15"}: return 0.5
    if method in {"C1", "C7"}: return float(np.clip(0.1+0.8*phase, 0.1, 0.9))
    if method == "C2": return float(np.clip(0.1+0.8*phase, 0.1, 0.9)) if contacts else 0.1
    if method in {"C3", "C5"}:
        total = impulses[0]+impulses[1]
        return float(impulses[1]/total) if total > 1e-12 else 0.5
    if method in {"C8", "C13", "C14"}: return correct
    if method == "C9": return shuffled
    if method == "C10": return shifted
    if method == "C11": return 1.0-correct
    raise ValueError(method)


def run(args):
    config = yaml.safe_load(args.config.read_text())
    meta = json.loads(args.tape_meta.read_text())
    tape = ExpertTape.load(args.tape)
    condition_spec = config["conditions"][args.condition]
    condition = dict(condition_spec["parameters"])
    amplitude = float(condition_spec["active_amplitude_m"])
    donor, receiver = meta["donor"], meta["receiver"]
    receiver_index = 0 if receiver == "left" else 1
    events = {k:int(v) for k,v in meta["events"].items()}
    capacity = _capacity_trace(args.capacity_file)
    shuffled = _capacity_trace(args.shuffled_capacity_file)
    shifted_targets = np.roll([r["target"] for r in capacity], 2)
    for row, target in zip(capacity, shifted_targets): row["shifted"] = float(target)
    v1_trace = None
    if args.v1_trace_file is not None:
        local = json.loads(args.v1_trace_file.read_text())
        v1_trace = [{"phase": float(row["phase"]), "target": float(row["base_actual"])}
                    for row in local["rows"] if row["method"] == "L0"]
    task = override = None
    started = time.perf_counter()
    try:
        task, kwargs = build_handover_block(str(args.robotwin_root), planner="mplib_screw")
        task.setup_demo(now_ep_num=int(meta["episode"]), seed=int(meta["seed"]), **kwargs)
        frame = ObjectTaskFrame.from_task(task)
        override = ConditionOverride(task, receiver, condition, frame)
        delay = deque()
        initial_receiver = None
        positions=[]; references=[]; contacts_log=[]; impulses_log=[]; heights=[]; target_log=[]; mods=[]
        ref_origin = None; blocked_release=0; release_requests=0; premature_release=0
        for index in range(len(tape)):
            raw = tape.item(index); step=int(raw["step"])
            if step == events["E2"]: override.apply()
            item, active_offset = _active_item(task, raw, step, events, frame, amplitude)
            active = events["E3"] <= step <= events["E5"]
            if active and initial_receiver is None:
                joints = task.robot.left_arm_joints if receiver == "left" else task.robot.right_arm_joints
                initial_receiver = (np.asarray([j.get_drive_target()[0] for j in joints]),
                                    np.asarray([j.get_drive_velocity_target()[0] for j in joints]))
            if active and float(condition.get("receiver_gain",1.0)) != 1.0:
                measured=np.asarray((task.robot.get_left_arm_real_jointState() if receiver=="left" else task.robot.get_right_arm_real_jointState())[:-1])
                gain=float(condition["receiver_gain"]); p=np.asarray(item[f"{receiver}_position"]); v=np.asarray(item[f"{receiver}_velocity"])
                item[f"{receiver}_position"]=measured+gain*(p-measured); item[f"{receiver}_velocity"]=gain*v
            delay_steps=int(condition.get("receiver_delay_steps",0))
            if active and delay_steps:
                delay.append((item[f"{receiver}_position"],item[f"{receiver}_velocity"]))
                item[f"{receiver}_position"],item[f"{receiver}_velocity"] = initial_receiver if len(delay)<=delay_steps else delay.popleft()
            contact = gripper_object_contacts(task); impulse=_contact_impulses(task)
            phase=(step-events["E3"])/max(events["E5"]-events["E3"],1)
            if active:
                correct=_nearest(capacity,phase,"target"); shuf=_nearest(shuffled,phase,"target"); shifted=_nearest(capacity,phase,"shifted")
                receiver_impulse=float(impulse[receiver]); donor_impulse=float(impulse[donor])
                target=_receiver_target(args.method,phase,contact[receiver],
                    (donor_impulse,receiver_impulse),correct,shuf,shifted)
                if args.method == "C5" and v1_trace is not None:
                    target = _nearest(v1_trace, phase, "target")
                if args.method not in {"C0","C4","C6","C12","C15"}:
                    magnitude=float(config["operator"]["correction_amplitude_m"])*(target-0.5)
                    if args.method=="C14": magnitude*=0.75
                    if args.method in {"C13","C14"}:
                        effect4=np.asarray([0.25*magnitude,magnitude,0.10*magnitude,0.50*magnitude])
                        delta_r,_=task_effect_joint_delta(task,receiver,frame,effect4,max_joint_delta_rad=0.08)
                        delta_d,_=task_effect_joint_delta(task,donor,frame,-effect4,max_joint_delta_rad=0.08)
                    else:
                        delta_r,_=task_direction_joint_delta(task,receiver,frame.e_perp,magnitude,max_joint_delta_rad=0.08)
                        delta_d,_=task_direction_joint_delta(task,donor,frame.e_perp,-magnitude,max_joint_delta_rad=0.08)
                    item[f"{receiver}_position"]=np.asarray(item[f"{receiver}_position"])+delta_r
                    item[f"{donor}_position"]=np.asarray(item[f"{donor}_position"])+delta_d
                    mods.append(float(np.linalg.norm(delta_r)+np.linalg.norm(delta_d)))
                else: mods.append(0.0)
                target_log.append(target)
            commands={side:item[f"{side}_gripper"] for side in ("left","right")}
            if commands[donor] is not None and commands[donor][0] > 0.2:
                release_requests += 1
                guard = args.method in {"C4","C6","C13","C14"}
                current_target=target_log[-1] if target_log else 0.0
                if guard and (not contact[receiver] or current_target < 0.5):
                    commands[donor]=None; blocked_release += 1
                elif not contact[receiver]: premature_release += 1
            for side in ("left","right"):
                task.robot.set_arm_joints(np.asarray(item[f"{side}_position"]),np.asarray(item[f"{side}_velocity"]),side)
                if commands[side] is not None: task.robot.set_gripper(commands[side][0],side,commands[side][1])
            task.scene.step()
            if active:
                state=object_state(task); pos=state["pose"][:3]
                if ref_origin is None: ref_origin=pos.copy()
                positions.append(pos); references.append(ref_origin+active_offset*np.asarray(frame.e_perp))
                c=gripper_object_contacts(task); contacts_log.append([c["left"],c["right"]])
                im=_contact_impulses(task); impulses_log.append([im["left"],im["right"]]); heights.append(pos[2])
        pos=np.asarray(positions); ref=np.asarray(references); contacts_arr=np.asarray(contacts_log); impulses_arr=np.asarray(impulses_log)
        result={"status":"COMPLETE","seed":int(meta["seed"]),"method":args.method,"condition":args.condition,
                "condition_eligible":bool(condition_spec["eligible"]),"condition_reason":condition_spec["reason"],
                "success":bool(task.plan_success and task.check_success()),
                "trajectory_rmse_m":float(np.sqrt(np.mean(np.sum((pos-ref)**2,axis=1)))),
                "contact_retention":float(np.mean(contacts_arr[:,receiver_index])),
                "dual_contact_fraction":float(np.mean(np.all(contacts_arr,axis=1))),
                "min_object_height_m":float(np.min(heights)),
                "internal_force_proxy":float(np.mean(np.abs(impulses_arr[:,0]-impulses_arr[:,1]))),
                "impulse_spike":float(np.max(impulses_arr)),"premature_release":premature_release,
                "release_requests":release_requests,"release_guard_blocked":blocked_release,
                "mean_target_receiver_share":float(np.mean(target_log)),"responsibility_slew":float(np.sum(np.abs(np.diff(target_log)))),
                "mean_joint_action_modification_rad":float(np.mean(mods)),"solver_latency_s":0.0,
                "capacity_source":str(args.capacity_file),"v1_trace_source":str(args.v1_trace_file) if args.v1_trace_file else None,
                "fresh_process":True,"total_wall_time_s":time.perf_counter()-started,
                "accepted":False,"pai_job_created":False,
                "limitation":"target share is commanded allocation; actual contribution requires separate local branch audit"}
        _write(args.output/"result.json",result); return result
    finally:
        if override is not None: override.close()
        if task is not None:
            try: task.close_env(clear_cache=True)
            except Exception: pass


def main():
    p=argparse.ArgumentParser(); p.add_argument("--robotwin-root",type=Path,required=True); p.add_argument("--config",type=Path,required=True)
    p.add_argument("--tape",type=Path,required=True); p.add_argument("--tape-meta",type=Path,required=True); p.add_argument("--capacity-file",type=Path,required=True)
    p.add_argument("--shuffled-capacity-file",type=Path,required=True); p.add_argument("--v1-trace-file",type=Path); p.add_argument("--method",required=True); p.add_argument("--condition",required=True); p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(); run(args)
if __name__=="__main__": main()
