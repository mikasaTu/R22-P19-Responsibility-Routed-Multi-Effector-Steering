#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
robotwin_root=${ROBOTWIN_ROOT:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/RoboTwin}
venv_root=${ROBOTWIN_VENV:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv}
run_id=${R22P19_SIGNAL_RUN_ID:-pilot-$(date -u +%Y%m%dT%H%M%SZ)}
output=${R22P19_SIGNAL_OUTPUT:-$repo_root/stage2_robotwin/results/oracle_signal/$run_id}
episodes=${R22P19_SIGNAL_EPISODES:-1}
seed_start=${R22P19_SEED_START:-0}
seed_stop=${R22P19_SEED_STOP:-1}
base_stride=${R22P19_BRANCH_BASE_STRIDE:-50}
swap_stride=${R22P19_BRANCH_SWAP_STRIDE:-250}
profile_mode=${R22P19_BRANCH_PROFILE_MODE:-all}
planner=${ROBOTWIN_PLANNER:-mplib_screw}
read -r -a horizons <<< "${R22P19_BRANCH_HORIZONS:-5 10}"

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-3}
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"
export __EGL_VENDOR_LIBRARY_FILENAMES="$venv_root/lib/python3.10/site-packages/sapien/vulkan_library/10_nvidia.json"

mkdir -p "$output"
"$repo_root/stage2_robotwin/scripts/apply_runtime_patches.sh" \
  "$robotwin_root" "$venv_root"

"$venv_root/bin/python" -m stage2_robotwin.scripts.run_smoke \
  --robotwin-root "$robotwin_root" \
  --output "$output" \
  --episodes "$episodes" \
  --seed-start "$seed_start" \
  --seed-stop "$seed_stop" \
  --planner "$planner" \
  --oracle-branches \
  --branch-base-stride "$base_stride" \
  --branch-swap-stride "$swap_stride" \
  --branch-profile-mode "$profile_mode" \
  --branch-horizons "${horizons[@]}" \
  2>&1 | tee "$output/runtime.log"

branch_files=("$output"/branches/*.jsonl)
if [[ ! -e "${branch_files[0]}" ]]; then
  echo "no branch records were produced" >&2
  exit 3
fi

successful=$(
  "$venv_root/bin/python" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["successful_valid_event_episodes"])' \
    "$output/smoke_summary.json"
)
"$venv_root/bin/python" -m stage2_robotwin.scripts.analyze_signal_audit \
  "${branch_files[@]}" \
  --output "$output/signal_metrics.json" \
  --plot "$output/responsibility_curve.png" \
  --successful-episodes "$successful"
