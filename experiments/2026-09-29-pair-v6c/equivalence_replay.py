"""Decision equivalence of the pre-close cross-section rule across two source commits (no physics).

The grasp_lift probes ran on one commit; the contiguity rule was then made
robust to detached noise tails (third review). This replays every recorded
grasp-pose own frame of the b-v6c cases through ``cross_section`` of both
commits, with the same anchored beam (re-fitted offline from the recorded
standoff frames, as in replay_boundary_entry.py), and counts accept/reject
decisions that differ. Zero differences means the physics outcomes carry over.

usage: python equivalence_replay.py <old commit> <raw dir> [<raw dir> ...]
"""
from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import replay_boundary_entry as R  # noqa: E402
from harness import zone_pair_grasp_entry_v6c as new  # noqa: E402

MIN_WIDTH = new.MIN_WIDTH_FRACTION * new.BEAM_WIDTH_M


def old_module(commit):
    source = subprocess.check_output(['git', 'show', f'{commit}:harness/zone_pair_grasp_entry_v6c.py'], cwd=ROOT,
                                     text=True)
    module = types.ModuleType('entry_old')
    exec(compile(source, f'{commit}:zone_pair_grasp_entry_v6c.py', 'exec'), module.__dict__)
    return module


def decide(module, pts, beam):
    span = module.cross_section(pts, beam)
    return span is not None and span >= module.MIN_WIDTH_FRACTION * module.BEAM_WIDTH_M


def main(commit, raws):
    old = old_module(commit)
    total = differ = unanchored = 0
    rows = []
    for raw in map(Path, raws):
        for case in sorted(p for p in (raw/'cases').iterdir() if p.is_dir() and 'b-v6c' in p.name):
            if not (case/'robots.json').exists():
                continue
            robots = json.loads((case/'robots.json').read_text())
            for rid in ('r1', 'r2'):
                frames = robots[rid]['frames']
                inspect = [f for f in frames if all(f['commanded_servo'].get(k) == v for k, v in R.INSPECT.items())][-3:]
                if not inspect:
                    continue
                after = frames[frames.index(inspect[-1]) + 1:]
                descended = [f for f in after if f['commanded_servo'].get('3', 0) > R.INSPECT['3']]
                if not descended:
                    continue
                last = max(descended, key=lambda f: f['commanded_servo']['3'])
                grasp = [f for f in after if f['commanded_servo'] == last['commanded_servo']]
                track = new.GraspRangeBeamTrack()
                if not any(track.observe_standoff(*R.load(case, rid, f), 3) for f in reversed(inspect)):
                    unanchored += 1
                    continue
                for f in grasp:
                    obs, servo = R.load(case, rid, f)
                    pts = new.grasp_range_points(obs['image'], servo)
                    a, b = decide(old, pts, track.beam), decide(new, pts, track.beam)
                    total += 1
                    if a != b:
                        differ += 1
                        rows.append((raw.name, case.name, rid, f['frame_id'], a, b))
    for row in rows:
        print('DIFF', *row)
    summary = {'old_commit': commit, 'frames': total, 'decisions_differ': differ, 'robots_unanchored': unanchored}
    print(json.dumps(summary))
    return summary


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
