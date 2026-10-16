"""REVIEW_363 P1-4 re-run: reviewer's 3 headless conditions + v96 grip monitor.

Physics, scene, commands and the three injections are exactly the reviewer's
(outputs/review-363-20261003/headless_review.py over probe_headless.py): 52 SIM s,
no renderer, no model, no student, weld OFF.

What is new: every 0.1 s, for r1/r2, a GEOMETRIC STAND-IN of the own view is
built on the evaluation side (actual camera pose + actual beam boxes; bar painted
beam colour, grip bands dark, nothing else) and fed to the v96 decision code
(harness.zone_pair_highpose_grip.relation / TransitMonitor stability /
owncam_pair_hold_v3.hold_iou) with the robot's own ISSUED PWM. This measures
whether the decision logic separates normal motion from grip loss on real
physics trajectories. It is NOT RGB detector validation (no lighting, texture,
JPEG, arm/jaw occlusion), not a student run and not P03/E2E.

For the grip-loss condition the injected gripper-open command is hidden from the
monitor (it sees a closed gripper), so only the RGB-path detection is measured.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from scripts.run_final_environment_checks import write, check_source  # noqa: E402
from harness import zone_final_pair_contract as c  # noqa: E402
from harness import zone_pair_highpose as pose  # noqa: E402
from harness import zone_pair_highpose_grip as grip  # noqa: E402
from harness import owncam_pair_hold_v3 as hv3  # noqa: E402
from harness.owncam_view import _pixel_rays  # noqa: E402

COLOUR = None
CARRIERS = ('r1', 'r2')
WINDOWS = {'raise': (10., 27.2), 'high': (27.2, 34.), 'lower': (34., 47.6), 'floor_return': (47.6, 49.)}


def probe():
    spec = importlib.util.spec_from_file_location('probe_headless', HERE.parent/'probe_headless.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stand_in(model, data, rid, rays4):
    """4-px grid first-hit of the actual beam parts -> BGR stand-in frame."""
    import cv2
    global COLOUR
    if COLOUR is None:
        COLOUR = cv2.cvtColor(np.uint8([[[40, 190, 205]]]), cv2.COLOR_HSV2BGR)[0, 0]
    xs, ys, normal, valid = rays4
    cam = data.camera(rid+'__robot_cam')
    origin = cam.xpos.copy()
    axes = cam.xmat.reshape(3, 3) @ np.diag([1., -1., -1.])
    optical = np.column_stack((normal, np.ones(len(normal))))
    optical /= np.linalg.norm(optical, axis=1)[:, None]
    rays = optical @ axes.T
    near = float(model.stat.extent*model.vis.map.znear)
    entries = []
    for part in ('bar', 'band_neg', 'band_pos'):
        gid = model.geom('cargo_beam__'+part).id
        rot = data.geom_xmat[gid].reshape(3, 3)
        o, v, half = rot.T @ (origin-data.geom_xpos[gid]), rays @ rot, model.geom_size[gid]
        with np.errstate(divide='ignore', invalid='ignore'):
            a, b = (-half-o)/v, (half-o)/v
        enter, leave = np.max(np.minimum(a, b), axis=1), np.min(np.maximum(a, b), axis=1)
        entries.append(np.where(leave >= np.maximum(enter, 0.), enter, np.inf))
    entries = np.asarray(entries)
    first = entries.argmin(axis=0)
    depth = entries.min(axis=0)*(rays @ axes[:, 2])
    hit = valid & np.isfinite(entries.min(axis=0)) & (depth >= near)
    small = np.full((120, 160, 3), 155, np.uint8)
    flat = small.reshape(-1, 3)
    flat[hit & (first == 0)] = COLOUR
    flat[hit & (first > 0)] = (20, 20, 20)
    return cv2.resize(small, (640, 480), interpolation=cv2.INTER_NEAREST)


def issued_servo(events, rid, t, hide_open):
    servo = {}
    for e in events:
        if e['robot_id'] != rid or e['t'] > t+1e-8:
            continue
        a = e['action']
        if a['kind'] == 'arm':
            servo[a['servo_id']] = a['pulse']
        elif a['kind'] == 'look':
            servo[6] = a['pan_pulse']
    if hide_open:
        servo[1] = 1500
    return servo


class Track:
    """Per-robot decision trace (own image + own issued PWM only)."""

    def __init__(self, rid, events, hide_open, shift=0.):
        self.rid, self.events, self.hide_open = rid, events, hide_open
        # Own schedule offset (delay condition): the robot's own queue is
        # consistent; windows follow its own raise/lower. The reviewer's open
        # command at 49 s is not shifted, so a shifted floor window is skipped.
        self.windows = {k: (a+shift, b+shift) for k, (a, b) in WINDOWS.items()}
        if shift:
            self.windows['floor_return'] = (0., 0.)
        own = [e for e in events if e['robot_id'] == rid and e['action']['kind'] in ('arm', 'look')]
        self.raise_events = [(e['t'], e['action'].get('servo_id', 6), e['action'].get('pulse', e['action'].get('pan_pulse')))
                             for e in own if 10.+shift-1e-8 <= e['t'] < 34.+shift-1e-8]
        self.rows, self.floor_anchor, self.high_anchor = [], None, None
        self.monitor = None
        self.first_fail = {}
        self.stable_at = None

    def sample(self, t, image):
        servo = issued_servo(self.events, self.rid, t, self.hide_open)
        if self.floor_anchor is None and t >= 3.5-1e-8:
            self.floor_anchor = hv3.hold_view_mask(image).copy()   # closed at floor, before lift
        window = next((name for name, (a, b) in self.windows.items() if a-1e-8 <= t < b-1e-8), None)
        if window is None:
            return
        rel = grip.relation(image, servo)
        row = {'t': round(t, 3), 'window': window, 'relation_ok': rel['ok'],
               'coverage': rel.get('coverage'), 'iou': rel.get('iou'), 'support': rel.get('support'),
               'slope_delta': rel.get('edge_slope_delta'), 'at_high': pose.at_high(servo)}
        if window == 'raise':
            if self.monitor is None:
                t0 = self.windows['raise'][0]
                start = issued_servo(self.events, self.rid, t0-1e-6, self.hide_open)
                # queue end = raise start + 3 x (move + settle), as in the runtime
                until = t0+sum(d+s for _, d, s in pose.raise_path())
                self.monitor = grip.TransitMonitor('raise', t0, start, self.raise_events, until, 1)
            self.monitor._stability(t, {'image': image}, servo)
            if self.monitor.stable(t) and self.stable_at is None and t >= self.monitor.until-1e-8:
                self.stable_at = t
        if window == 'high' and self.high_anchor is None and rel['ok']:
            self.high_anchor = hv3.hold_view_mask(image).copy()
        if window == 'high' and self.high_anchor is not None:
            row['high_hold_iou'] = hv3.hold_iou(self.high_anchor, image)
        if window == 'floor_return' and self.floor_anchor is not None:
            row['floor_iou'] = hv3.hold_iou(self.floor_anchor, image)
        if not rel['ok'] and window not in self.first_fail:
            self.first_fail[window] = row['t']
        self.rows.append(row)

    def summary(self):
        out = {'first_relation_failure_s': self.first_fail,
               'raise_end_stable_at_s': self.stable_at}
        for name in WINDOWS:
            rows = [r for r in self.rows if r['window'] == name]
            out[name] = {'samples': len(rows), 'relation_ok': sum(r['relation_ok'] for r in rows)}
            if name == 'high':
                ious = [r['high_hold_iou'] for r in rows if 'high_hold_iou' in r]
                out[name]['hold_iou_min'] = min(ious) if ious else None
                out[name]['hold_ok'] = sum(i >= hv3.HOLD_MIN_IOU for i in ious)
            if name == 'floor_return':
                ious = [r['floor_iou'] for r in rows if 'floor_iou' in r]
                out[name]['floor_iou_max'] = max(ious) if ious else None
                out[name]['floor_iou_min'] = min(ious) if ious else None
            cov = [r['coverage'] for r in rows if r['coverage'] is not None]
            out[name]['coverage_min'] = min(cov) if cov else None
        # Would-abort time of the RGB path: the first failed transit sample.
        fails = [self.first_fail[w] for w in ('raise', 'high', 'lower') if w in self.first_fail]
        out['rgb_monitor_first_abort_s'] = min(fails) if fails else None
        return out


def main(out_root, sha):
    check_source(sha)
    p = probe()
    rays4 = _pixel_rays(4)
    out_root.mkdir(parents=True, exist_ok=False)
    summaries = {}
    for name, delay, slip in [('nominal', 0., False), ('partner_delay_2s', 2., False), ('raise_grip_loss', 0., True)]:
        out = out_root/name
        out.mkdir()
        events = copy.deepcopy(p.commands())
        if delay:
            for row in events:
                if row['robot_id'] == 'r2' and 10 < row['t'] < 49:
                    row['t'] = round(row['t']+delay, 8)
        if slip:
            events = [e for e in events if not (e['robot_id'] == 'r2' and e['t'] >= 12. and e['action'].get('servo_id') == 1)]
            events.append({'t': 12., 'robot_id': 'r2', 'action': {'kind': 'arm', 'servo_id': 1, 'pulse': 2000}})
        events.sort(key=lambda row: row['t'])
        bundle = c.bundle('zone_wide_two_doors_final_v3', 'calibration-loaded')
        write(out/'commands.json', events)
        result = {'source_sha': sha, 'driver_sha256': c.base.sha(Path(__file__)), 'injection': name,
                  'loadavg_start': list(os.getloadavg()), 'sim_s': 52., 'commands': len(events), 'model_calls': 0,
                  'renders': 0, 'weld': False, 'status': 'HOST_ERROR', 'physical_success': None,
                  'method': __doc__.strip().splitlines()[0]}
        tracks = {rid: Track(rid, events, hide_open=slip and rid == 'r2', shift=delay if rid == 'r2' else 0.)
                  for rid in CARRIERS}
        gt = []
        backend = None
        try:
            backend = p.Headless(bundle, out, seed=911)
            backend.reset(5.)
            start = backend.now
            backend.set_deadline(start+52.)
            j = 0
            m, d = backend.world.model, backend.world.data
            for i in range(1041):
                t = round(i*.05, 8)
                backend.eval_sample()
                if i % 2 == 0:
                    for rid in CARRIERS:
                        tracks[rid].sample(t, stand_in(m, d, rid, rays4))
                    gid = m.geom('cargo_beam__bar').id
                    z = d.geom_xmat[gid].reshape(3, 3)[:, 0]
                    gt.append({'t': t, 'beam_z_m': float(d.geom_xpos[gid][2]),
                               'tilt_deg': float(np.degrees(np.arcsin(abs(z[2]))))})
                if i == 1040:
                    break
                while j < len(events) and events[j]['t'] <= t+1e-8:
                    e = events[j]
                    backend.issue(e['robot_id'], e['action'])
                    j += 1
                backend.advance_to(start+(i+1)*.05)
            assert j == len(events)
            result['status'] = 'HEADLESS_CHECK_COMPLETE'
        except Exception as exc:
            result['failure'] = repr(exc)
            raise
        finally:
            if backend is not None:
                backend.close()
            result['loadavg_end'] = list(os.getloadavg())
            result['robots'] = {rid: tr.summary() for rid, tr in tracks.items()}
            result['eval_only_beam'] = {'max_tilt_deg_raise_high': max(g['tilt_deg'] for g in gt if 10 <= g['t'] < 34),
                                        'min_bar_z_high_m': min(g['beam_z_m'] for g in gt if 27.2 <= g['t'] < 34)}
            write(out/'samples.json', {rid: tr.rows for rid, tr in tracks.items()})
            write(out/'eval_only_beam.json', gt)
            write(out/'summary.json', result)
            write(out/'artifacts.sha256.json', {str(f.relative_to(out)): c.base.sha(f)
                  for f in sorted(out.rglob('*')) if f.is_file() and f.name != 'artifacts.sha256.json'})
        summaries[name] = result
        print(json.dumps({'name': name, 'robots': result['robots'], 'beam': result['eval_only_beam']}), flush=True)
    write(out_root/'headless_grip_monitor.json', summaries)


if __name__ == '__main__':
    out_root, sha = Path(sys.argv[1]), sys.argv[2]
    primary = Path('/Users/changmin/projects/ugrp/outputs')
    if not out_root.is_absolute() or not out_root.resolve().is_relative_to(primary):
        raise SystemExit('raw output must be absolute under primary outputs')
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise SystemExit('HOST_ERROR: ENOSPC (<10 GiB free)')
    main(out_root, sha)
