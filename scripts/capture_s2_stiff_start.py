"""Record the fixed s1052 stationary command prefix with stiff servos; no PF."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

RAW = Path('/Users/changmin/projects/ugrp/outputs/s2-realism-18e5e42e-s1052-P1-2-place')


def prefix():
    rows = json.loads((RAW/'student_record.json').read_text())['commands']
    rows = [r for r in rows if r['t'] < 12.]
    if any(r['kind'] in ('drive','mecanum') and any(r.get(k,0) for k in ('forward','left','turn')) for r in rows):
        raise ValueError('stationary prefix contains base motion')
    return rows


def capture(out, sha, option):
    from sim.s2_eval_camera_trace import backend_class
    from sim import s2_realism
    from sim.s2_servo_stiffness import transform_xml
    from scripts.run_final_environment_checks import write
    bundle = json.loads((RAW/'bundle.json').read_text())
    out.mkdir(parents=True, exist_ok=False)
    write(out/'setup_bundle.json', bundle)
    commands = prefix()
    write(out/'fixed_commands.json', commands)
    original = s2_realism.make_scene
    def scene_factory(*args, **kwargs):
        scene = original(*args, **kwargs); transform = scene.robot_transform
        scene.robot_transform = lambda xml, **kw: transform_xml(transform(xml, **kw), servo_stiffness=option)
        scene.manifest['s2_stiff_start'] = dict(servo_stiffness=option, diagnostic_only=True, source_sha=sha)
        return scene
    backend = None; start = time.monotonic()
    try:
        s2_realism.make_scene = scene_factory
        backend = backend_class()(bundle, out, seed=1052)
    finally:
        s2_realism.make_scene = original
    try:
        backend.reset(5.); backend.set_deadline(12.)
        if backend.now != 1.3: raise ValueError('unexpected standard reset time')
        for index in range(214):
            now = round(1.3 + index*.05, 2)
            backend.advance_to(now); backend.eval_sample(); backend.capture()
            for cmd in commands:
                if cmd['t'] == now and cmd['kind'] != 'initial_servo_command':
                    backend.issue('r3', {k:v for k,v in cmd.items() if k!='t'})
        write(out/'result.json', dict(schema='ugrp.s2.stiff_start.v1', source_sha=sha,
            workflow_id='s2-stiff-start-capture-v1', seed=1052, diagnostic_only=True,
            full_dev=False, frames=214, sim_s=backend.now, wall_s=time.monotonic()-start,
            options={**bundle['options'], 'servo_stiffness':option}, model_calls=0,
            command_source_sha256=hashlib.sha256((RAW/'student_record.json').read_bytes()).hexdigest(),
            command_source=str(RAW), start_dock_prior=False, controller_present=False))
    finally:
        backend.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path);p.add_argument('--servo-stiffness',choices=('off','real_v1'),default='off')
    a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False,sim_cap_s=12,servo_stiffness=a.servo_stiffness)));return
    from scripts.run_final_environment_checks import check_source
    from scripts.agent_lock import status,DEFAULT_ROOT
    check_source(a.expected_source_sha);lock=status(DEFAULT_ROOT)
    if not lock or not lock['pid_alive'] or lock['owner']!='codex' or lock['branch']!='codex/s2-realism':
        raise ValueError('owned diagnostic lock required')
    if a.output is None or not a.output.is_absolute():raise ValueError('absolute new output required')
    capture(a.output,a.expected_source_sha,a.servo_stiffness)


if __name__=='__main__':main()
