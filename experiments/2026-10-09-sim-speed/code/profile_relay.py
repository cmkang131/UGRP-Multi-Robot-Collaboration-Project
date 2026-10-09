"""Replay v7 command-state computation from saved issued motors; physics=0."""
import cProfile
import json
from pathlib import Path
import pstats
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    import numpy as np
    from sim.masterpi_drive_friction_v7 import DriveParameters
    source = Path('/Users/changmin/projects/ugrp/outputs/teach-capture-v1/seed49001/robots/r3/frames.jsonl')
    frames = [json.loads(line) for line in source.read_text().splitlines()][:61]
    p = DriveParameters()
    state = [np.zeros(4, dtype=int) for _ in range(3)]
    commands = [np.zeros(4), np.zeros(4), np.zeros(4)]
    prof = cProfile.Profile()
    with prof:
        for frame in frames[:-1]:
            commands[2] = np.array(frame['actuator_state']['motor_commands'])
            for _ in range(800):
                for i in range(3):
                    effective, state[i] = p.command_step(commands[i], state[i])
    out = Path('/Users/changmin/projects/ugrp/outputs/simspeed-20261009/relay-profile')
    out.mkdir(parents=True, exist_ok=False)
    prof.dump_stats(out/'cpu.prof')
    stats = pstats.Stats(prof)
    top = sorted(stats.stats.items(), key=lambda item: item[1][2], reverse=True)[:10]
    result = dict(scope='command relay replay only; physics=0; concurrent diagnostic, not wall/SIM measurement',
        calls=144000, top10=[dict(function=f'{key[0]}:{key[1]}:{key[2]}', calls=v[1], self_s=v[2],
            cumulative_s=v[3], percent=100*v[2]/stats.total_tt) for key,v in top])
    (out/'profile.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
