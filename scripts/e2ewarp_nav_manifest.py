#!/usr/bin/env python3
"""Write the hash-bound navigation component manifest for ``--mode nav``.

The manifest references ``harness/e2ewarp_nav_gate.py:navigation_factory`` and
its current file SHA-256, plus the measured calibration artifact admitted by the
queue. Written from the frozen source tree on the VM, so the hash can never go
stale against the code that will run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTORY = 'harness.e2ewarp_nav_gate:navigation_factory'
FACTORY_FILE = ROOT / 'harness/e2ewarp_nav_gate.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--calibration', type=Path, required=True)
    p.add_argument('--source-sha', required=True)
    a = p.parse_args(argv)
    calibration = json.loads(a.calibration.read_text())
    if calibration.get('schema') != 'ugrp.e2ewarp.nav_calibration.v1' or calibration.get('measured') is not True:
        raise SystemExit('measured calibration artifact required')
    manifest = dict(
        schema='ugrp.e2ewarp.nav_components.v1',
        navigation=dict(ready=True, owner='dsh-e2ewarp-nav-gate',
                        evidence=dict(calibration_sha256=sha(a.calibration),
                                      calibration_path=str(a.calibration.resolve()),
                                      calibration_source_sha=calibration.get('source_sha'),
                                      scene='s7_pair_with_solo_v7',
                                      visibility_check='outputs/e2e18-admin/nav-gate/visibility-check.json',
                                      source_sha=a.source_sha)),
        navigation_factory=dict(entry=FACTORY, sha256=sha(FACTORY_FILE)),
        static_map_input=False,
        note='nav-only gate: ACT / loaded FK / static-map registration / '
             'own-static correction / release are not required and not loaded')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(dict(out=str(a.out), factory_sha256=manifest['navigation_factory']['sha256'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
