#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
robotwin_root=${ROBOTWIN_ROOT:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/RoboTwin}
venv_root=${ROBOTWIN_VENV:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv}
run_id=${R22P19_STAGE2_RUN_ID:-smoke-$(date -u +%Y%m%dT%H%M%SZ)}
output=${R22P19_STAGE2_OUTPUT:-$repo_root/stage2_robotwin/results/smoke/$run_id}
planner=${ROBOTWIN_PLANNER:-mplib_screw}
episode_offset=${R22P19_EPISODE_OFFSET:-0}

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"
export __EGL_VENDOR_LIBRARY_FILENAMES="$venv_root/lib/python3.10/site-packages/sapien/vulkan_library/10_nvidia.json"

"$repo_root/stage2_robotwin/scripts/apply_runtime_patches.sh" \
  "$robotwin_root" "$venv_root"

"$venv_root/bin/python" -m stage2_robotwin.scripts.run_smoke \
  --robotwin-root "$robotwin_root" \
  --output "$output" \
  --episodes 10 \
  --seed-start 0 \
  --seed-stop 100 \
  --episode-offset "$episode_offset" \
  --planner "$planner"
