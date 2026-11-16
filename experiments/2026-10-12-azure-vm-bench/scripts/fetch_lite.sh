#!/bin/bash
set -euo pipefail
v=$1; O=/Users/changmin/projects/ugrp/outputs/azure-vm-bench-20261012/runs-${v}; mkdir -p "$O"
F=(--exclude='*.jpg' --exclude='*.jpeg' --exclude='*.png' --exclude='*.npz' --exclude='*.npy' --exclude='*.mp4' --exclude='*-request.json' --exclude='rgb/' --exclude='request_images/')
RSH="ssh -F $PWD/ssh_config"
rsync -a -e "$RSH" "${F[@]}" --include="vmb-${v}-*/***" --include="vmb-attempt1-relay400/***" --exclude='*' "vmb-${v}:ugrp-sim/runs/" "$O/"
d=$(rsync -anc -e "$RSH" "${F[@]}" --include="vmb-${v}-*/***" --include="vmb-attempt1-relay400/***" --exclude='*' --out-format='%n' "vmb-${v}:ugrp-sim/runs/" "$O/" | grep -v '/$' || true)
[ -z "$d" ] && echo "checksum-verified $v $(find $O -type f | wc -l) files $(du -sk $O | cut -f1) KiB" || { echo "MISMATCH $d"; exit 1; }
grep -rl -E 'data:image|jpeg_base64' "$O" && echo IMAGE_FOUND || echo no-embedded-images
