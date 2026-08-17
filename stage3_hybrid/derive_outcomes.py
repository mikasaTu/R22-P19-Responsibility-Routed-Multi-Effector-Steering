from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from stage3_hybrid.outcomes.disturbance_metrics import trajectory_rmse
from stage3_hybrid.outcomes.takeover_label import takeover_success


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(); completion=json.loads((args.root/"completion.json").read_text())
    if not completion["matrix_complete"]: raise RuntimeError("derived outcomes refuse incomplete matrix")
    rows=[json.loads(path.read_text()) for path in sorted((args.root/"cells").glob("*.json"))]
    groups=defaultdict(list)
    for row in rows: groups[(row["condition"],row["seed"],row["repeat"])].append(row)
    derived=[]
    for group,cells in sorted(groups.items()):
        if len(cells)!=6: raise RuntimeError(f"missing mode in {group}")
        base=next(row for row in cells if row["mode"]=="M0_BASE")
        base_trace=np.load(args.root/"cells"/base["trace"])["object_position"]
        for row in cells:
            trace=np.load(args.root/"cells"/row["trace"])["object_position"]
            metrics=dict(row["metrics"])
            metrics["trajectory_rmse_to_base_m"]=trajectory_rmse(trace,base_trace)
            metrics["takeover_success"]=takeover_success(metrics)
            derived.append({"condition":row["condition"],"seed":row["seed"],"repeat":row["repeat"],
                            "mode":row["mode"],"trajectory_rmse_to_base_m":metrics["trajectory_rmse_to_base_m"],
                            "takeover_success":metrics["takeover_success"]})
    result={"schema":"r22p19.stage3a.derived_outcomes.v1","cell_count":len(derived),"cells":derived,
            "accepted":False,"pai_job_count":0}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(f"STAGE3_DERIVED cells={len(derived)}"); return 0


if __name__=="__main__": raise SystemExit(main())
