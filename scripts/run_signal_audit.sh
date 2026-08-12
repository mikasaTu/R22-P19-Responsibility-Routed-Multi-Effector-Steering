#!/usr/bin/env bash
set -euo pipefail

CODE_DIR="${R22P19_CODE_DIR:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/code/r22p19-libero-phase1-20260813}"
SIM_PYTHON="${R22P19_SIM_PYTHON:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/envs/libero-original/bin/python}"
RUN_ID="${R22P19_RUN_ID:-signal-$(date -u +%Y%m%dT%H%M%SZ)}"
OUTPUT_DIR="${R22P19_OUTPUT_DIR:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/r22p19_libero_phase1/${RUN_ID}}"
export MUJOCO_GL="${MUJOCO_GL:-glx}"

cd "${CODE_DIR}/experiments/r22p19_libero_phase1"
exec "${SIM_PYTHON}" -m r22p19_libero.audit \
  --mode signal \
  --config configs/signal_pilot.yaml \
  --output "${OUTPUT_DIR}"
