"""Dev closed-loop check of ``vision_zero_tag_v1`` (issue #216): one robot, zero tags, own camera only.

"dev closed-loop check, 연구 결과 아님". M1 style: one robot delivers the episode's cyan box through the
door with the own-camera executor (#206, ``kiro/zone-own-executor`` 6fde2607 merged) whose pose
provider is the tag-free vision provider (``harness/vision_pose_source.py``, torch worker out of
process). The two other robots hold at their docks for the whole run.

Scene: environment v3 (walls_v3, 0.40 m) with ZERO AprilTags = PR #233's ``TagFreeZoneScene`` on
``zone_wide_door``. ``sim/zone_arena.py``, ``sim/zone_scene.py``, ``sim/zone_landmarks.py`` and
``sim/zone_tag_rule_v3.py`` are loaded at run time from the pinned v3 source commit (``V3_SOURCE_SHA``,
``kiro/zone-map-v3``; the same commit the VIS3 renders ran) as git blobs, hash-recorded; no file of
those owners is edited or merged. Episode = VIS3 round-3 DEV ``vl3-dev-s942`` (seed, spawn offset,
box, slot); no v3 test seed. cargo_noslip_v1, weld OFF, SYNC SIM.

Robot inputs: own robot_cam frames, own issued commands, the static tag-free map, fixed calibrations,
static idle-spawn discs, the order sheet and the start prior (own dock row of the static layout, from
the scenario setup; the setup-only spawn offset is not given). Simulator truth goes to ``eval_only/``
only and is read after the run for the localization error, door pass and delivery.

Usage (from the worktree root, under ``scripts/ugrp_session.py run`` and the physics agent lock):
    python experiments/2026-09-27-vision-worker-closed-loop/run_dev_check.py --output <primary outputs dir>
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
V3_SOURCE_SHA = '7cedb0490b3802088df5b5f789566657aebd82d0'
V3_MODULES = ('zone_arena', 'zone_scene', 'zone_tag_rule_v3', 'zone_landmarks')
EPISODE = 'vl3-dev-s942'
ACTIVE_SLOT = 'A2'
SIM_LIMIT_S = 900.
SCHEMA = 'ugrp.vision_worker_closed_loop_dev.v1'
LABEL = 'dev closed-loop check, 연구 결과 아님'


def git(*args) -> str:
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def overlay_v3_sim() -> dict:
    """Load the four v3 zone modules from the pinned commit before anything imports them."""
    import hashlib

    import sim
    record = {}
    for name in V3_MODULES:
        rel = f'sim/{name}.py'
        code = subprocess.run(['git', 'show', f'{V3_SOURCE_SHA}:{rel}'], cwd=ROOT, capture_output=True,
                              check=True).stdout
        module = types.ModuleType(f'sim.{name}')
        module.__file__ = str(ROOT / rel)                  # MAP_DIR = <worktree>/maps/zones (base maps unchanged)
        sys.modules[module.__name__] = module
        setattr(sim, name, module)
        exec(compile(code, f'{V3_SOURCE_SHA[:8]}:{rel}', 'exec'), module.__dict__)
        record[rel] = {'source': f'{V3_SOURCE_SHA}:{rel}', 'sha256': hashlib.sha256(code).hexdigest()}
    return record


def episode_spec() -> dict:
    table = json.loads((ROOT / 'experiments' / '2026-09-26-vision-loc' / 'episodes_v3.json').read_text())
    row = next(e for e in table['episodes'] if e['episode_id'] == EPISODE)
    if row['split'] != 'dev':
        raise SystemExit(f'{EPISODE} is not a dev episode')
    return row


def install_scene(row, state):
    """``TaggedZoneScene.from_tagged`` -> PR #233 ``TagFreeZoneScene`` (the host builds the scene by name)."""
    sys.path.insert(0, str(ROOT / 'experiments' / '2026-09-26-vision-loc'))
    import tagfree_scene

    import sim.zone_landmarks as zl
    scene_cls = tagfree_scene.make_scene_class()

    class TagFreeShim:
        @classmethod
        def from_tagged(cls, name, seed, goal, extra_boxes=None, contact_profile=None):
            if name != tagfree_scene.map_id('zone_wide_door'):
                raise ValueError(f'dev check expects {tagfree_scene.map_id("zone_wide_door")}, got {name}')
            return scene_cls.from_tagfree('zone_wide_door', seed, goal, extra_boxes, contact_profile=contact_profile,
                                          spawn_offset=state['spawn_offset'])
    zl.TaggedZoneScene = TagFreeShim
    return tagfree_scene


