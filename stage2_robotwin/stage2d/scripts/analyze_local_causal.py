from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    rows=[]
    for path in args.root.rglob("seed_*.json"):rows.extend(json.loads(path.read_text())["rows"])
    summary={}
    for method in [f"L{i}" for i in range(9)]:
        rs=[r for r in rows if r["method"]==method];summary[method]={"states":len(rs),"target_mae":float(np.mean([r["target_mae"] for r in rs])),"movement":float(np.mean([r["movement"] for r in rs])),"net_error":float(np.mean([r["net_effect_relative_error"] for r in rs])),"contact":float(np.mean([r["receiver_contact_retention"] for r in rs])),"synergy":float(np.mean([r["synergy_norm"] for r in rs])),"action_modification_ratio":float(np.mean([r.get("action_modification_ratio",0) for r in rs]))}
    correct=[r for r in rows if r["method"]=="L3"];swapped=[r for r in rows if r["method"]=="L4"]
    direction=float(np.mean([np.sign(a["movement"])==-np.sign(b["movement"]) for a,b in zip(correct,swapped)]))
    gates={"receiver_movement_ge_0p15":abs(summary["L3"]["movement"])>=0.15,"swapped_opposite_rate_ge_0p8":direction>=0.8,
        "correct_beats_shuffled_shifted":summary["L3"]["target_mae"]<min(summary["L5"]["target_mae"],summary["L6"]["target_mae"]),"tracking_mae_le_0p15":summary["L3"]["target_mae"]<=0.15,
        "net_error_le_0p10":summary["L3"]["net_error"]<=0.10,"internal_not_above_base":summary["L8"]["synergy"]<=summary["L0"]["synergy"],"contact_unchanged":summary["L3"]["contact"]>=summary["L0"]["contact"],"action_modification_5_to_30pct":0.05<=summary["L3"]["action_modification_ratio"]<=0.30,"effect_exceeds_null_floor":abs(summary["L3"]["movement"])>1e-6}
    result={"rows":len(rows),"summary":summary,"swapped_opposite_rate":direction,"gates":gates,"decision":"LOCAL_GO" if all(gates.values()) else "LOCAL_NO_GO","accepted":False,"pai_job_created":False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n");print(json.dumps({"decision":result["decision"],"gates":gates},indent=2))
if __name__=="__main__":main()
