#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 ROBOTWIN_ROOT VENV_ROOT" >&2
  exit 2
fi

robotwin_root=$(cd "$1" && pwd)
venv_root=$(cd "$2" && pwd)
stage2_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if git -C "$robotwin_root" apply --unidiff-zero --reverse --check \
  "$stage2_root/patches/robotwin_optional_curobo.patch" >/dev/null 2>&1; then
  echo "robotwin optional-CuRobo patch already applied"
else
  git -C "$robotwin_root" apply --unidiff-zero --check \
    "$stage2_root/patches/robotwin_optional_curobo.patch"
  git -C "$robotwin_root" apply --unidiff-zero \
    "$stage2_root/patches/robotwin_optional_curobo.patch"
  echo "applied robotwin optional-CuRobo patch"
fi

mplib_dir="$venv_root/lib/python3.10/site-packages"
if patch -d "$mplib_dir" -p1 --dry-run --reverse \
  < "$stage2_root/patches/mplib_official_install.patch" >/dev/null 2>&1; then
  echo "official MPLib compatibility patch already applied"
else
  patch -d "$mplib_dir" -p1 --dry-run \
    < "$stage2_root/patches/mplib_official_install.patch" >/dev/null
  patch -d "$mplib_dir" -p1 \
    < "$stage2_root/patches/mplib_official_install.patch"
  echo "applied official MPLib compatibility patch"
fi