def make_host_class(state):
    from harness.vision_pose_source import PRIOR_STD, VisionPoseSource
    from harness.zone_own_team_host import OwnCamTeamHost
    from sim.zone_arena import layout

    class VisionHost(OwnCamTeamHost):
        """#206 host; the active robot's pose provider is ``vision_zero_tag_v1`` (as PR #229's seam does)."""

        def __init__(self, spec, student, **kw):
            super().__init__(spec, student, **kw)
            rid = state['rid']
            ex = self.robots[rid].executor
            arena = layout(self.static['base_map']['map_id'])
            row_y = min(arena['spawn_rows_y'], key=lambda y: abs(y - self.spawns[rid][1]))  # own dock row (setup)
            provider = VisionPoseSource(ex.map, ex.params, seed=int(spec['seed']))
            self.vision = provider
            for row in self.robots[rid].commands:            # own command log so far (initial servo command)
                provider.on_command(row)
            provider.init_prior((float(arena['spawn_x']), float(row_y), 0.), PRIOR_STD,
                                source='scenario setup: own start dock row of the static layout '
                                       '(sim.zone_arena.layout spawn_x/spawn_rows_y); setup-only offset not given')
            ex._require_owncam(provider.source, 'pose provider')
            ex.pose = provider

        def close(self):
            try:
                self.vision.close()
            finally:
                super().close()
    return VisionHost


def plan(row, static, spawns, objects, rid):
    from harness.zone_own_executor import pickup_slot_of, zone_slot
    cyan = [(oid, o) for oid, o in objects.items() if o['kind'] == 'cyan']
    if len(cyan) != 1:
        raise SystemExit(f'expected one cyan box, got {len(cyan)}')
    oid, obj = cyan[0]
    zone_slot(static, row['slot_id'])
    slot = pickup_slot_of(static, obj['position_m'][:2])
    sheet = {'schema': 'ugrp.zone_own_executor_order_sheet.v1', 'map_id': static['map_id'],
             'orders': [{'order_id': 'o1', 'kind': 'cyan', 'count': 1, 'required_robots': 1,
                         'destination_zone': row['slot_id'][0],
                         'initial_location': {'pickup_bay': slot.split('-')[0], 'slot': slot}}],
             'source': 'scenario config (sim.zone_arena.episode setup placement -> coarse pickup slot)'}
    jobs = {r: ({'hold_s': 0, 'order_id': 'o1', 'zone_slot': row['slot_id']} if r == rid else {'hold_s': SIM_LIMIT_S})
            for r in spawns}
    return sheet, jobs, {rid: oid}


def layer(jobs, state):
    def study_layer(host, kind, event, now):
        """Scripted no-LLM layer: reads executor events only."""
        if kind == 'start':
            for r, job in jobs.items():
                if job['hold_s'] > 0:
                    host.call(r, 'hold', job['hold_s'])
                else:
                    state['deliver_job'] = host.call(r, 'deliver', job['order_id'], job['zone_slot'])['job_id']
            return
        if event['robot_id'] == state['rid'] and event['event'] in ('job_done', 'job_failed') \
                and event['job_id'] == state.get('deliver_job'):
            state['finished'] = True
    return study_layer


