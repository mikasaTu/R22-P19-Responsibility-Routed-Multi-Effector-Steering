"""Actual SAPIEN local branch audit for L0--L8 at active handover states."""
from __future__ import annotations

import argparse, json, time, traceback
from pathlib import Path
import numpy as np

from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import task_direction_joint_delta
from stage2_robotwin.stage2d.scripts.run_capacity_audit import _active_item, _drive
from stage2_robotwin.stage2d.scripts.run_closed_loop_cell import _capacity_trace, _nearest
from stage2_robotwin.responsibility.oracle import decompose_outcomes
from stage2_robotwin.responsibility.oracle_brancher import capture_outcome_origin, measure_outcome, _joint_neutral_state
from stage2_robotwin.wrappers.counterfactual_brancher import SapienSnapshot, gripper_object_contacts
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


METHODS=[f"L{i}" for i in range(9)]


def write(path,value): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")


def _rollouts(task,snapshot,future,frame,donor,receiver,target,scale=1.0):
    outcomes={}; origin=None; ratios=[]
    for branch in ("LR","L","R","ZERO"):
        SapienSnapshot.restore(task,snapshot)
        if origin is None: origin=capture_outcome_origin(task)
        neutral={s:_joint_neutral_state(task,s) for s in ("left","right")}
        for item in future:
            targets={s:(np.asarray(item[f"{s}_position"]).copy(),np.asarray(item[f"{s}_velocity"]).copy()) for s in ("left","right")}
            magnitude=0.012*(target-0.5)*scale
            if abs(magnitude)>1e-12:
                dr,_=task_direction_joint_delta(task,receiver,frame.e_perp,magnitude,max_joint_delta_rad=0.08)
                dd,_=task_direction_joint_delta(task,donor,frame.e_perp,-magnitude,max_joint_delta_rad=0.08)
                targets[receiver]=(targets[receiver][0]+dr,targets[receiver][1]); targets[donor]=(targets[donor][0]+dd,targets[donor][1])
                denominator=sum(np.linalg.norm(targets[s][0]-neutral[s][0]) for s in ("left","right"))
                ratios.append(float((np.linalg.norm(dr)+np.linalg.norm(dd))/max(denominator,1e-9)))
            active={"left":branch in {"LR","L"},"right":branch in {"LR","R"}}
            for side in ("left","right"): task.robot.set_arm_joints(*(targets[side] if active[side] else neutral[side]),side)
            task.scene.step()
        outcomes[branch]=measure_outcome(task,origin)
    SapienSnapshot.restore(task,snapshot); return outcomes, float(np.mean(ratios)) if ratios else 0.0


