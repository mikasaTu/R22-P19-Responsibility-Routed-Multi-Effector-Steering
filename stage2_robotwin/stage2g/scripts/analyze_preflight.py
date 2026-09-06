"""Analyze only the preregistered Delivery-1 smoke; never decide P1/P2."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from stage2_robotwin.stage2g.analysis.authority_ratio import authority_ratio
from stage2_robotwin.stage2g.analysis.wrench_decomposition import trajectory_wrench_decomposition
from stage2_robotwin.stage2g.scripts.preflight_gates import amplitude_selection
from stage2_robotwin.stage2g.scripts.run_probe_cell import effects_hash

def analyze_cell(path):
    c=json.loads(path.read_text())
    if c["status"]!="COMPLETE":raise ValueError("incomplete cell")
    trace=Path(c["trace_path"])
    if not trace.exists():trace=path.parent/trace.name
    if hashlib.sha256(trace.read_bytes()).hexdigest()!=c["trace_sha256"]:raise ValueError("trace checksum")
    with np.load(trace,allow_pickle=False) as z:a={k:z[k] for k in z.files}
    if effects_hash(a)!=c["effect_vector_sha256"]:raise ValueError("effect bytes checksum")
    r=authority_ratio(a["object_e_perp"],250,f_soft=c["frequency_left_hz"],f_receiver=c["frequency_right_hz"],
                      reference_soft=a["input_offsets"][:,0],reference_receiver=a["input_offsets"][:,1])
    w=trajectory_wrench_decomposition(a["left_wrench"],a["right_wrench"])
    valid=w["valid"]
    return dict(cell_path=str(path),cell_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),amplitude_m=c["amplitude_m"],
                task_success=c["task_success"],dual_contact_fraction=c["dual_contact_fraction"],
                spectral_snr=[r.get("snr_soft"),r.get("snr_receiver")],authority=r,
                internal_wrench_ratio_mean=float(np.mean(w["internal_fraction"][valid])) if valid.any() else None,
                internal_wrench_valid_steps=int(valid.sum()),window_samples=c["window_samples"],
                mean_net_wrench_norm=float(np.linalg.norm(w["w_ext"],axis=1).mean()),
                mean_internal_wrench_norm=float(np.linalg.norm(w["w_int"],axis=1).mean()),
                effect_vector_sha256=c["effect_vector_sha256"],
                confidence_interval_95=None,ci_reason="one episode per smoke condition; repeat is deterministic replay, not independent episodes",
                accepted=False,pai_job_created=False)

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    reps=[json.loads((a.root/("repeat"+str(i)+".json")).read_text()) for i in (0,1)]
    same=all(reps[0][k]==reps[1][k] for k in ("probe_tape_sha256","gamma","seed","mode","soft_arm","effect_vector_sha256","left_command_sha256","right_command_sha256"))
    repeat=dict(bitwise_passed=same,separate_pids=reps[0]["pid"]!=reps[1]["pid"],hashes=[x["effect_vector_sha256"] for x in reps],
                input_probe_sha256=reps[0]["probe_tape_sha256"],source_pids=[x["pid"] for x in reps])
    if not repeat["separate_pids"]:raise ValueError("repeat was not fresh-process")
    rows=[analyze_cell(a.root/("amplitude_"+x+".json")) for x in ("003","005","008")]
    selection=amplitude_selection(rows,repeat_bitwise_passed=same)
    out=dict(schema="r22p19.stage2g.delivery1_preflight.v1",repeatability=repeat,amplitude_selection=selection,
             phase_I_executed=False,phase_II_executed=False,scientific_P1_decision=None,scientific_P2_decision=None,
             stage2f_retrospective_wrench="NOT_RECOVERABLE_FROM_STORED_TRACES",
             accepted=False,pai_job_created=False)
    if a.output.exists():raise FileExistsError(a.output)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps(selection,indent=2,allow_nan=False))
if __name__=="__main__":main()
