"""Exact enumerated Step9 matrices; planning never launches a cell."""
from itertools import product
import random

def stage_i(seed=22019):
    rows=[]
    for calibration, pair, repeat in product((0,1),((1.0,2.5),(2.5,1.0)),(0,1)):
        rows.append(dict(group="I-A",seed=calibration,frequencies=list(pair),repeat=repeat,mode="dual"))
    for calibration, side in product((0,1),("left","right")):
        rows.append(dict(group="I-B",seed=calibration,frequencies=[1.0,2.5],repeat=0,mode="single-"+side))
        rows.append(dict(group="I-C",seed=calibration,frequencies=[1.0,2.5],repeat=0,mode="locked-"+side))
    for calibration, repeat in product((0,1),(0,1,2)):
        rows.append(dict(group="I-D",seed=calibration,frequencies=[1.0,2.5],repeat=repeat,mode="none"))
    for calibration in (0,1):
        rows.append(dict(group="I-E",seed=calibration,frequencies=[1.0,1.0],repeat=0,mode="same-frequency"))
    random.Random(seed).shuffle(rows)
    return [dict(row,launch_index=i,accepted=False,pai_job_created=False) for i,row in enumerate(rows)]

def stage_ii(*,instrument_passed,amplitude_m,seed=22019):
    if instrument_passed is not True:
        raise ValueError("P2 cannot run without all P1 gates passing")
    if amplitude_m not in (.003,.005,.008):
        raise ValueError("a smoke-eligible preregistered amplitude must be frozen")
    rows=[dict(group="II",seed=c,soft_arm=side,gamma=g,repeat=r,frequencies=[1.0,2.5],mode="dual",amplitude_m=amplitude_m)
          for c,side,g,r in product((0,1),("left","right"),(1.0,.8,.6,.4,.25,.15),(0,1))]
    random.Random(seed).shuffle(rows)
    return [dict(row,launch_index=i,accepted=False,pai_job_created=False) for i,row in enumerate(rows)]
