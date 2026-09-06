"""Frozen preflight selection. Scientific P1/P2 are not adjudicated here."""
import math

def amplitude_selection(rows, *, repeat_bitwise_passed):
    if repeat_bitwise_passed is not True:
        return {"status":"REPEATABILITY_BLOCKED","recommended_amplitude_m":None,"eligible_amplitudes_m":[],"accepted":False,"pai_job_created":False}
    if len(rows)!=3 or {row["amplitude_m"] for row in rows}!={.003,.005,.008}:
        raise ValueError("require exactly one smoke per preregistered amplitude")
    assessed=[]
    for row in rows:
        finite=lambda value: isinstance(value,(int,float)) and math.isfinite(value)
        snr=row.get("spectral_snr")
        snr_pass=isinstance(snr,list) and len(snr)==2 and all(finite(v) and v>=10 for v in snr)
        contact=row.get("dual_contact_fraction")
        i5=finite(contact) and contact>=.95 and row.get("task_success") is True
        assessed.append(dict(row,I5_smoke_proxy_pass=i5,both_spectral_snr_pass=snr_pass,eligible=bool(i5 and snr_pass)))
    eligible=sorted(row["amplitude_m"] for row in assessed if row["eligible"])
    return {"status":"AMPLITUDE_RECOMMENDED_AWAITING_CHECKPOINT" if eligible else "NO_ELIGIBLE_AMPLITUDE_DO_NOT_FREEZE","recommended_amplitude_m":eligible[0] if eligible else None,"eligible_amplitudes_m":eligible,"rows":assessed,"full_instrument_gate_evaluation":False,"accepted":False,"pai_job_created":False}