def evaluate(host, rid, door) -> dict:
    """Evaluation only (after the run): own-estimate error vs GT, door pass from the GT trajectory."""
    rows = [r for r in host.eval_only['frames_eval'] if r['robot_id'] == rid]
    est = [r for r in rows if 'pos_err_m' in r]

    def stats(vals):
        v = sorted(vals)
        return None if not v else {'n': len(v), 'p50': v[len(v) // 2], 'p90': v[min(len(v) - 1, int(.9 * len(v)))],
                                   'max': v[-1]}
    dx, dy = door['center_m']
    near = [r for r in est if math.hypot(r['gt'][0] - dx, r['gt'][1] - dy) <= .5]
    traj = [(g['t'], *g['robots'][rid]) for g in host.eval_only['gt']]
    crossings = [{'t': b[0], 'y_m': round(b[2], 4), 'lateral_off_m': round(b[2] - dy, 4)}
                 for a, b in zip(traj, traj[1:]) if a[1] < dx <= b[1]]
    return {'frames': len(rows), 'frames_initialized': len(est),
            'pos_err_m': stats([r['pos_err_m'] for r in est]), 'yaw_err_deg': stats([r['yaw_err_deg'] for r in est]),
            'near_door_pos_err_m': stats([r['pos_err_m'] for r in near]),
            'door_crossings_west_to_east': crossings, 'door_passed': bool(crossings),
            'max_x_m': round(max(t[1] for t in traj), 4) if traj else None}


def write_result(out, host, row, rid, run, robot, ev, spec, student, sheet, code, load0, started):
    import cv2
    import mujoco
    import numpy as np

    from harness import vision_loc_protocol as vp
    result = {'schema': SCHEMA, 'label': LABEL, 'research_result': False, 'episode': EPISODE, 'split': 'dev',
              'seed': row['seed'], 'robot': rid, 'run': run, 'sim_s': run['sim_s'],
              'deliver_outcome': robot['deliver_outcome'], 'deliver_confirmation': robot['deliver_confirmation'],
              'm1_success': robot['m1_success'], 'm1_failed_checks': robot.get('m1_failed_checks'),
              'assigned_box_in_slot': robot['evaluation_only']['assigned_box_in_slot'],
              'false_confirmation': robot['evaluation_only']['false_confirmation'],
              'evaluation_only_localization': ev, 'vision_provider': host.vision.record(),
              'weld_max_eq_active': host.eval_only['max_eq_active'], 'contact_profile': host.contact_record,
              'robot_result': robot, 'order_sheet': sheet}
    manifest = {'schema': SCHEMA, 'label': LABEL, 'code': code, 'spec': {k: v for k, v in spec.items() if k != 'order_sheet'},
                'episode_row': row, 'student': student, 'static_map_sha256': host.scene.manifest.get('static_map_sha256'),
                'tag_count': host.scene.manifest.get('tag_count'), 'scene_xml_sha256': vp.sha256_bytes(host.world.scene_xml.encode()),
                'sync_sim': True, 'frame_period_s': host.FRAME_S, 'weld': 'off',
                'env': {'python': sys.version.split()[0], 'mujoco': mujoco.__version__, 'opencv': cv2.__version__,
                        'numpy': np.__version__, 'threads': {k: os.environ.get(k) for k in (
                            'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')}},
                'load_average': {'start': load0, 'end': os.getloadavg()}, 'wall_s': round(time.time() - started, 1)}
    manifest['files'] = {str(q.relative_to(out)): vp.file_sha256(q) for q in sorted(out.rglob('*'))
                         if q.is_file() and q.suffix in ('.jsonl', '.json', '.xml') and q.name != 'manifest.json'}
    (out / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + '\n')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + '\n')
    print(json.dumps({k: result[k] for k in ('episode', 'robot', 'sim_s', 'deliver_outcome', 'm1_success',
                                             'assigned_box_in_slot')} | {'door_passed': ev['door_passed'],
                                                                         'pos_err_m': ev['pos_err_m'],
                                                                         'wall_s': manifest['wall_s']}, default=str),
          flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--sim-limit-s', type=float, default=SIM_LIMIT_S)
    args = p.parse_args(argv)
    started, load0 = time.time(), os.getloadavg()
    out = args.output / EPISODE
    out.mkdir(parents=True, exist_ok=False)                      # never overwrite
    overlay = overlay_v3_sim()
    row = episode_spec()
    state = {'finished': False, 'spawn_offset': None}
    tagfree = install_scene(row, state)
    sys.path.insert(0, str(ROOT / 'experiments' / '2026-09-26-zone-own-executor'))
    import run_smoke_v2 as v2
    from harness import vision_loc_protocol as vp
    from sim.zone_arena import episode as zone_episode
    cfg = zone_episode('zone_wide_door', row['seed'], goal=row['goal'], extra_boxes=row['extra_boxes'])
    spawns = cfg['setup_only']['spawns']
    rid = state['rid'] = min(spawns, key=lambda r: abs(spawns[r][1] - row['spawn_y']))
    off = row['spawn_offset']
    state['spawn_offset'] = {rid: [float(off[0]), float(off[1]), math.radians(float(off[2]))]}
    static = tagfree.load_map('zone_wide_door')
    sheet, jobs, assigned = plan(row, static, spawns, cfg['setup_only']['objects'], rid)
    prereg = json.loads((ROOT / 'experiments' / '2026-09-26-zone-own-executor' / 'prereg_v3.json').read_text())
    spec = {'episode_id': EPISODE, 'seed': row['seed'], 'map': static['map_id'], 'base_map': 'zone_wide_door',
            'goal': row['goal'], 'extra_boxes': row['extra_boxes'], 'contact_profile': 'cargo_noslip_v1',
            'job_sim_limit_s': 720, 'order_sheet': sheet}
    student = dict(prereg['student'])
    code = {'sha': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain', '--', 'harness', 'sim',
                                                                'scripts', 'configs', 'experiments')),
            'v3_sim_overlay': overlay, 'vision_frozen_sha256': vp.check_frozen(),
            'runtime_files_sha256': {f: vp.file_sha256(ROOT / f) for f in v2.RUNTIME_FILES + (
                'harness/vision_pose_source.py', 'harness/vision_loc_client.py', 'harness/vision_loc_protocol.py',
                'scripts/vision_loc_worker.py', 'configs/vision_loc_worker.json',
                'experiments/2026-09-27-vision-worker-closed-loop/run_dev_check.py') if (ROOT / f).exists()}}
    (out / 'attempt_started.json').write_text(json.dumps({'label': LABEL, 'episode': EPISODE, 'robot': rid, 'code': code,
                                                          'sim_limit_s': args.sim_limit_s, 'load_average_start': load0,
                                                          'started_unix': round(started, 3)}, indent=2) + '\n')
    host, stage, run, exc_rec = None, 'setup', None, None
    try:
        host = make_host_class(state)(spec, student, root=ROOT, study_layer=layer(jobs, state), frames_dir=out / 'frames')
        stage = 'run'
        run = host.run(args.sim_limit_s, done=lambda: state['finished'])
        stage = 'results'
        slot = host.robots[rid]
        robot = v2.robot_result(rid, slot, host, spec, jobs, assigned, sheet, prereg)
        ev = evaluate(host, rid, next(q for q in static['passages'] if q['kind'] == 'door'))
    except BaseException as exc:                                  # noqa: BLE001 - record, close, re-raise
        exc_rec = {'stage': stage, 'type': type(exc).__name__, 'message': str(exc)[:2000],
                   'traceback': traceback.format_exc()[-6000:]}
        raise
    finally:
        if host is not None:
            try:
                v2.write_logs(out, host, EPISODE, row['seed'])
                (out / 'robots' / rid / 'vision_provider.json').write_text(
                    json.dumps(host.vision.record(), indent=1, default=str) + '\n')
                v2.jsonl(out / 'robots' / rid / 'vision_timing.jsonl', host.vision.timing)
            except Exception as log_exc:                          # noqa: BLE001
                exc_rec = {**(exc_rec or {}), 'partial_log_error': f'{type(log_exc).__name__}: {log_exc}'}
        if exc_rec is not None:
            (out / 'failure.json').write_text(json.dumps({'label': LABEL, 'exception': exc_rec, 'code': code,
                                                          'sim_s': None if host is None else round(float(host.world.data.time), 3),
                                                          'load_average': {'start': load0, 'end': os.getloadavg()},
                                                          'wall_s': round(time.time() - started, 1)}, indent=2,
                                                         default=str) + '\n')
        if host is not None:
            host.close()
    write_result(out, host, row, rid, run, robot, ev, spec, student, sheet, code, load0, started)


if __name__ == '__main__':
    main()