def audit_seed(robotwin_root,tape_path,meta_path,cap_path,shuf_path,states,horizon):
    tape=ExpertTape.load(tape_path); meta=json.loads(meta_path.read_text()); seed=int(meta["seed"]); events={k:int(v) for k,v in meta["events"].items()}
    donor,receiver=meta["donor"],meta["receiver"]; receiver_key="rho_left" if receiver=="left" else "rho_right"
    cap=_capacity_trace(cap_path); shuf=_capacity_trace(shuf_path); shifted=np.roll([x["target"] for x in cap],2)
    for row,value in zip(cap,shifted): row["shifted"]=float(value)
    points=set(np.linspace(events["E3"],events["E4"],states,dtype=int).tolist()); task=oracle=None; rows=[]; started=time.perf_counter()
    try:
        task,kwargs=build_handover_block(str(robotwin_root),planner="mplib_screw"); task.setup_demo(now_ep_num=int(meta["episode"]),seed=seed,**kwargs)
        oracle,okw=build_handover_block(str(robotwin_root),planner="mplib_screw"); oracle.setup_demo(now_ep_num=int(meta["episode"]),seed=seed,**okw)
        frame=ObjectTaskFrame.from_task(task)
        for index in range(len(tape)):
            raw=tape.item(index); step=int(raw["step"]); item,_=_active_item(task,raw,step,events,frame,0.015); _drive(task,item)
            if step not in points: continue
            phase=(step-events["E3"])/max(events["E5"]-events["E3"],1); snapshot=SapienSnapshot.capture(task); SapienSnapshot.restore(oracle,snapshot)
            future=[]
            for j in range(index+1,min(len(tape),index+1+horizon)):
                rawf=tape.item(j); mod,_=_active_item(task,rawf,int(rawf["step"]),events,frame,0.015); future.append(mod)
            base_out,base_mod=_rollouts(oracle,snapshot,future,frame,donor,receiver,0.5); base_decomp=decompose_outcomes(base_out); base_share=float(base_decomp["three_channel"][receiver_key])
            correct=_nearest(cap,phase,"target"); targets={"L0":0.5,"L1":0.1+0.8*phase,"L2":0.1+0.8*phase,"L3":correct,"L4":1-correct,
                "L5":_nearest(shuf,phase,"target"),"L6":_nearest(cap,phase,"shifted"),"L7":base_share,"L8":correct}
            base_vec=np.r_[base_out["LR"]["translation"],base_out["LR"]["rotation_vector"]]
            for method in METHODS:
                if method=="L0": out,modification=base_out,base_mod
                else: out,modification=_rollouts(oracle,snapshot,future,frame,donor,receiver,targets[method],0.75 if method=="L8" else 1.0)
                decomp=base_decomp if method=="L0" else decompose_outcomes(out); actual=float(decomp["three_channel"][receiver_key]); vec=np.r_[out["LR"]["translation"],out["LR"]["rotation_vector"]]
                rows.append({"seed":seed,"step":step,"phase":phase,"method":method,"target":float(targets[method]),"base_actual":base_share,"actual":actual,
                    "movement":actual-base_share,"target_mae":abs(actual-targets[method]),"net_effect_relative_error":float(np.linalg.norm(vec-base_vec)/max(np.linalg.norm(base_vec),1e-9)),
                    "receiver_contact_retention":float(out["LR"]["contact_retention"][0 if receiver=="left" else 1]),"drop":bool(out["LR"]["drop"]),
                    "synergy_norm":float(np.linalg.norm(decomp["motion"]["synergy"])),"action_modification_ratio":modification})
        return {"status":"COMPLETE","seed":seed,"states":states,"methods":METHODS,"rows":rows,"wall_time_s":time.perf_counter()-started,"fresh_main_scene":True,"disjoint_oracle_scene":True,"accepted":False,"pai_job_created":False}
    finally:
        for value in (oracle,task):
            if value is not None:
                try:value.close_env(clear_cache=True)
                except Exception:pass


def main():
    p=argparse.ArgumentParser(); p.add_argument("--robotwin-root",type=Path,required=True); p.add_argument("--tape-root",type=Path,required=True); p.add_argument("--capacity-root",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--seeds",type=int,nargs="+",required=True); p.add_argument("--states",type=int,default=5); p.add_argument("--horizon",type=int,default=20); args=p.parse_args()
    tapes=discover_tapes(args.tape_root); caps={json.loads(x.read_text())["seed"]:x for x in args.capacity_root.rglob("seed_*.json")}; allseeds=sorted(caps); receipts=[]
    for seed in args.seeds:
        try:
            shuf=allseeds[(allseeds.index(seed)+1)%len(allseeds)]; result=audit_seed(args.robotwin_root,*tapes[seed],caps[seed],caps[shuf],args.states,args.horizon); write(args.output/f"seed_{seed:04d}.json",result); receipts.append({"seed":seed,"status":"COMPLETE"})
        except Exception as exc: receipts.append({"seed":seed,"status":"FAILED","error":str(exc),"traceback":traceback.format_exc()})
        write(args.output/"receipts.json",receipts); print(f"LOCAL_CAUSAL seed={seed} {receipts[-1]['status']}",flush=True)
    return 0 if all(x["status"]=="COMPLETE" for x in receipts) else 1
if __name__=="__main__":raise SystemExit(main())
