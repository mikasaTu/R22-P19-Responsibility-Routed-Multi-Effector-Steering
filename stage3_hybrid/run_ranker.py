from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from stage3_hybrid.baselines import oracle
from stage3_hybrid.ranker import feature_vector


def outcome_key(row):
    m=row["metrics"]
    return (int(m["eventual_task_success"]),int(not m["drop"]),int(not m["takeover_failure"]),
            -float(m["peak_relative_slip_m"]),-float(m["peak_object_linear_jerk"]),-float(m["donor_action_deviation_mean"]))


def load_rows(roots):
    rows=[]
    for root in roots:
        completion=json.loads((root/"completion.json").read_text())
        if not completion["matrix_complete"]: raise RuntimeError(f"incomplete matrix {root}")
        rows += [json.loads(p.read_text()) for p in sorted((root/"cells").glob("*.json"))]
    return rows


def groups(rows):
    result=defaultdict(list)
    for row in rows: result[(row["condition"],row["seed"],row["repeat"])].append(row)
    if any(len(cells)!=6 for cells in result.values()): raise RuntimeError("ranker requires six complete modes per group")
    return result


def fit_logistic(x,y,l2=.1,steps=50):
    x=np.asarray(x,float); y=np.asarray(y,float); mean=x.mean(0); scale=x.std(0); scale[scale<1e-8]=1
    z=(x-mean)/scale; design=np.column_stack([np.ones(len(z)),z]); w=np.zeros(design.shape[1])
    penalty=np.eye(len(w))*l2; penalty[0,0]=0
    for _ in range(steps):
        p=1/(1+np.exp(-np.clip(design@w,-30,30))); grad=design.T@(p-y)+penalty@w
        h=design.T@((p*(1-p))[:,None]*design)+penalty+np.eye(len(w))*1e-8
        delta=np.linalg.solve(h,grad); w-=delta
        if np.linalg.norm(delta)<1e-9: break
    return {"weights":w.tolist(),"mean":mean.tolist(),"scale":scale.tolist(),"l2":l2}


def utility(model, row, horizon, feature_override=None):
    x=feature_vector(row,horizon) if feature_override is None else feature_override
    z=(x-np.asarray(model["mean"]))/np.asarray(model["scale"])
    return float(np.asarray(model["weights"])[0]+z@np.asarray(model["weights"])[1:])


def main():
    p=argparse.ArgumentParser(); p.add_argument("--calibration-roots",type=Path,nargs="+",required=True); p.add_argument("--heldout-root",type=Path,required=True); p.add_argument("--heldout-analysis",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(); heldout_gate=json.loads(args.heldout_analysis.read_text())
    if heldout_gate["decision"]!="ORACLE_UPPER_BOUND_GO_SHORT_HORIZON_PENDING": raise RuntimeError("ranker prohibited before oracle upper-bound GO")
    train_groups=groups(load_rows(args.calibration_roots)); test_groups=groups(load_rows([args.heldout_root])); passing=set(heldout_gate["passing_stresses"])
    reports=[]
    for horizon in (50,100,200):
        x=[]; y=[]
        for (condition,seed,repeat),cells in train_groups.items():
            if condition=="clean" or condition not in passing: continue
            for i in range(len(cells)):
                for j in range(i+1,len(cells)):
                    if outcome_key(cells[i])==outcome_key(cells[j]): continue
                    delta=feature_vector(cells[i],horizon)-feature_vector(cells[j],horizon)
                    label=float(outcome_key(cells[i])>outcome_key(cells[j])); x.extend([delta,-delta]); y.extend([label,1-label])
        if not x: raise RuntimeError("no non-tied calibration pairs")
        model=fit_logistic(x,y); pair_correct=[]; selections=[]
        for group_key,cells in sorted(test_groups.items()):
            condition,seed,repeat=group_key
            if condition!="clean" and condition not in passing: continue
            for i in range(len(cells)):
                for j in range(i+1,len(cells)):
                    if outcome_key(cells[i])==outcome_key(cells[j]): continue
                    predicted=utility(model,cells[i],horizon)>utility(model,cells[j],horizon)
                    pair_correct.append(int(predicted==(outcome_key(cells[i])>outcome_key(cells[j]))))
            selected=max(cells,key=lambda row:utility(model,row,horizon)); base=next(row for row in cells if row["mode"]=="M0_BASE"); best=oracle(cells)
            selections.append({"condition":condition,"seed":seed,"repeat":repeat,"selected":selected["mode"],"oracle":best["mode"],
                               "selected_success":int(selected["metrics"]["eventual_task_success"]),"base_success":int(base["metrics"]["eventual_task_success"]),
                               "oracle_success":int(best["metrics"]["eventual_task_success"]),"selected_drop":int(selected["metrics"]["drop"])})
        stress=[r for r in selections if r["condition"]!="clean"]; clean=[r for r in selections if r["condition"]=="clean"]
        base=float(np.mean([r["base_success"] for r in stress])); selected=float(np.mean([r["selected_success"] for r in stress])); upper=float(np.mean([r["oracle_success"] for r in stress]))
        recovered=(selected-base)/max(upper-base,1e-12); accuracy=float(np.mean(pair_correct)); clean_drop=float(np.mean([r["selected_drop"] for r in clean]))
        # Wrong-mapping controls use the same branch budget and rotate candidate utilities.
        shuffled=[]; shifted=[]
        for _,cells in sorted(test_groups.items()):
            scores=[utility(model,row,horizon) for row in cells]
            shuffled.extend([int((scores[(i+1)%6]>scores[(j+1)%6])==(outcome_key(cells[i])>outcome_key(cells[j]))) for i in range(6) for j in range(i+1,6) if outcome_key(cells[i])!=outcome_key(cells[j])])
            other={50:100,100:200,200:50}[horizon]; alt=[utility(model,row,horizon,feature_vector(row,other)) for row in cells]
            shifted.extend([int((alt[i]>alt[j])==(outcome_key(cells[i])>outcome_key(cells[j]))) for i in range(6) for j in range(i+1,6) if outcome_key(cells[i])!=outcome_key(cells[j])])
        shuffled_acc=float(np.mean(shuffled)); shifted_acc=float(np.mean(shifted))
        passed=accuracy>=.70 and recovered>=.70 and selected-base>=.10 and accuracy>shuffled_acc and accuracy>shifted_acc and clean_drop<=.03 and len(passing)>=2
        reports.append({"horizon":horizon,"model":model,"pairwise_accuracy":accuracy,"shuffled_accuracy":shuffled_acc,"time_shifted_accuracy":shifted_acc,
                        "base_success":base,"selected_success":selected,"oracle_success":upper,"success_gain":selected-base,
                        "recovered_oracle_gain_fraction":recovered,"clean_drop_rate":clean_drop,"stress_count":len(passing),"passed":passed,"selections":selections})
    decision="HYBRID_ROUTING_SIGNAL_GO" if any(r["passed"] for r in reports) else "SHORT_HORIZON_SIGNAL_WEAK"
    result={"schema":"r22p19.stage3a.ranker.v1","decision":decision,"horizons":reports,"accepted":False,"pai_job_count":0}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); print(f"STAGE3_RANKER {decision}"); return 0


if __name__=="__main__": raise SystemExit(main())
