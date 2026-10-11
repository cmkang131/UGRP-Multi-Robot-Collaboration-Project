#!/bin/bash
# Installed as /usr/local/bin/ugrp-auto-archive on oracle-x86.
# Finished, idle runs only. Archive migration is not dev evidence pruning.
set -euo pipefail
R=${UGRP_RUNS:-/home/ubuntu/ugrp-sim/runs}
A=${UGRP_ARCHIVE:-/home/ubuntu/ugrp-sim/arm}
TOOLS=${UGRP_STORAGE_TOOLS:-/usr/local/lib/ugrp-storage}
L=$R/SUPERVISOR-NOTES.txt
dry=false
if [[ ${1:-} == --dry-run ]]; then dry=true; elif [[ $# != 0 ]]; then exit 2; fi
mountpoint -q "$A" || ls "$A" >/dev/null 2>&1
mountpoint -q "$A" || exit 1
exec 9>/tmp/ugrp-auto-archive.lock
flock -n 9 || exit 0
for d in "$R"/*/; do
  d=${d%/}; n=$(basename "$d")
  [[ -L "$d" ]] && continue
  [[ -f "$d/EXIT" ]] || continue
  [[ -n $(find "$d" -newermt '-20 min' -print -quit) ]] && continue
  if $dry; then
    python3 "$TOOLS/scripts/compress_json_traces.py" "$d" || continue
    continue
  fi
  # Compression includes decompressed SHA-256 verification + durable inventories.
  python3 "$TOOLS/scripts/compress_json_traces.py" "$d" --execute || continue
  bytes=$(du -sb "$d" | cut -f1)
  # Recheck for EACH run, including the next copy; never consume ARM's 25 GiB reserve.
  python3 "$TOOLS/scripts/storage_budget.py" --host arm --path "$A" \
    --runs 1 --per-run-mb "$(python3 -c 'import sys; print(int(sys.argv[1])/2**20)' "$bytes")" || {
      echo "$(date -u +%FT%TZ) auto-archive refused: ARM projected free below 25 GiB" >> "$L"
      continue
    }
  if [[ -e "$A/$n" ]]; then
    echo "$(date -u +%FT%TZ) auto-archive skipped existing destination: $n (no overwrite)" >> "$L"
    continue
  fi
  # A temporary directory prevents readers from observing an incomplete archive.
  target="$A/.incoming-$n"
  [[ ! -e "$target" ]] || continue
  mkdir "$target"
  rsync -a -- "$d/" "$target/" || continue
  differences=$(rsync -anc --out-format=%n -- "$d/" "$target/") || continue
  [[ -z "$differences" ]] || continue
  # Verify the entire archive against source SHA-256, beyond rsync's checksum.
  python3 - "$d" "$target" "$TOOLS" "$A/$n" <<'PY' || continue
import os, pathlib, shutil, sys
sys.path.insert(0, sys.argv[3])
from scripts.storage_common import files, sha256, lock_run, idle_reason
from scripts.worktree_guard import refuse_if_in_use
root = pathlib.Path(sys.argv[1])
target, published = pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[4])
with lock_run(root):
    if idle_reason(root):
        raise SystemExit('run became active')
    refuse_if_in_use(root, 0, None)
    def key(folder):
        return {(p.relative_to(folder).as_posix(), p.stat().st_size, sha256(p)) for p in files(folder)}
    # Include the hash inventories themselves in this archive comparison.
    if key(root) != key(target):
        raise SystemExit('archive SHA-256 mismatch')
    if published.exists() or published.is_symlink() or idle_reason(root):
        raise SystemExit('destination exists or run became active')
    target.rename(published)
    shutil.rmtree(root)
    os.symlink(published, root)
PY
  # Existing migration behavior: remove verified local copy, leave archive symlink.
  echo "$(date -u +%FT%TZ) auto-archived $n (zstd + SHA-256 + rsync -c verified)" >> "$L"
done
