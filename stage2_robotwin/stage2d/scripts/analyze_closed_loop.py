from __future__ import annotations

import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,action="append",required=True); p.add_argument("--output",type=Path,required=True); args=p.parse_args()
    keyed={}
    for root in args.root:
        for path in sorted(root.glob("*/result.json")):
            row=json.loads(path.read_text()); keyed[(row["seed"],row["condition"],row["method"])]=row
    rows=list(keyed.values())
    grouped=defaultdict(list)
    for row in rows: grouped[(row["condition"],row["method"])].append(row)
    summary={}
    for (condition,method), values in sorted(grouped.items()):
        summary[f"{condition}/{method}"]={"episodes":len(values),"success_rate":float(np.mean([v["success"] for v in values])),
            "trajectory_rmse_m":float(np.mean([v["trajectory_rmse_m"] for v in values])),"contact_retention":float(np.mean([v["contact_retention"] for v in values])),
            "internal_force_proxy":float(np.mean([v["internal_force_proxy"] for v in values])),"action_modification_rad":float(np.mean([v["mean_joint_action_modification_rad"] for v in values]))}
    comparisons={}
    for condition in sorted({r["condition"] for r in rows}):
        def val(method,key): return summary[f"{condition}/{method}"][key]
        if not all(f"{condition}/C{i}" in summary for i in range(16)):
            comparisons[condition]={"status":"INCOMPLETE_CONDITION"}
            continue
        comparisons[condition]={"full_vs_base_success_pp":100*(val("C13","success_rate")-val("C0","success_rate")),
            "full_vs_conservation_success_pp":100*(val("C13","success_rate")-val("C12","success_rate")),
            "correct_vs_swapped_success_pp":100*(val("C8","success_rate")-val("C11","success_rate")),
            "correct_vs_shuffled_success_pp":100*(val("C8","success_rate")-val("C9","success_rate")),
            "correct_vs_shifted_success_pp":100*(val("C8","success_rate")-val("C10","success_rate")),
            "internal_suppression_delta":val("C14","internal_force_proxy")-val("C13","internal_force_proxy")}
    result={"schema":"r22p19-stage2d-closed-loop-v1","completed_cells":len(rows),"expected_cells":320,"complete":len(rows)==320,
            "summary":summary,"comparisons":comparisons,"accepted":False,"pai_job_created":False,
            "evidence_boundary":"actual SAPIEN task metrics; commanded allocation proxy is not measured contribution",
            "source_roots":[str(root) for root in args.root],
            "cells":sorted(rows,key=lambda row:(row["condition"],row["seed"],row["method"]))}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"completed_cells":len(rows),"comparisons":comparisons},indent=2))
if __name__=="__main__": main()
