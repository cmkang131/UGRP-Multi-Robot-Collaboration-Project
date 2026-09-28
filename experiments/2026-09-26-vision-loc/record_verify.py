"""Verify recorded VIS4/VIS5 source digests against the Git blobs of the commit that holds those bytes.

On 2026-09-28 the VIS4/VIS5 changes to ``vision_pf.py`` and ``vision_loc_cli.py`` moved to versioned files
(``vision_pf_v4.py``, ``vision_loc_cli_v4.py``, and later ``*_v5.py``) so that the VIS3 student files pinned by
main (``prereg_v3.json``, ``harness/vision_loc_protocol.py::check_frozen``) stay byte-identical. The historical
``source_freeze.json`` records name the old paths with the old bytes, so their *source* digests are checked
against the recording commit (``git show <commit>:<path>``), never against the working tree. Data inputs under
``outputs/`` are not in Git and are still checked against the files on disk by the callers.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO_TOP_DIRS = ('experiments', 'harness', 'sim', 'scripts', 'tests', 'maps', 'configs')

# Commit whose blobs equal every source digest in outputs/vision-loc-v4/sigma/source_freeze.json (VIS4 sigma run).
VIS4_SIGMA_RECORD_COMMIT = '3e9bdf7a17893079cc1ebecc0e2af00d6317052b'
# Commit whose blobs equal every source digest in outputs/vision-loc-v5/final/source_freeze.json (VIS5 dev run).
VIS5_FINAL_RECORD_COMMIT = '5cc83adbcbaab80191a84f592a88139d89ebe7a9'


def repo_relative(path: str) -> str:
    """Repository-relative POSIX path of a recorded (absolute, possibly other-worktree) source path."""
    parts = Path(os.path.normpath(path)).parts
    for i, part in enumerate(parts):
        if part in REPO_TOP_DIRS:
            return '/'.join(parts[i:])
    raise ValueError(f'not a repository source path: {path}')


def git_blob(commit: str, rel: str) -> bytes:
    return subprocess.run(['git', 'show', f'{commit}:{rel}'], cwd=ROOT, capture_output=True, check=True).stdout


def blob_mismatches(hashes: dict, commit: str) -> list:
    """Recorded paths whose digest differs from (or is missing in) ``commit``'s blob."""
    bad = []
    for path, want in hashes.items():
        try:
            data = git_blob(commit, repo_relative(path))
        except (ValueError, subprocess.CalledProcessError):
            bad.append(path)
            continue
        if hashlib.sha256(data).hexdigest() != want:
            bad.append(path)
    return bad
