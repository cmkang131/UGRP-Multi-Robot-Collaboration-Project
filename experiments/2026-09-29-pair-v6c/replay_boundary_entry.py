"""Offline replay of the recorded grasp-entry boundary frames (no physics, no models).

Input: a PR #260 stage-probe raw directory (``pair-stage-probes-*-bound``). For
every v5h boundary case and robot it replays the exact own RGB frames and the
issued PWM through

* the standoff fit (v1 lime ``standoff_estimate`` vs v6c ``standoff_estimate_v6c``)
  on the last three inspect-pose frames, and
* the pre-close partial check (``RestingBeamTrack`` vs ``GraspRangeBeamTrack``
  ``estimate``) on the first four frames at the final descent pose, anchored by
  the last standoff frame that the same model could fit.

The staged offset in the case id is a label only (eval); nothing here feeds a
controller. Usage:  python replay_boundary_entry.py <raw dir>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.zone_pair_beam_track import RestingBeamTrack, standoff_estimate  # noqa: E402
from harness.zone_pair_grasp_entry_v6c import GraspRangeBeamTrack, standoff_estimate_v6c  # noqa: E402

INSPECT = {'3': 508, '4': 2432}   # standoff inspect pose (issued PWM)


def load(case, rid, f):
    data = (case/'frames'/rid/f"{f['frame']:05d}.jpg").read_bytes()
    obs = {'image': data, 'frame_id': f['frame_id'], 'sha256': hashlib.sha256(data).hexdigest(),
           'sim_time': f['t']}
    return obs, {int(k): v for k, v in f['commanded_servo'].items()}


def replay(case, rid):
    frames = json.loads((case/'robots.json').read_text())[rid]['frames']
    inspect = [f for f in frames if all(f['commanded_servo'].get(k) == v for k, v in INSPECT.items())][-3:]
    # Grasp pose = the deepest issued pose AFTER the inspect pose; a robot that
    # never descended (its pair stopped at the standoff) has no grasp-pose frame.
    after = frames[frames.index(inspect[-1]) + 1:] if inspect else []
    descended = [f for f in after if f['commanded_servo'].get('3', 0) > INSPECT['3']]
    grasp = []
    if descended:
        last = max(descended, key=lambda f: f['commanded_servo']['3'])
        grasp = [f for f in after if f['commanded_servo'] == last['commanded_servo']][:4]
    row = {}
    for name, fit, cls in (('lime', standoff_estimate, RestingBeamTrack),
                           ('v6c', standoff_estimate_v6c, GraspRangeBeamTrack)):
        ok = [fit(*load(case, rid, f)) is not None for f in inspect]
        track = cls()
        anchored = False
        for f in reversed(inspect):
            if track.observe_standoff(*load(case, rid, f), 3):
                anchored = True
                break
        patch = []
        if anchored:
            for f in grasp:
                obs, servo = load(case, rid, f)
                patch.append(track.estimate(obs['sim_time'], obs, servo, 3) is not None)
        row[name] = {"standoff_ok": ok, "anchored": anchored, "descended": bool(grasp), "grasp_pose_patch_ok": patch}
    return row


def main(raw):
    raw = Path(raw)
    out = {}
    # v5h cases carry no policy tag in their id (grasp_lift_boundary_<cell>_s911).
    for case in sorted(p for p in (raw/'cases').iterdir()
                       if p.is_dir() and not any(tag in p.name for tag in ('b-only', 'a+b', 'b-v6c'))):
        if not (case/'robots.json').exists():
            continue
        out[case.name] = {rid: replay(case, rid) for rid in ('r1', 'r2')}
    tally = {m: {'standoff_frames_failed': 0, 'standoff_frames': 0, 'unanchored': 0,
                 'grasp_pose_frames_failed': 0, 'grasp_pose_frames': 0} for m in ('lime', 'v6c')}
    for case, robots in out.items():
        cells = []
        for rid, row in robots.items():
            for m, r in row.items():
                t = tally[m]
                t['standoff_frames'] += len(r['standoff_ok'])
                t['standoff_frames_failed'] += r['standoff_ok'].count(False)
                t['unanchored'] += not r['anchored']
                t['grasp_pose_frames'] += len(r['grasp_pose_patch_ok'])
                t['grasp_pose_frames_failed'] += r['grasp_pose_patch_ok'].count(False)
            cells.append(f"{rid} lime so{sum(row['lime']['standoff_ok'])}/{len(row['lime']['standoff_ok'])} "
                         f"gp{sum(row['lime']['grasp_pose_patch_ok'])}/{len(row['lime']['grasp_pose_patch_ok'])} | "
                         f"v6c so{sum(row['v6c']['standoff_ok'])}/{len(row['v6c']['standoff_ok'])} "
                         f"gp{sum(row['v6c']['grasp_pose_patch_ok'])}/{len(row['v6c']['grasp_pose_patch_ok'])}")
        print(case.replace('grasp_lift_', ''), '::', ' || '.join(cells))
    print(json.dumps(tally, indent=1))
    return out, tally


if __name__ == '__main__':
    main(sys.argv[1])
