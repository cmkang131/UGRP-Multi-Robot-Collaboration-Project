"""Rebuild missing prefix JPEGs only if every original frame digest matches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if os.environ.get('MUJOCO_GL') != 'osmesa' or os.sched_getaffinity(0) != {0} or os.getloadavg()[0] >= 12.8:
        raise ValueError('Azure single-core admission required')
    sys.path.insert(0, str(a.source))
    from sim.goal_route_assets import PhysicsBackend
    frames = [json.loads(x) for x in (a.prefix / 'robots/r3/frames.jsonl').read_text().splitlines()]
    commands = [json.loads(x) for x in (a.prefix / 'robots/r3/commands.jsonl').read_text().splitlines()]
    bundle = json.loads((a.prefix / 'bundle.json').read_text())
    groups = {}
    start = frames[0]['sim_time']
    for row in commands:
        if row['kind'] != 'initial_servo_command':
            tick = round((row['t'] - start) / .2)
            groups.setdefault(tick, []).append({k: v for k, v in row.items() if k != 't'})
    a.output.mkdir(exist_ok=False)
    backend = PhysicsBackend(bundle, a.output, seed=63003)
    began = time.monotonic()
    results = []
    try:
        backend.reset(5.)
        assert abs(backend.now - start) < 1e-8
        backend.set_deadline(frames[-1]['sim_time'] + .2)
        for command in groups.get(0, []):
            backend.issue('r3', command)
        for tick, frame in enumerate(frames):
            backend.capture()
            if tick >= 10:
                backend.own_range()
            if tick:
                for command in groups.get(tick, []):
                    backend.issue('r3', command)
            backend.eval_sample()
            image = a.output / frame['path']
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            results.append(dict(path=frame['path'], original=frame['sha256'], reconstructed=digest,
                match=digest == frame['sha256']))
            if tick % 10 == 0:
                print(json.dumps(dict(tick=tick, sim_s=backend.now, matches=sum(r['match'] for r in results),
                    frames=len(results), wall_s=time.monotonic()-began)), flush=True)
            if tick < len(frames)-1:
                backend.advance_to(round(start + (tick+1)*.2, 9))
    finally:
        backend.close()
    report = dict(status='VERIFIED' if all(r['match'] for r in results) else 'MISMATCH',
        seed=63003, source_sha=a.source.name, commands_source=str(a.prefix), frames=results,
        matches=sum(r['match'] for r in results), count=len(frames), controller_run=False,
        checkpoint_state_replacement=False, use='missing prefix RGB only after exact original SHA-256 match')
    (a.output / 'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    (a.output / 'EXIT').write_text('0\n' if report['status'] == 'VERIFIED' else '1\n')
    return int(report['status'] != 'VERIFIED')


if __name__ == '__main__':
    raise SystemExit(main())
