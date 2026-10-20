"""Explicit, ACT-private native contact launch. Frozen common source is read-only."""
import argparse
import json
from pathlib import Path
import runpy
import sys

from act16w_runtime import frozen_source, require_gcp2, sha256

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--mode', choices=('teacher', 'record', 'eval-owner', 'dagger-owner'), required=True)
    parser.add_argument('--native-gate', type=Path)
    parser.add_argument('runner', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('explicit native profile opt-in required')
    require_gcp2(training=True)
    source = frozen_source(ROOT)
    expected = json.loads((ROOT/'experiments/2026-10-16-act16w/resume3/contact-adapter-provenance.json').read_text())
    if sha256(Q/'scripts/warp_act_backend.py') != expected['base_backend_sha256']:
        raise ValueError('private adapter requires the exact frozen common backend')
    runner = args.runner[1:] if args.runner[:1] == ['--'] else args.runner
    if args.mode != 'teacher':
        if not args.native_gate:
            parser.error('completed native teacher gate required before record/student execution')
        gate = json.loads(args.native_gate.read_text())
        if (gate.get('passed') is not True or gate.get('N', 0) < 40 or gate.get('n', 0)/gate['N'] < .95
                or gate.get('contact_profile') != 'warp_native_contact_v1'
                or gate.get('training_rgb') is not False or gate.get('input_audit_violations') != 0):
            raise ValueError('native gate not admitted')
        for receipt in gate['raw_results']:
            if sha256(receipt['path']) != receipt['sha256']:
                raise ValueError('native gate evidence changed')
    sys.path.insert(0, str(Q/'scripts'))
    sys.path.insert(0, str(B/'src/warp1-teacher-snapshot-6f057f7e'))
    import sim
    sim.__path__.append(str(ROOT/'sim'))
    # Default OFF scene-fit test (UGRP_ACT18_SCENE_FIT); no-op when unset.
    from act18_scene_fit import install_if_requested
    install_if_requested()
    from act16w_native_contact import installed
    script = (Q/'scripts/run_warp_act_teacher.py' if args.mode == 'teacher' else ROOT/'scripts'/
              {'record': 'run_warp_act_record.py', 'eval-owner': 'act16w_eval_owner.py',
               'dagger-owner': 'act16w_dagger_owner.py'}[args.mode])
    sys.argv = [str(script), *runner]
    with installed():
        runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    main()
