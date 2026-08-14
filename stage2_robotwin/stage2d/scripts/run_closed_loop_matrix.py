from __future__ import annotations

import argparse, concurrent.futures, json, os, subprocess, sys, threading
from pathlib import Path
import yaml

from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")


def capacity_files(root: Path):
    found={}
    for path in root.rglob("seed_*.json"):
        data=json.loads(path.read_text()); found[int(data["seed"])]=path
    return found


def main():
    p=argparse.ArgumentParser(); p.add_argument("--robotwin-root",type=Path,required=True); p.add_argument("--tape-root",type=Path,required=True)
    p.add_argument("--config",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--gpus",type=int,nargs="+",default=[1,2]); p.add_argument("--only-methods",nargs="+"); p.add_argument("--v1-root",type=Path)
    args=p.parse_args(); config=yaml.safe_load(args.config.read_text()); args.output.mkdir(parents=True,exist_ok=True)
    tapes=discover_tapes(args.tape_root); seeds=[int(x) for x in config["seeds"]]; methods=list(config["methods"])
    if methods != [f"C{i}" for i in range(16)]: raise ValueError("method contract changed")
    selected_methods=list(args.only_methods or methods)
    if not set(selected_methods)<=set(methods): raise ValueError("unknown selected method")
    caps={name:capacity_files(Path(spec["capacity_root"])) for name,spec in config["conditions"].items()}
    v1_files=capacity_files(args.v1_root) if args.v1_root else {}
    cells=[]; index=0
    for condition in config["conditions"]:
        for seed_index,seed in enumerate(seeds):
            shuffled=seeds[(seed_index+1)%len(seeds)]
            for method in selected_methods:
                output=args.output/f"seed_{seed:04d}__{condition}__{method}"
                cells.append({"seed":seed,"condition":condition,"method":method,"gpu":args.gpus[index%len(args.gpus)],"output":output,
                              "tape":tapes[seed][0],"meta":tapes[seed][1],"capacity":caps[condition][seed],"shuffled":caps[condition][shuffled],
                              "v1":v1_files.get(seed)})
                index+=1
    locks={g:threading.Lock() for g in args.gpus}; repo=Path(__file__).resolve().parents[3]; receipts=[]
    def run(cell):
        result=cell["output"]/"result.json"
        if result.is_file(): return {"status":"REUSED_COMPLETE","returncode":0}
        cell["output"].mkdir(parents=True,exist_ok=True); env=os.environ.copy(); env["CUDA_VISIBLE_DEVICES"]=str(cell["gpu"]); env["PYTHONDONTWRITEBYTECODE"]="1"
        command=[sys.executable,"-m","stage2_robotwin.stage2d.scripts.run_closed_loop_cell","--robotwin-root",str(args.robotwin_root),"--config",str(args.config),"--tape",str(cell["tape"]),"--tape-meta",str(cell["meta"]),"--capacity-file",str(cell["capacity"]),"--shuffled-capacity-file",str(cell["shuffled"]),"--method",cell["method"],"--condition",cell["condition"],"--output",str(cell["output"])]
        if cell["v1"] is not None: command.extend(["--v1-trace-file",str(cell["v1"])])
        with locks[cell["gpu"]]: completed=subprocess.run(command,cwd=repo,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (cell["output"]/"runtime.log").write_text(completed.stdout)
        return {"status":"COMPLETE" if completed.returncode==0 and result.is_file() else "FAILED","returncode":completed.returncode}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        future_map={pool.submit(run,c):c for c in cells}
        for count,future in enumerate(concurrent.futures.as_completed(future_map),1):
            cell=future_map[future]; receipt={"seed":cell["seed"],"condition":cell["condition"],"method":cell["method"],"gpu":cell["gpu"],**future.result()}; receipts.append(receipt)
            write(args.output/"receipts.partial.json",receipts); print(f"CLOSED_LOOP {count}/{len(cells)} {receipt}",flush=True)
    write(args.output/"receipts.json",receipts)
    return 0 if all(r["status"] in {"COMPLETE","REUSED_COMPLETE"} for r in receipts) else 1
if __name__=="__main__": raise SystemExit(main())
