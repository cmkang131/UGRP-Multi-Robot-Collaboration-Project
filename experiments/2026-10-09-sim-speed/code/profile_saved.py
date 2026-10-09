"""cProfile of saved own inputs; no physics step, render, or timing claim."""
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
RAW = Path('/Users/changmin/projects/ugrp/outputs/simspeed-20261009')
SOURCE = Path('/Users/changmin/projects/ugrp/outputs/teach-capture-v1/seed49001')


def main():
    import numpy as np
    from PIL import Image
    from scripts.run_teach_capture import old, make_controller
    from harness.active_camera import SEARCH
    from harness.active_wall_vision import observe
    frames = [json.loads(line) for line in (SOURCE/'robots/r3/frames.jsonl').read_text().splitlines()][:61]
    expected = {r['frame_id']: r for r in map(json.loads, (SOURCE/'own-controller.jsonl').read_text().splitlines())}
    explorer = old.actor('r3', frames[0]['sim_time'], SEARCH, active_mapping='frontier_rbpf_v1',
        active_loop='information_gain_v1', seed=49001, active_recovery='nav2_frontier_v1',
        navigation_map='public_ros_v8', motion_model='s2_pulse_v122_rotL_v1')
    old.base.install_profile(explorer.memory.self_map, profile='egomap27_wide')
    controller = make_controller(explorer, seed=49001)
    out = RAW/'saved-profile'
    out.mkdir(parents=True, exist_ok=False)
    prof = cProfile.Profile()
    matches = []
    with (out/'controller.jsonl').open('w') as stream:
        for i, frame in enumerate(frames):
            if i < 10:
                continue
            image = SOURCE/frame['path']
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            assert digest == frame['sha256']
            with prof:
                rgb = np.asarray(Image.open(image).convert('RGB'))
                detection = observe(rgb, SEARCH, body_settling=.7)
                command, trace = controller.receive(robot_id='r3', t=frame['sim_time'], frame_id=frame['frame_id'],
                    rgb=rgb, servo=SEARCH, observation=detection, frame_sha256=digest)
                controller.command(expected[frame['frame_id']]['command'])
                line = json.dumps(trace, ensure_ascii=False, allow_nan=False)+'\n'
                stream.write(line)
            matches.append(trace == expected[frame['frame_id']])
    prof.dump_stats(out/'cpu.prof')
    stats = pstats.Stats(prof)
    top = sorted(stats.stats.items(), key=lambda item: item[1][2], reverse=True)[:10]
    table = [dict(function=f'{key[0]}:{key[1]}:{key[2]}', calls=v[1], self_s=v[2],
                  cumulative_s=v[3], percent=100*v[2]/stats.total_tt) for key,v in top]
    (out/'profile.json').write_text(json.dumps(dict(scope='saved RGB/controller only; no physics/render; concurrent diagnostic, not timing',
        frames=len(matches), identical_traces=sum(matches), profile_total_s=stats.total_tt, top10=table),indent=2)+'\n')
    print((out/'profile.json').read_text())


if __name__ == '__main__':
    main()
