"""pairact-r1 two-stage freeze of COLLECT_PREREG_DRAFT.json + RUN_MANIFEST.json (v3, Codex v2 B1/B2).

    # commit Y: every VM-fill field except the three recording_check hashes is already filled
    python scripts/pairact_r1_freeze.py core --collector-sha X [--verify-assets]
    git commit -m 'pairact-r1 FROZEN_CORE'          # prints core_sha256; record it in the commit message
    # probe source run, probe-cases, recording probe, check-rows, recording-check (RUNBOOK 1-2b)
    python scripts/pairact_r1_freeze.py final --recording-dir RUNC [--verify-assets]
    git commit -m 'pairact-r1 FROZEN'                # core_sha256 must be the one printed at FROZEN_CORE

``core`` writes collector.source_sha = X, prereg.core_sha256 and status FROZEN_CORE in both files,
then runs the stage 'core' gate with the collector provenance check (X ancestor of HEAD, fixed
collector files unchanged X..HEAD).  ``final`` fills the three recording_check sha256 from
RUNC/{probe-cases,check-rows,recording-check}.json, sets FROZEN and runs the stage 'final' gate;
it refuses when core_sha256 moved.  Only the status line of the prereg is rewritten (other bytes kept).
Nothing is written when the gate fails.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import pairact_collect as pc  # noqa: E402

EXP = ROOT / 'experiments/2026-10-21-pairact-r1'
STATUS_LINE = re.compile(r'^(  "status": )"[A-Z_]+"(,)$', re.M)


def set_prereg_status(text, status):
    out, n = STATUS_LINE.subn(lambda m: f'{m.group(1)}"{status}"{m.group(2)}', text, count=1)
    if n != 1:
        raise ValueError('prereg top-level status line not found')
    return out


def freeze(stage, *, prereg_path, manifest_path, repo=ROOT, collector_sha=None, recording_dir=None,
           verify_assets=False, expect_core=None):
    prereg_text = Path(prereg_path).read_text()
    manifest = json.loads(Path(manifest_path).read_text())
    status = 'FROZEN_CORE' if stage == 'core' else 'FROZEN'
    if stage == 'core':
        if not collector_sha:
            raise ValueError('--collector-sha (commit X) required')
        manifest['collector']['source_sha'] = collector_sha
    else:
        before = json.loads(prereg_text)
        if before.get('status') != 'FROZEN_CORE' or manifest.get('status') != 'FROZEN_CORE':
            raise ValueError('final needs FROZEN_CORE prereg and manifest')
        core_before = pc.core_sha256(before, manifest)
        if expect_core is not None and core_before != expect_core:
            raise ValueError(f'core_sha256 {core_before} != expected {expect_core}')
        for key, name in pc.RECORDING_FILES.items():
            manifest['recording_check'][key] = pc.file_sha256(Path(recording_dir) / name)
    new_prereg_text = set_prereg_status(prereg_text, status)
    prereg = json.loads(new_prereg_text)
    manifest['prereg']['core_sha256'] = pc.prereg_core_sha256(prereg)
    manifest['status'] = status
    core = pc.check_run_manifest(manifest, stage=stage, prereg=prereg, repo=repo, recording_dir=recording_dir,
                                 verify_assets=verify_assets)
    if stage == 'final' and core != core_before:
        raise ValueError(f'core_sha256 moved at FROZEN: {core_before} -> {core}')
    Path(prereg_path).write_text(new_prereg_text)
    Path(manifest_path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return dict(stage=status, core_sha256=core, prereg_sha256=pc.file_sha256(prereg_path),
                manifest_sha256=pc.file_sha256(manifest_path), prereg_core_sha256=manifest['prereg']['core_sha256'])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('stage', choices=('core', 'final'))
    p.add_argument('--prereg', type=Path, default=EXP / 'COLLECT_PREREG_DRAFT.json')
    p.add_argument('--manifest', type=Path, default=EXP / 'RUN_MANIFEST.json')
    p.add_argument('--collector-sha', help='core: commit X (collector code)')
    p.add_argument('--recording-dir', type=Path, help='final: probe source run root with the three recording files')
    p.add_argument('--expect-core', help='final: core_sha256 printed at FROZEN_CORE')
    p.add_argument('--verify-assets', action='store_true', help='re-hash the episode assets (on the collection VM)')
    a = p.parse_args()
    if a.stage == 'final' and a.recording_dir is None:
        p.error('final needs --recording-dir')
    print(json.dumps(freeze(a.stage, prereg_path=a.prereg, manifest_path=a.manifest, collector_sha=a.collector_sha,
                            recording_dir=a.recording_dir, verify_assets=a.verify_assets, expect_core=a.expect_core)))


if __name__ == '__main__':
    main()
