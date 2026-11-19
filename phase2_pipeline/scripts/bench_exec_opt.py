"""Run one measured, offline fixed-plan team or staged ACT case on the work VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def revision(path):
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('team', 'grasp'))
    p.add_argument('case', type=Path, help='new directory for this invocation')
    p.add_argument('input', help='N03 / N09 (P2 S01), or the staged plan.json path')
    p.add_argument('cap', type=float, help='simulated seconds')
    args, switches = p.parse_known_args()
    if any(s.split('=')[0] in ('--brain-url', '--actor-server-url', '--fixed', '--scene-id', '--plan',
                                 '--model', '--scenes', '--output', '--actor-python') for s in switches):
        p.error('the paired benchmark owns the inputs, fixed plan, local ACT worker and output')
    hybrid = Path(os.environ.get('EXEC_OPT_HYBRID', Path.home() / 'hybrid')).resolve()
    py = os.environ.get('EXEC_OPT_PYTHON', str(Path.home() / 'ugrp-cpu/bin/python'))
    tree = Path(os.environ.get('EXEC_OPT_TREE', ROOT)).resolve()
    wrapper = Path(os.environ.get('EXEC_OPT_WRAPPER', hybrid / 'speed/dev_run13_speed.py')).resolve()
    episode = hybrid / 'cover-dev20/episode/seed90721'
    if not episode.is_dir():
        episode = hybrid / 'cover-new12/episode/seed90721'
    protocol = episode / 'protocol.json'
    model = hybrid / 'gseg-actor'
    frozen = hybrid / 'graw/scene/frozen_slim'
    case = args.case.resolve()
    plan = episode / 'plan.json' if args.mode == 'team' else Path(args.input).resolve()
    inputs = {'plan': plan, 'protocol': protocol, 'weights': model / 'model.safetensors',
              'actor_config': model / 'config.json', 'adapter': model / 'adapter.json', 'wrapper': wrapper}
    if args.mode == 'team':
        if args.input not in ('N03', 'N09'):
            p.error('team size must be N03 or N09')
        scene_id = f'P2_{args.input}_S01'
        inputs['scene'] = hybrid / 'scenes-p2gate' / (scene_id + '.json')
        task = ['--robot-tags', '--overhead', '--regrasp-max', '1', '--fixed', 'oracle',
                '--scenes', str(inputs['scene']), '--scene-id', scene_id]
        entry = [str(wrapper)]
    else:
        # The supplied work-VM dev wrapper provides the same host receipt and
        # source pin for both entry points. Its final call is team.main().
        entry = ['-c', 'import runpy,sys; from scripts import run_team_carry as t, run_grasp_act_student as s; '
                 't.main=s.main; sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")', str(wrapper)]
        task = ['--teacher-start-v1', '--audit-grasp-start', '--robot-tags', '--overhead',
                '--grasp-transition-rule', '--release-code-v1', '--carry-v1', 'back:20p,left:30p,fwd:40p',
                '--scene-without', 'beam,can,tile,frame,crate,robots', '--n-action-steps', '8']
    env = os.environ.copy()
    for flag in ('SPEED_CULL_RENDER', 'SPEED_CULL_VERIFY', 'SPEED_SKIP_RGB_WRITES', 'SPEED_SAMPLE_RENDERS'):
        env.pop(flag, None)
    env.update(PYTHONPATH=os.pathsep.join((str(tree), str(hybrid / 'graw/pyvendor'))),
               MUJOCO_GL=env.get('MUJOCO_GL', 'osmesa'), HF_HUB_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               SPEED_OUT=str(case / 'speed'), SPEED_DUMP_SIM_S='1')
    env['PYOPENGL_PLATFORM'] = env['MUJOCO_GL']
    source = revision(tree)
    argv = [py, '-B', *entry, source, '--plan', str(plan), '--protocol', str(protocol), '--model', str(model),
            '--output', str(case / 'run'), '--actor-python', py, '--scene-source', str(frozen),
            '--cap-s', str(args.cap), *task, *switches]
    receipt = {'source': source, 'frozen_source': revision(frozen), 'mode': args.mode, 'cap_s': args.cap, 'switches': switches,
               'inputs': {k: sha(v) for k, v in inputs.items()}, 'argv': argv,
               'env': {k: env.get(k) for k in ('MUJOCO_GL', 'PYOPENGL_PLATFORM', 'LP_NUM_THREADS', 'GALLIUM_DRIVER',
                                                'EGL_PLATFORM', 'LIBGL_ALWAYS_SOFTWARE',
                                                'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')}}
    case.mkdir(parents=True, exist_ok=False)
    output = case / 'receipt.json'
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    with (case / 'process.log').open('x') as log:
        start = time.monotonic()
        try:
            status = subprocess.run(argv, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        except OSError as exc:
            print(exc, file=log)
            status = 127
        receipt.update(wall_s=time.monotonic() - start, exit_code=status)
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'{case}: exit={status}, wall_s={receipt["wall_s"]:.3f}', flush=True)
    return status


if __name__ == '__main__':
    sys.exit(main())
