#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
robotwin_root=${ROBOTWIN_ROOT:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/RoboTwin}
venv_root=${ROBOTWIN_VENV:-/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv}
config=${R22P19_STAGE2C_CONFIG:-$repo_root/stage2_robotwin/stage2c/configs/stage2c.yaml}

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-3}
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"
export __EGL_VENDOR_LIBRARY_FILENAMES="$venv_root/lib/python3.10/site-packages/sapien/vulkan_library/10_nvidia.json"
export PYTHONDONTWRITEBYTECODE=1

"$repo_root/stage2_robotwin/scripts/apply_runtime_patches.sh" "$robotwin_root" "$venv_root"

command=${1:-}
shift || true
case "$command" in
  capture-tapes)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.capture_expert_tapes \
      --robotwin-root "$robotwin_root" --config "$config" "$@"
    ;;
  replay-cell)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.replay.fresh_prefix_runner \
      --robotwin-root "$robotwin_root" --config "$config" "$@"
    ;;
  replay-noise)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.run_replay_noise_audit \
      --robotwin-root "$robotwin_root" --config "$config" "$@"
    ;;
  natural)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.run_natural_responsibility "$@"
    ;;
  soft-audit)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.audit_soft_authority "$@"
    ;;
  local-gate)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.run_local_operator_gate "$@"
    ;;
  stress-calibration)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.calibrate_stress "$@"
    ;;
  closed-loop)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.run_closed_loop_matrix "$@"
    ;;
  analyze)
    exec "$venv_root/bin/python" -m stage2_robotwin.stage2c.scripts.analyze_stage2c "$@"
    ;;
  *)
    echo "usage: $0 {capture-tapes|replay-cell|replay-noise|natural|soft-audit|local-gate|stress-calibration|closed-loop|analyze} [args...]" >&2
    exit 2
    ;;
esac
