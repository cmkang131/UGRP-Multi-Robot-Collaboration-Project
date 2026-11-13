"""Run the ORIGINAL worker/main/actor loader in its ORIGINAL interpreter."""
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def install(mode):
    if mode not in ('none', 'arm_c', 'arm_s'):
        raise ValueError('unknown treatment mode')
    reference = json.loads((HERE / 'baseline-reference.json').read_text())
    source = reference['aliases']['S']
    sys.path.insert(0, source)
    # These are the exact methods mirrored by the external subclasses. Do not
    # silently apply a treatment to a changed pinned source.
    labels = {'S/harness/pairact_r1_student.py', 'S/harness/beamact_pair_student.py',
              'S/harness/pairact_r1.py', 'S/scripts/pairact_r1_student_worker.py'}
    for row in reference['files']:
        if row['label'] in labels:
            actual = hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()
            if actual != row['expected_sha256']:
                raise ValueError('baseline source mismatch: ' + row['label'])
    from harness import pairact_r1_student as target
    from controller import ORIGINAL_CONTROLLER, TreatmentController
    if mode == 'none':
        target.PairStudentController = ORIGINAL_CONTROLLER
    else:
        class SelectedController(TreatmentController):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, mode=mode, **kwargs)
        target.PairStudentController = SelectedController
    return target.PairStudentController


def main():
    args = list(sys.argv[1:])
    mode = os.environ.get('UGRP_BASELINE_TREATMENT', 'none')
    if args[:1] == ['--treatment-mode']:
        if len(args) < 2:
            raise ValueError('treatment mode value required')
        mode, args = args[1], args[2:]
    selected = install(mode)
    if args == ['--treatment-inspect']:
        print(json.dumps(dict(mode=mode, python=sys.executable, controller=selected.__name__,
            original=mode == 'none', cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),
            simulator_modules=[m for m in sys.modules if m == 'mujoco' or m == 'warp'])))
        return
    if args[:2] != ['-m', 'scripts.pairact_r1_student_worker']:
        raise ValueError('wrapper accepts only the pinned student worker -m invocation')
    sys.argv = ['scripts.pairact_r1_student_worker', *args[2:]]
    from scripts.pairact_r1_student_worker import main as original_main
    original_main()


if __name__ == '__main__':
    main()
