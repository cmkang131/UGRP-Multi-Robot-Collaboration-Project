#!/usr/bin/env python3
"""Short, stage-scoped physics probes for the own-camera pair-carry controller.

Stage probe, NOT E2E success. Each case starts from a staged state, runs ONLY
one controller stage (the merged v5h PairTeam/M2 controller, unchanged) and
stops with pass/fail and stage metrics. Cases run in parallel subprocesses
(OMP_NUM_THREADS=2 each). No model calls. weld OFF, cargo_noslip_v1.

  plan only (no MuJoCo):   run_pair_stage_probes.py --stage align --output <dir>
  physical grid:           ... --execute --lock-owner claude --output /abs/<primary>/outputs/<name>

Design, boundary and citations: experiments/2026-09-28-pair-stage-probes/README.md
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import copy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import pair_stage_probe as sp  # noqa: E402

WORKFLOW = 'pair-stage-probes'
E2E_DEFAULT = Path('/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v6-3c26acddec066adcd9164e6d2a6f51c1261c5f66')
E2E_RUNS = ('v6-s911-v5h', 'v6-s912-v5h')
MAP_ID = 'zone_wide_door_tags_v2_dock_v3'
CALIBRATION = 'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'
ORDER = {'orders': [{'order_id': 'cargoX', 'kind': 'long_beam', 'count': 1, 'required_robots': 2,
                     'destination_zone': 'B', 'initial_location': {'pickup_bay': 'P2', 'slot': 'P2-3'}}]}
SAMPLE_S = .05


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=_jsonable) + '\n')


def _jsonable(v):
    import numpy as np
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (set, tuple)):
        return list(v)
    raise TypeError(type(v).__name__)


def safe_name(case_id):
    return re.sub(r'[^A-Za-z0-9_.+-]+', '_', case_id)


# ================================================================== physical case (worker process)
class ProbeState:
    """Probe bookkeeping. Controller hooks WRITE here; nothing here is read by control."""
    def __init__(self, case):
        self.case = case
        self.stage = case['stage']
        self.spec = sp.STAGES[self.stage]
        self.exits = {}
        self.entry = {}
        self.entry_error = None
        self.acks = {}
        self.submitted = set()
        self.submit_t = None
        self.staging_start_t = None
        self.host = None  # set after construction; the GT snapshot callback only


def install_stage(ctl, execution, probe):
    """Wrap ONE real controller instance: stage entry on its first control tick,
    and a hold at the stage's exit transition. Controller logic is unchanged."""
    from harness import owncam_pair_beam as ob
    from harness import owncam_pair_beam_v2 as ob2
    from harness import owncam_pair_hold_v3 as hv3
    from scripts import study_owncam_pair_beam as study

    rid, spec, stage = execution.own.robot_id, probe.spec, probe.stage
    orig_tick = ctl.tick
    state = {'entered': False, 'grip_seen': False}

    def record_entry(now, **detail):
        r = execution.own.last_report
        probe.entry[rid] = {'sim_s': now, 'entry_state': spec['entry'],
                            'own_report': None if r is None else r.as_dict(), **detail}

    def entry(now):
        own = execution.own
        est = ctl.driver.loc.estimate()
        ctl.driver.outcome = 'arrived'
        ctl.arm.commanded.update({k: v for k, v in ctl.driver.servo.items() if k in ctl.arm.commanded})
        if stage == 'align':
            ctl.claims['at_prestation'] = {'estimate': [round(est['x'], 4), round(est['y'], 4), round(est['yaw'], 4)],
                                           'std_xy_m': round(est['std_xy_m'], 4), 'looks': 0, 'sim_time': now,
                                           'source': 'stage probe entry: own PF estimate at the staged approach end'}
            record_entry(now)
            return ctl.set('align_start', now, stage_probe_entry=True)
        report = own.last_report
        ctl.pregrasp_done = True
        ctl.pregrasp_started_at = probe.staging_start_t
        ctl.grasp_estimate = [report.x_m, report.y_m, report.yaw_rad]
        ctl.claims['grasp_pose_estimate'] = {'xyyaw': list(ctl.grasp_estimate), 'sim_time': now,
                                             'source': 'stage probe entry: shared own.pose/last_report'}
        ctl.look_name = ob2.look_posture(sp.GRASP_RADIUS_M)[0]
        if stage == 'grasp_lift':
            ctl.arm.queue(ob2.pose_of(ctl.look_name), now, duration=.8, settle=.3)
            record_entry(now, look_name=ctl.look_name)
            return ctl.set('pregrasp_standoff', now, stage_probe_entry=True)
        # Teacher-held beam (carry/setdown). The controller's grip belief is the
        # align target in its own base frame (a static constant, not GT).
        from harness.visual_arm import solve_grip_ik, tool_pose
        import numpy as np
        ctl.grip_base = [sp.GRASP_RADIUS_M, 0.]
        grasp = solve_grip_ik(ctl.grip_base[0], 0., study.GRASP_Z_M, -90)
        pitch = tool_pose(grasp).pitch_deg
        ctl.hover = solve_grip_ik(ctl.grip_base[0], 0., study.HOVER_Z_M, pitch)
        ctl.grasp_pose = [solve_grip_ik(ctl.grip_base[0], 0., float(h), pitch)
                          for h in np.linspace(study.HOVER_Z_M, study.GRASP_Z_M, 8)[1:]][-1]
        obs = ctl.look(now)
        ctl.anchor, ctl.anchor_kind = ob.held_signature(obs['image']), 'lime_v1'
        ctl.anchor_full = hv3.hold_view_mask(obs['image'])
        ctl.beam_grasp_receipt = {'segment': ctl.seg, 'frame_id': obs['frame_id'], 'sha256': obs['sha256'],
                                  'observed_at_s': obs['sim_time'], 'closed_command_at_s': probe.staging_start_t,
                                  'source': 'stage probe entry: own RGB + own issued (teacher) close'}
        ctl.claims['lifted'] = {'held_iou': None, 'sim_time': now, 'source': 'stage probe entry (teacher lift)'}
        if stage == 'setdown':
            ctl.seg = len(ctl.segments) - 1   # final segment: lower -> open -> release -> done
        elif probe.case.get('leg'):
            ctl.seg = int(probe.case['leg'])  # carry leg k: the controller's own segment index (route[k] -> route[k+1])
        record_entry(now, anchor_frame=obs['frame_id'], seg=ctl.seg)
        return ctl.set(spec['entry'], now, stage_probe_entry=True)

    def tick(now):
        if not state['entered']:
            state['entered'] = True
            entry(now)
            if ctl.state == 'failed':
                return
        if spec['exit_state'] and ctl.state == spec['exit_state']:
            ctl.status[1].tick(spec['exit_status'], now)
            if any(v['state'] == 'abort' for v in ctl.status[0].partner_view(ctl.rid, now).values()):
                ctl.port.hold(now)
                return ctl.fail('PARTNER_ABORT_AFTER_OWN_EXIT', now)
            return
        return orig_tick(now)

    ctl.tick = tick

    if stage == 'grasp_lift':
        orig_standoff = ctl._pregrasp_standoff

        def standoff(now, arm_idle):
            if not state['grip_seen']:
                if not arm_idle:
                    return
                # Own-RGB grip fix at the standoff view (what align's last aligned
                # view provides in the full sequence). A clipped/missing band fails.
                obs = ctl.look(now)
                beam = ob2.observe_beam(obs['image'], ctl.pose_of(obs))
                ctl.log(ctl.rid, 'stage_probe_grip_view', now,
                        **{k: v for k, v in beam.items() if k != 'provenance'})
                if not beam.get('visible') or not beam.get('end_visible') or beam.get('grip_base_m') is None:
                    probe.entry_error = probe.entry_error or 'GRIP_NOT_OBSERVED_AT_STANDOFF'
                    return ctl.fail('STAGE_ENTRY_GRIP_NOT_OBSERVED', now)
                state['grip_seen'] = True
                ctl.grip_base = list(beam['grip_base_m'])
                ctl.claims['aligned'] = {'grip_base_m': ctl.grip_base, 'errors': ob.align_errors(beam),
                                         'sim_time': now, 'source': 'stage probe entry own RGB'}
                return  # next control tick captures a fresh frame for the standoff check
            return orig_standoff(now, arm_idle)
        ctl._pregrasp_standoff = standoff
        orig_close = ctl._wait_close

        def wait_close(now, arm_idle):
            if arm_idle and ctl.state == 'wait_close' and execution.own.last_obs is not None:
                # Read-only diagnostics of the controller's own pre-close inputs (pure functions of
                # its own frame and issued PWM); the decision is still made by the original method.
                from scripts import run_m2_pair as m2
                own = execution.own
                view = m2.grip_view_m2(own.last_obs['image'])
                servo_match = {str(k): own.servo.get(k) == v for k, v in getattr(ctl, 'grasp_pose', {}).items() if k != 1}
                ctl.log(ctl.rid, 'stage_probe_close_view', now, grip_view_m2=view,
                        servo_open=own.servo.get(1) == study.OPEN, servo_match_all=all(servo_match.values()),
                        pregrasp_done=bool(ctl.pregrasp_done), source='own RGB + issued PWM (diagnostic only)')
            return orig_close(now, arm_idle)
        ctl._wait_close = wait_close

    hook = spec.get('exit_hook')
    if hook:
        def exit_now(now, *args, **kwargs):
            probe.exits[rid] = {'sim_s': now, 'from_state': ctl.state,
                                'claims': copy.deepcopy({k: v for k, v in ctl.claims.items()
                                                         if k in ('aligned', 'gripped', 'lifted', 'route_done')})}
            if probe.host is not None:
                probe.exits[rid]['gt'] = probe.host.gt_snapshot(rid)   # eval only, never returned to control
            ctl.port.hold(now)
            ctl.set(spec['exit_state'], now, stage_probe_exit=True)
        setattr(ctl, hook, exit_now)
    return ctl


def instrument_pose(pose, rid, log, clock):
    """Count the controller's own relook calls on its pose provider (pass-through, bookkeeping only)."""
    for name in ('begin_relocalization', 'begin_observation'):
        original = getattr(pose, name, None)
        if original is None:
            continue

        def wrapped(*a, _original=original, _name=name, **k):
            before = id(pose.loc)
            out = _original(*a, **k)
            log.append({'t': clock(), 'robot_id': rid, 'event': _name,
                        'localizer_object_replaced': id(pose.loc) != before,
                        'class': type(pose.loc).__name__})
            return out
        setattr(pose, name, wrapped)


def stage_global_anchor(anchors, log):
    """Probe-process-only: give each new PairCommandGuard the STATED global anchor (sp.staged_global_anchor).

    The v6 a+b global envelope otherwise starts empty and aborts at submission
    (GLOBAL_ANCHOR_UNKNOWN) because a staged entry has no approach fix. Only the
    envelope's starting anchor is set; its update/growth/expiry code is unchanged.
    """
    from harness import zone_pair_guards as guards
    from harness.zone_own_guards import OwnPose

    original = guards.PairCommandGuard.__init__

    def init(self, execution):
        original(self, execution)
        rid = execution.own.robot_id
        a = anchors.get(rid)
        if a is None or not self.relative_enabled:
            return
        now = float(execution.own.now)
        env = self.global_envelope
        env.anchor = OwnPose(*[float(v) for v in a['xyyaw']], float(a['std_xy_m']), float(a['std_yaw_rad']))
        env.fix_t, env.t = now - a['age_s'], now
        env._reset_motion()
        log.append({'t': now, 'robot_id': rid, 'event': 'staged_global_anchor', 'anchor': a})
    guards.PairCommandGuard.__init__ = init
    return original


def save_checkpoint(host, out, label):
    """mj_getState(mjSTATE_INTEGRATION) + each participant's PF state, with a bitwise restore check.

    Prototype of the E2E checkpoint design (README); probe bookkeeping only, never read by control.
    """
    import mujoco
    import numpy as np
    m, d = host.world.model, host.world.data
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mujoco.mj_stateSize(m, spec))
    mujoco.mj_getState(m, d, state, spec)
    probe_d = mujoco.MjData(m)
    mujoco.mj_setState(m, probe_d, state, spec)
    roundtrip = bool(np.array_equal(probe_d.qpos, d.qpos) and np.array_equal(probe_d.qvel, d.qvel)
                     and probe_d.time == d.time and np.array_equal(probe_d.ctrl, d.ctrl))
    arrays = {'mj_state_integration': state}
    meta = {'label': label, 'sim_s': float(d.time), 'mj_state_spec': 'mjSTATE_INTEGRATION', 'mujoco': mujoco.__version__,
            'state_size': int(state.size), 'roundtrip_bitwise': roundtrip, 'localizer': {}}
    for rid in sp.PARTICIPANTS:
        pose = host.robots[rid].executor.pose
        loc = pose.loc
        for key in ('px', 'logw', 'scale', 'vel', 'cmd'):
            arrays[f'{rid}_{key}'] = np.asarray(getattr(loc, key))
        meta['localizer'][rid] = {
            'class': type(loc).__name__, 'initialized': bool(loc.initialized), 't': float(loc.t),
            'cmd_expires': float(loc.cmd_expires), 'last_tag_t': loc.last_tag_t,
            'last_informative_t': getattr(loc, 'last_informative_t', None),
            'servo': {str(k): int(v) for k, v in loc.servo.items()}, 'loaded': bool(loc.load.loaded),
            'motion_profile': loc.motion_profile, 'stats': dict(loc.stats),
            'rng_state': loc.rng.bit_generator.state, 'provider_servo': {str(k): int(v) for k, v in pose.servo.items()},
            'recovery_v6': bool(getattr(pose, 'recovery_v6', False)),
            'exact_fix_clock_v6c': bool(getattr(pose, 'exact_fix_clock_v6c', False))}
    path = Path(out) / 'checkpoints' / f'{label}.npz'
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    write_json(path.with_suffix('.json'), meta)
    return {'label': label, 'sim_s': meta['sim_s'], 'npz': str(path.relative_to(out)), 'npz_sha256': sp.sha_file(path),
            'roundtrip_bitwise': roundtrip}


def run_case(case, out):
    """One staged case in THIS process. Returns the result row."""
    import mujoco
    import numpy as np

    from harness.zone_own_team_host import OwnCamTeamHost
    from harness.zone_pair_executor import m2_controller
    from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID
    from scripts.zone_pair_dev_runtime import make_scene
    from scripts.zone_teacher import ArmSequence
    from scripts import study_owncam_pair_beam as study

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    probe = ProbeState(case)
    stage = case['stage']
    spec_stage = sp.STAGES[stage]
    write_json(out / 'case.json', {**case, 'labels': sp.LABELS})
    sheet = case['coarse_order_sheet']
    spec = {'map': MAP_ID, 'seed': case['seed'], 'goal': {'B': {'cyan': 1}}, 'pair_policy': case.get('pair_policy', 'v5h'),
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': list(case['beam_xyyaw'])}],
            'pair_order_sheets': {'cargoX': sheet}, 'order_sheet': copy.deepcopy(ORDER),
            'contact_profile': 'cargo_noslip_v1', 'job_sim_limit_s': 900.}
    student = {'mode': 'm1', 'calibration': CALIBRATION,
               'skill_module': 'harness.wrist_zone_skill_v9', 'skill_class': 'WristZoneDeliveryV9'}
    scene = make_scene(spec)
    if case.get('render_profile'):     # opt-in visual profile (sim/render_profile.py); absent = unchanged behaviour
        from sim import render_profile as rp
        rp.install(scene, case['render_profile'])
    spawns = scene.config['setup_only']['spawns']
    z = spawns['r1'][2]
    for rid in sp.PARTICIPANTS:
        x, y, yaw = case['placement_xyyaw'][rid]
        spawns[rid] = [float(x), float(y), z, float(yaw)]
    if case.get('r3_xyyaw'):
        x, y, yaw = case['r3_xyyaw']
        spawns['r3'] = [float(x), float(y), z, float(yaw)]
    trace, loc_log, checkpoints = [], [], []

    class ProbeHost(OwnCamTeamHost):
        def enable_pair_carry(self, sheets, params, **kw):
            def factory(execution, plan, prm):
                return install_stage(m2_controller(execution, plan, prm), execution, probe)
            return super().enable_pair_carry(sheets, params, controller_factory=factory, **kw)

        def _decide_raw(self, rid, now):
            if (rid in sp.PARTICIPANTS and probe.submit_t is not None and now + 1e-9 >= probe.submit_t
                    and rid not in probe.submitted and not self.closed):
                probe.submitted.add(rid)
                probe.acks[rid] = self.call(rid, 'pair_carry', 'cargoX', 'B', 'r2' if rid == 'r1' else 'r1')
            return super()._decide_raw(rid, now)

        # ---------------- eval-only observer (never read by control)
        def beam_pose(self):
            body = self.world.data.body(self.scene.cargo[0].body)
            mat = body.xmat.reshape(3, 3)
            return ([float(v) for v in body.xpos], math.atan2(float(mat[1, 0]), float(mat[0, 0])),
                    math.degrees(math.acos(max(-1., min(1., float(mat[2, 2]))))))

        def jaws(self, fingers):
            return {r: list(fingers[r].get('cargoX', [False, False])) for r in sp.PARTICIPANTS}

        def gt_snapshot(self, rid=None):
            xyz, yaw, tilt = self.beam_pose()
            robots = {r: list(self._truth(r)) for r in self.robots}
            snap = {'t': float(self.world.data.time), 'beam_xyz': xyz, 'beam_yaw': yaw, 'tilt_deg': tilt,
                    'lift_m': xyz[2] - self.rest_z, 'robots': robots, 'jaws': self.jaws(self._contact_kinds_raw()[1])}
            geo = sp.stations([xyz[0], xyz[1], yaw])
            snap['grip_errors_all'] = {r: sp.grip_errors(robots[r], geo['grip_xyz'][r][:2], geo['station'][r][2])
                                       for r in sp.PARTICIPANTS}
            if rid is not None:
                snap['grip_errors'] = snap['grip_errors_all'][rid]
            return snap

        def _contact_kinds_raw(self):
            return OwnCamTeamHost._contact_kinds(self, self.world.data)

        def _contact_kinds(self, data):
            kinds, fingers = super()._contact_kinds(data)
            now = float(data.time)
            if now + 1e-9 >= self.next_sample:
                self.next_sample = now + SAMPLE_S
                xyz, yaw, tilt = self.beam_pose()
                states = {}
                for r in sp.PARTICIPANTS:
                    ep = next((s['endpoints'][r] for s in reversed(self.pairs.sessions) if r in s['endpoints']), None)
                    states[r] = ep.controller.state if ep is not None else None
                lift = xyz[2] - self.rest_z
                row = {'t': now, 'states': states, 'beam_xyz': xyz, 'beam_yaw': yaw, 'tilt_deg': tilt,
                       'lift_m': lift, 'jaws': self.jaws(fingers),
                       'robots': {r: list(self._truth(r)) for r in sp.PARTICIPANTS}}
                for r in sp.PARTICIPANTS:
                    loc = self.robots[r].executor.pose.loc
                    if id(loc) != self.loc_ids.get(r):
                        if r in self.loc_ids:
                            loc_log.append({'t': now, 'robot_id': r, 'event': 'localizer_object_replaced',
                                            'class': type(loc).__name__})
                        self.loc_ids[r] = id(loc)
                trace.append(row)
                self.max_tilt = max(self.max_tilt, tilt)
                if lift >= sp.CRITERIA.get('grasp_lift', {}).get('min_lift_m', .03):
                    self.lifted_once = True
                if self.lifted_once:
                    self.min_lift_after = lift if self.min_lift_after is None else min(self.min_lift_after, lift)
            return kinds, fingers

        def done(self):
            if len(probe.acks) == len(sp.PARTICIPANTS) and not all(a['accepted'] for a in probe.acks.values()):
                return True
            if not self.pairs.sessions:
                return False
            eps = self.pairs.sessions[-1]['endpoints']
            if set(eps) != set(sp.PARTICIPANTS):
                return False
            finished = [r in probe.exits or eps[r].terminal for r in sp.PARTICIPANTS]
            if all(finished) and self.gt_at_stop is None:
                self.gt_at_stop = self.gt_snapshot()          # eval only, at the stage stop instant
                checkpoints.append(save_checkpoint(self, out, 'stage_stop'))
            return all(finished)

    host = ProbeHost.__new__(ProbeHost)
    host.next_sample, host.max_tilt, host.lifted_once, host.min_lift_after = 0., 0., False, None
    host.rest_z = 0.
    host.loc_ids, host.gt_at_stop = {}, None
    result = {'case_id': case['case_id'], 'stage': stage, 'source': case['source'], 'cell': case['cell'],
              'seed': case['seed'], 'labels': sp.LABELS, 'probe_version': sp.PROBE_VERSION,
              'controller': {'pair_policy': case.get('pair_policy', 'v5h'), 'execution_bundle_id_on_main': EXECUTION_BUNDLE_ID,
                             'factory': 'harness.zone_pair_executor.m2_controller (unchanged) + probe entry/exit wrapper'},
              'weld': False, 'contact_profile': 'cargo_noslip_v1', 'model_calls': 0, 'ultrasonic': 'off (not connected)'}
    result['diag_patch'] = case.get('diag_patch')
    result['loadavg_case_start'] = list(os.getloadavg())
    IMAGE_VALID_REAL.clear()
    result['image_valid_real_stats'] = IMAGE_VALID_REAL if case.get('diag_patch') == 'image_valid_off' else None
    install_diag_patch(case.get('diag_patch'))
    result['staging_bypass'] = case.get('staging_bypass')
    result['admission_image_valid_real'] = {}
    install_staging_bypass(case.get('staging_bypass'), result['admission_image_valid_real'])
    result['staged_global_anchor'] = (sp.staged_global_anchor(case) if case.get('pair_policy') == 'a+b' else None)
    if result['staged_global_anchor']:
        stage_global_anchor(result['staged_global_anchor'], loc_log)
    try:
        OwnCamTeamHost.__init__(host, spec, student, root=ROOT, study_layer=lambda *a: None,
                                frames_dir=out / 'frames', scene=scene)
        probe.host = host
        if case.get('route') is not None:   # the staged route must be the controller's own static route
            from harness.zone_pair_executor import make_plan
            got = [[float(v) for v in q] for q in make_plan(scene.config['static_map'], sheet, 'B')['route']]
            result['route_check'] = {'matches_case_route': got == case['route'], 'leg': case.get('leg'), 'route': got}
            if got != case['route']:
                raise RuntimeError('case route differs from make_plan(scene static map)')
        for rid in sp.PARTICIPANTS:
            instrument_pose(host.robots[rid].executor.pose, rid, loc_log, lambda: float(host.world.data.time))
        if any(host.world.data.eq_active):
            raise RuntimeError('weld/equality active at start')
        result['applied'] = {'timestep_s': float(host.world.model.opt.timestep),
                             'noslip_iterations': int(host.world.model.opt.noslip_iterations),
                             'contact_record': host.contact_record,
                             'scene_resolved_sha256': host.scene.record()['resolved_sha256'],
                             'scene_xml_sha256': host.scene.manifest.get('scene_xml_sha256')}
        if case.get('render_profile'):
            from sim import render_profile as rp
            result['applied']['render_profile'] = {**host.scene.manifest['render_profile'],
                                                   'model_audit': rp.verify_model(host.world.model, case['render_profile'])}
        host.rest_z = host.beam_pose()[0][2]
        t0 = float(host.world.data.time)
        # ---- stated priors (no fix). Before ANY own frame reaches the PF.
        result['prior_seeded'] = {}
        for rid in sp.PARTICIPANTS:
            loc = host.robots[rid].executor.pose.loc
            est = sp.seed_gaussian_prior(loc, t0, case['prior'][rid])
            result['prior_seeded'][rid] = {'t': t0, 'estimate': {k: est[k] for k in ('x', 'y', 'yaw', 'std_xy_m', 'std_yaw_rad')},
                                           'last_tag_t': loc.last_tag_t}
        probe.staging_start_t = t0
        # ---- teacher-held beam (carry / setdown only): GT station geometry,
        # commands issued through each robot's own port (own command history).
        if case.get('teacher_held'):
            # Same stationary own-frame window as the other stages, BEFORE the
            # arm leaves the tag-viewing fold posture; then the teacher lift.
            host._physics_until(max(t0, sp.SUBMIT_AFTER_S) + sp.STAGING_S)
            geo = sp.stations(case['beam_xyyaw'])
            from harness.visual_arm import solve_grip_ik, tool_pose

            class TeacherPort:
                def __init__(self, rid):
                    self.rid = rid

                def apply(self, action, now):
                    host._apply(self.rid, action, now)
            arms, teacher = {}, {}
            for rid in sp.PARTICIPANTS:
                g = sp.grip_errors(host._truth(rid), geo['grip_xyz'][rid][:2], 0.)['grip_base_m']
                grasp = solve_grip_ik(g[0], g[1], study.GRASP_Z_M, -90)
                pitch = tool_pose(grasp).pitch_deg
                hover = solve_grip_ik(g[0], g[1], study.HOVER_Z_M, pitch)
                path = [solve_grip_ik(g[0], g[1], float(h), pitch) for h in np.linspace(study.HOVER_Z_M, study.GRASP_Z_M, 8)[1:]]
                commanded = {int(k): int(v) for k, v in host.world.robot(rid).servo_command_pulses.items()}
                arm = ArmSequence(TeacherPort(rid), commanded)
                arm.queue({**hover, 1: study.OPEN}, t0, duration=1.)
                for p in path:
                    arm.queue(p, t0, duration=.12, settle=0.)
                arm.queue({1: study.CLOSED}, t0, duration=.5, settle=.4)
                arm.queue({**hover, 1: study.CLOSED}, t0, duration=1.2, settle=.5)
                arms[rid] = arm
                teacher[rid] = {'grip_base_gt_m': g, 'hover': hover, 'grasp': path[-1]}
            while True:
                now = float(host.world.data.time)   # the port clock must never move backwards
                if all([a.tick(now) for a in arms.values()]):
                    break
                host._physics_until(now + .05)
            result['teacher'] = {'staging': 'GT grip -> IK open/descend/close/lift via own ports (teacher exception)',
                                 'robots': teacher, 'end_t': float(host.world.data.time),
                                 'gt_after_lift': host.gt_snapshot()}
            probe.submit_t = float(host.world.data.time) + .2
        else:
            probe.submit_t = max(float(host.world.data.time), sp.SUBMIT_AFTER_S) + sp.STAGING_S
        sim_end = probe.submit_t + spec_stage['budget_s']
        result['submit_t'] = probe.submit_t
        result['gt_at_entry'] = host.gt_snapshot()
        checkpoints.append(save_checkpoint(host, out, 'staged_before_submit'))
        run = host.run(sim_end, done=host.done)
        result['termination'] = run
    except Exception as exc:  # noqa: BLE001 - HOST_ERROR is a recorded outcome, never a pass
        import traceback
        result['host_error'] = {'type': type(exc).__name__, 'message': str(exc)[:2000],
                                'traceback': traceback.format_exc()[-6000:], 'classification': 'HOST_ERROR',
                                'enospc': isinstance(exc, OSError) and getattr(exc, 'errno', None) == 28}
    finally:
        try:
            if getattr(host, 'world', None) is not None and getattr(host, 'pairs', None) is not None:
                result['acks'] = probe.acks
                result['entry'] = probe.entry
                result['exits'] = probe.exits
                result['api_calls'] = host.api_calls
                result['event_log'] = host.event_log
                sessions = host.pairs.sessions
                result['controller_events'] = {r: ep.events for s in sessions for r, ep in s['endpoints'].items()}
                result['final_states'] = {r: ep.controller.state for s in sessions for r, ep in s['endpoints'].items()}
                result['failures'] = {r: ep.controller.failure for s in sessions for r, ep in s['endpoints'].items()}
                write_json(out / 'pair_records.json', host.pairs.records())
                write_json(out / 'commands.json', {r: s.commands for r, s in host.robots.items()})
                write_json(out / 'robots.json', {r: {'frames': s.frames, 'exception': s.exception}
                                                 for r, s in host.robots.items()})
                write_json(out / 'eval_only/host.json', host.eval_only)
                result['gt_at_end'] = host.gt_snapshot()
                result['gt_at_stop'] = host.gt_at_stop
                result['localizer_log'] = loc_log
                result['localizer_stats'] = {r: dict(host.robots[r].executor.pose.loc.stats) for r in sp.PARTICIPANTS}
                result['localizer_class'] = {r: type(host.robots[r].executor.pose.loc).__name__ for r in sp.PARTICIPANTS}
                result['checkpoints'] = checkpoints
                result['max_tilt_deg'] = host.max_tilt
                result['min_lift_after_first_lift_m'] = host.min_lift_after
                with (out / 'eval_only/trace.jsonl').open('w') as f:
                    for row in trace:
                        f.write(json.dumps(row, default=_jsonable) + '\n')
        finally:
            if getattr(host, 'world', None) is not None:
                host.close()
    result['wall_s'] = time.monotonic() - started
    result['loadavg_case_end'] = list(os.getloadavg())
    return finish_result(case, result, out)


def leg_end_metrics(p0, p1, beam_end_xy, yaw0, yaw1):
    """Eval-only leg-end metrics: distance to the planned route point, cross-track vs the leg line, beam yaw drift."""
    length = math.dist(p0, p1)
    ux, uy = (p1[0] - p0[0]) / length, (p1[1] - p0[1]) / length
    dx, dy = beam_end_xy[0] - p0[0], beam_end_xy[1] - p0[1]
    return {'end_error_m': math.dist(beam_end_xy, p1), 'along_error_m': dx * ux + dy * uy - length,
            'cross_track_m': abs(-dx * uy + dy * ux), 'yaw_drift_deg': math.degrees(sp.wrap(yaw1 - yaw0))}


def stage_diagnostics(case, result, out, record):
    """Own-report / eval-only summaries for cause classification and the README tables.

    ANALYSIS ONLY: reads files the run already wrote. own_* fields are the robots' own PoseReports; est_vs_gt is
    the eval-only own-estimate-vs-truth error at the reference time (failure, else stage exit, else stop).
    """
    frames = (_load(out / 'robots.json') or {})
    tpath = out / 'eval_only/trace.jsonl'
    trace = [json.loads(line) for line in tpath.read_text().splitlines() if line] if tpath.exists() else []
    host = _load(out / 'eval_only/host.json') or {}
    cmds = _load(out / 'commands.json') or {}
    submit_t = result.get('submit_t')
    stop_t = (result.get('termination') or {}).get('sim_s')
    ff = record.get('first_failure') or {}
    exits = result.get('exits', {})

    def ref_t(rid):
        if ff.get('sim_s') is not None:
            return ff['sim_s']
        if rid in exits:
            return exits[rid]['sim_s']
        return stop_t

    def brief(rep):
        if not rep:
            return None
        q = rep.get('observation_quality') or {}
        return {'t': rep.get('t_est'), 'xyyaw': rep.get('xyyaw') or [rep.get('x_m'), rep.get('y_m'), rep.get('yaw_rad')],
                'std_xy_m': rep.get('std_xy_m'), 'std_yaw_rad': rep.get('std_yaw_rad'), 'fix_age_s': rep.get('fix_age_s'),
                'fix_source': rep.get('fix_source'), 'obs_reason': q.get('reason'), 'load_state': rep.get('load_state')}

    d = {'own_at_entry': {}, 'own_at_ref': {}, 'own_at_failure': {}, 'ref_t': {}, 'est_vs_gt_at_ref': {}, 'sigma_yaw_max': {}}
    for rid in sp.PARTICIPANTS:
        fr = [f for f in (frames.get(rid) or {}).get('frames', []) if f.get('report')]
        entry_rep = (result.get('entry', {}).get(rid) or {}).get('own_report')
        d['own_at_entry'][rid] = brief(entry_rep)
        t = ref_t(rid)
        d['ref_t'][rid] = t
        upto = [f for f in fr if t is None or f['t'] <= t + 1e-6]
        last = upto[-1] if upto else None
        d['own_at_ref'][rid] = brief(last['report']) if last else None
        d['own_at_failure'][rid] = d['own_at_ref'][rid]
        t0 = (result.get('entry', {}).get(rid) or {}).get('sim_s')
        span = [f for f in upto if t0 is None or f['t'] >= t0 - 1e-6]
        ys = [f['report'].get('std_yaw_rad') for f in span if f['report'].get('std_yaw_rad') is not None]
        d['sigma_yaw_max'][rid] = None if not ys else round(max(ys), 5)
        rows = [r for r in trace if t is not None and r['t'] <= t + 1e-6]
        if last and rows:
            gt = rows[-1]['robots'][rid]
            est = last['report']['xyyaw']
            d['est_vs_gt_at_ref'][rid] = {'xy_m': round(math.dist(est[:2], gt[:2]), 4),
                                          'yaw_rad': round(sp.wrap(est[2] - gt[2]), 4), 'gt_t': rows[-1]['t'], 'est_t': last['t']}
    kinds = {}
    for rid in sp.PARTICIPANTS:
        after = [c for c in cmds.get(rid, []) if submit_t is not None and c.get('t', -1) >= submit_t - 1e-9]
        kinds[rid] = {}
        for c in after:
            kinds[rid][c['kind']] = kinds[rid].get(c['kind'], 0) + 1
    d['commands_after_submit'] = kinds
    d['command_total'] = {rid: sum(v.values()) for rid, v in kinds.items()}
    d['base_motion_commands'] = {rid: sum(n for k, n in v.items() if k in ('mecanum', 'drive')) for rid, v in kinds.items()}
    contacts = {}
    for c in host.get('contacts', []):
        if c['robot_id'] in sp.PARTICIPANTS and submit_t is not None and c['t'] >= submit_t - 1e-9 \
                and (stop_t is None or c['t'] <= stop_t + 1e-9):
            contacts[c['kind']] = contacts.get(c['kind'], 0) + 1
    d['contacts'] = contacts
    return d


def finish_result(case, result, out):
    stage = case['stage']
    exits = result.get('exits', {})

    def in_stage(e):
        # Episode-end cancellation after the probe stopped, and anything a robot
        # does after its own stage exit, is outside the stage under test.
        reason = str((e.get('detail') or {}).get('reason', ''))
        rid = e.get('robot_id')
        return (not reason.startswith('EPISODE_END')
                and (rid not in exits or e['sim_s'] < exits[rid]['sim_s'] - 1e-9))
    fails = sorted((e for e in result.get('event_log', []) if e.get('event') == 'job_failed'
                    and e.get('robot_id') in sp.PARTICIPANTS and in_stage(e)),
                   key=lambda e: (e['sim_s'], str((e.get('detail') or {}).get('reason', '')).startswith('PARTNER')))
    # Same-instant tie: the partner's PARTNER_ABORT is a consequence, not the root cause (grid1 had 2 such rows).
    first = fails[0] if fails else None
    if result.get('host_error'):
        first = {'robot_id': None, 'sim_s': None, 'reason': 'HOST_ERROR'}
    elif any(not a.get('accepted') for a in result.get('acks', {}).values()):
        bad = next(a for a in result['acks'].values() if not a.get('accepted'))
        result['entry_error'] = 'ADMISSION_' + str(bad.get('rejected_reason'))
    record = {'exits': result.get('exits', {}), 'entry_error': result.get('entry_error'),
              'first_failure': None if first is None else {'robot_id': first.get('robot_id'), 'sim_s': first.get('sim_s'),
                                                            'reason': (first.get('detail') or {}).get('reason', first.get('reason'))},
              'max_tilt_deg': result.get('max_tilt_deg'),
              'min_lift_after_first_lift_m': result.get('min_lift_after_first_lift_m')}
    if record['first_failure'] and record['first_failure']['reason'] in ('STAGE_ENTRY_GRIP_NOT_OBSERVED',):
        record['entry_error'] = record['entry_error'] or 'GRIP_NOT_OBSERVED_AT_STANDOFF'
    exits = result.get('exits', {})
    if stage in ('grasp_lift', 'carry') and all(r in exits for r in sp.PARTICIPANTS):
        last = max(sp.PARTICIPANTS, key=lambda r: exits[r]['sim_s'])
        record['gt_at_exit'] = exits[last].get('gt')
    if stage == 'carry' and record.get('gt_at_exit') and result.get('gt_at_entry'):
        a, b = result['gt_at_entry']['beam_xyz'], record['gt_at_exit']['beam_xyz']
        record['beam_travel_m'] = math.dist(a[:2], b[:2])
        route, k = case['route'], int(case.get('leg') or 0)     # controller static route (make_plan), leg k
        p0, p1 = route[k], route[k + 1]
        record['planned_leg_m'] = math.dist(p0, p1)
        record.update(leg_error_frame='world; beam end vs route[k+1] (eval only)', **leg_end_metrics(
            p0, p1, b[:2], result['gt_at_entry']['beam_yaw'], record['gt_at_exit']['beam_yaw']))
    if stage == 'setdown' and result.get('gt_at_end'):
        record['gt_at_exit'] = result['gt_at_end']
        if result.get('gt_at_entry'):
            record['beam_shift_m'] = math.dist(result['gt_at_entry']['beam_xyz'][:2], result['gt_at_end']['beam_xyz'][:2])
        record['exits'] = {r: {} for r in sp.PARTICIPANTS if result.get('final_states', {}).get(r) == 'done'}
    ev = sp.evaluate(stage, record)
    diag = stage_diagnostics(case, result, out, record)
    diag['host_error_message'] = (result.get('host_error') or {}).get('message')
    cause = sp.classify_cause(stage, ev, record, diag)
    entry_t = min((v['sim_s'] for v in result.get('entry', {}).values()), default=None)
    end_t = (result.get('termination') or {}).get('sim_s')
    row = {'case_id': case['case_id'], 'stage': stage, 'source': case['source'], 'cell': case['cell'],
           'seed': case['seed'], 'labels': sp.LABELS, 'passed': ev['passed'], 'category': ev['category'],
           'checks': ev['checks'], 'metrics': ev['metrics'], 'first_failure': record['first_failure'],
           'exit_sim_s': {r: v['sim_s'] for r, v in exits.items()}, 'entry_sim_s': entry_t,
           'stage_sim_s': None if entry_t is None or end_t is None else round(end_t - entry_t, 3),
           'final_states': result.get('final_states'), 'wall_s': round(result['wall_s'], 2),
           'look_commands': {r: sum(c['kind'] == 'look' for c in cmds)
                             for r, cmds in (_load(out / 'commands.json') or {}).items() if r in sp.PARTICIPANTS},
           'host_error': result.get('host_error', {}).get('type'),
           'pair_policy': case.get('pair_policy', 'v5h'),
           'diag_patch': case.get('diag_patch'),
           'leg': case.get('leg'), 'cause': cause['code'], 'cause_sub': cause['sub'],
           'staging_infeasible': cause['code'] == 'STAGING_IK_ENVELOPE',
           'image_valid_real_stats': result.get('image_valid_real_stats'),
           'contacts_in_stage': cause['contacts_in_stage'],
           'own_at_entry': diag['own_at_entry'], 'own_at_ref': diag['own_at_ref'], 'ref_t': diag['ref_t'],
           'est_vs_gt_at_ref': diag['est_vs_gt_at_ref'], 'sigma_yaw_max': diag['sigma_yaw_max'],
           'commands_after_submit': diag['commands_after_submit'], 'command_total': diag['command_total'],
           'base_motion_commands': diag['base_motion_commands'], 'submit_t': result.get('submit_t'),
           'loadavg_case': [result.get('loadavg_case_start'), result.get('loadavg_case_end')],
           'stop_sim_s': (result.get('gt_at_stop') or {}).get('t'),
           'remaining_at_stop': {r: {k: round(v, 5) for k, v in e.items() if k != 'grip_base_m'}
                                 for r, e in ((result.get('gt_at_stop') or {}).get('grip_errors_all') or {}).items()},
           'relook_calls': {r: [x['event'] for x in result.get('localizer_log', []) if x['robot_id'] == r
                                and x['event'] in ('begin_relocalization', 'begin_observation')] for r in sp.PARTICIPANTS},
           'localizer_replaced': {r: sum(1 for x in result.get('localizer_log', []) if x['robot_id'] == r
                                         and x['event'] == 'localizer_object_replaced') for r in sp.PARTICIPANTS},
           'localizer_resets_stat': {r: (result.get('localizer_stats') or {}).get(r, {}).get('resets') for r in sp.PARTICIPANTS},
           'checkpoints_roundtrip': [c['roundtrip_bitwise'] for c in result.get('checkpoints', [])]}
    if case.get('render_profile'):
        row['render_profile'] = case['render_profile']
    result['evaluation'] = ev
    result['row'] = row
    write_json(out / 'result.json', result)
    return row


def _load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


# ================================================================== coordinator
def leg_arg(text):
    return text if text == 'end' else int(text)


def with_render_profile(cases, name):
    """Mark every case with the opt-in render profile. ``None`` returns the cases untouched (no new key)."""
    if name is None:
        return cases
    from sim import render_profile as rp
    rp.resolve(name)
    return [{**c, 'render_profile': name} for c in cases]


def build_cases(args):
    cases = []
    for stage in args.stage:
        spec = sp.STAGES[stage]
        if not spec['implemented']:
            raise ValueError(f'stage {stage} is not implemented here ({spec["owner"]})')
        for policy in args.policies:
            if 'teacher' in args.sources:
                for leg in (args.legs or [None]):
                    cases += sp.teacher_cases(stage, seeds=tuple(args.seeds), nominal_seeds=tuple(args.nominal_seeds),
                                              subset=set(args.cells) if args.cells else None, policy=policy,
                                              prior_std=args.prior_std, leg=leg)
            if 'boundary' in args.sources and stage == 'grasp_lift':
                cases += sp.boundary_cases(stage, policy=policy, seed=args.seeds[0],
                                           subset=set(args.cells) if args.cells else None, prior_std=args.prior_std)
            if 'e2e' in args.sources:
                for run in E2E_RUNS:
                    got = sp.e2e_checkpoint(args.e2e_root / run, stage, seeds=tuple(args.e2e_seeds) if args.e2e_seeds else None,
                                            policy=policy)
                    if isinstance(got, dict):
                        args.unavailable.append({**got, 'pair_policy': policy})
                    else:
                        cases += got
    cases = sp.apply_diag_patch(cases, args.diag_patch)
    cases = with_render_profile(cases, args.render_profile)
    if args.limit:
        cases = cases[:args.limit]
    return cases


IMAGE_VALID_REAL = {}   # image_valid_off: robot id -> [frames the real valid_frame accepted, frames it rejected]


def install_diag_patch(name):
    """Probe-process-only diagnostic patch (sp.DIAG_PATCHES). Never used by a non-diag case."""
    if name in sp.DIAG_COMPONENTS:
        for part in sp.DIAG_COMPONENTS[name]:
            install_diag_patch(part)
        return
    if name == 'loaded_yaw_gate_wide':
        import dataclasses
        import importlib
        import harness.zone_own_guards as guards
        wide = dataclasses.replace(guards.GATE_LOADED, high_yaw_rad=math.radians(sp.LOADED_YAW_GATE_DIAG_DEG[0]),
                                   low_yaw_rad=math.radians(sp.LOADED_YAW_GATE_DIAG_DEG[1]))
        # GATE_LOADED is imported by name; rebind it in every module that holds it (zone_pair_obstruction re-imports lazily).
        for mod in ('harness.zone_own_guards', 'harness.zone_own_driver', 'harness.zone_own_sweep', 'harness.zone_pair_guards'):
            module = importlib.import_module(mod)
            if not hasattr(module, 'GATE_LOADED'):
                raise RuntimeError(f'{mod} has no GATE_LOADED to patch')
            module.GATE_LOADED = wide
    elif name == 'pf_rest_no_abs_noise':
        import numpy as np
        from harness.owncam_localizer import OwnCamLocalizer
        registered = OwnCamLocalizer._motion_params

        def motion_params(self):
            mp = registered(self)
            still = float(np.max(np.abs(self.vel))) < 1e-3 and not (self.t < self.cmd_expires - 1e-9)
            return {**mp, 'noise_abs': [0., 0., 0.]} if still else mp
        OwnCamLocalizer._motion_params = motion_params
    elif name == 'carry_lateral_scale_measured':
        from scripts import study_owncam_pair_beam as study
        study.CARRY_ODOM_SCALE['lateral'] = sp.CARRY_LATERAL_SCALE_DIAG   # in place: run_m2_pair / the executor share this dict
    elif name == 'sigma_held_tiny':
        from harness.owncam_localizer import OwnCamLocalizer
        registered = OwnCamLocalizer.estimate
        cap_xy, cap_yaw = sp.SIGMA_TINY_DIAG['std_xy_m'], sp.SIGMA_TINY_DIAG['std_yaw_rad']

        def estimate(self):
            return sp.clamp_estimate_sigma(registered(self), cap_xy, cap_yaw)
        OwnCamLocalizer.estimate = estimate
    elif name == 'sigma_held_at_prior':
        from harness.owncam_localizer import OwnCamLocalizer
        registered = OwnCamLocalizer.estimate
        cap_xy, cap_yaw = sp.E2E_MATCHED_PRIOR['std_xy_m'], sp.E2E_MATCHED_PRIOR['std_yaw_rad']

        def estimate(self):
            return sp.clamp_estimate_sigma(registered(self), cap_xy, cap_yaw)
        OwnCamLocalizer.estimate = estimate   # RecoveryLocalizer / FixReportingLocalizer.estimate call super().estimate()
    elif name == 'image_valid_off':
        import importlib
        import harness.zone_pair_vision as vision
        real = vision.valid_frame

        def forced(obs, rid, now):
            IMAGE_VALID_REAL.setdefault(rid, [0, 0])[0 if real(obs, rid, now) else 1] += 1
            return True
        forced.__wrapped__ = real
        vision.valid_frame = forced      # zone_pair_admission / _executor / _guards import it at call time
        grasp = importlib.import_module('harness.zone_pair_grasp')   # imports the name at module load
        if not hasattr(grasp, 'valid_frame'):
            raise RuntimeError('harness.zone_pair_grasp has no valid_frame to patch')
        grasp.valid_frame = forced
    elif name == 'fix_age_round':
        from harness.owncam_recovery_v6 import RecoveryLocalizer
        from harness.owncam_localizer import OwnCamLocalizer

        def estimate(self):
            est = OwnCamLocalizer.estimate(self)
            t = getattr(self, 'last_informative_t', None)
            age = None if t is None else round(self.t - t, 3)
            est.update(last_fix_t=t, fix_age_s=age, fix_source='tags_temporary', since_tag_s=age)
            return est
        RecoveryLocalizer.estimate = estimate
    elif name is not None:
        raise ValueError(f'unknown diagnostic patch {name!r}')


def install_staging_bypass(names, verdicts):
    """Staging aid, not a controller change: force ONLY the submit-time admission ``image_valid`` predicate true.

    The real ``valid_frame`` verdict at every admission is written to ``verdicts`` (rid -> [bool...]). The
    endpoint's own per-step ``valid_frame`` check (PairEndpoint.step/arm_step -> INVALID_OWN_IMAGE) is left intact.
    """
    if not names:
        return
    if list(names) != ['admission_image_valid']:
        raise ValueError(f'unknown staging bypass {names!r}')
    import harness.zone_pair_admission as admission
    import harness.zone_pair_vision as vision
    registered_snapshot, current = admission.readiness_snapshot, vision.valid_frame
    real = getattr(current, '__wrapped__', current)   # image_valid_off wraps the real predicate; record the real verdict

    def snapshot(ex, now, *a, **k):
        verdicts.setdefault(ex.robot_id, []).append(bool(real(ex.last_obs, ex.robot_id, now)))
        vision.valid_frame = lambda obs, rid, t: True
        try:
            return registered_snapshot(ex, now, *a, **k)
        finally:
            vision.valid_frame = current
    admission.readiness_snapshot = snapshot


def git(*a):
    return subprocess.check_output(['git', *a], cwd=ROOT, text=True).strip()


def primary_root():
    return (ROOT / git('rev-parse', '--git-common-dir')).resolve().parent


def run_worker(case, case_dir, timeout_s):
    env = {**os.environ, 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2'}
    case_file = case_dir.parent / (case_dir.name + '.case.json')
    write_json(case_file, case)
    log = case_dir.parent / (case_dir.name + '.log')
    t = time.monotonic()
    with log.open('w') as f:
        try:
            proc = subprocess.run([sys.executable, '-m', 'scripts.run_pair_stage_probes', '--worker-case', str(case_file),
                                   '--worker-out', str(case_dir)], cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT,
                                  timeout=timeout_s)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = 'WALL_TIMEOUT'
    row = _load(case_dir / 'result.json')
    if row is None or 'row' not in row:
        return {'case_id': case['case_id'], 'stage': case['stage'], 'source': case['source'], 'cell': case['cell'],
                'seed': case['seed'], 'labels': sp.LABELS, 'passed': False,
                'category': f'HOST_ERROR:worker_exit_{code}', 'wall_s': round(time.monotonic() - t, 2),
                'stage_sim_s': None}
    return row['row']


def rp_names():
    from sim import render_profile as rp
    return rp.PROFILES


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--stage', nargs='+', choices=[s for s, v in sp.STAGES.items() if v['implemented']])
    p.add_argument('--output', type=Path)
    p.add_argument('--sources', nargs='+', default=['teacher', 'e2e'], choices=['teacher', 'e2e', 'boundary'])
    p.add_argument('--diag-patch', choices=sorted(sp.DIAG_PATCHES),
                   help='probe-only DIAGNOSTIC controller patch (case ids get :diag-<name>; not the registered v6)')
    p.add_argument('--prior-std', choices=['grid', 'e2e'], default='grid',
                   help="teacher/boundary prior std: 'grid' (0.06 m, 0.05 rad; grid1) or 'e2e' (sp.E2E_MATCHED_PRIOR)")
    p.add_argument('--render-profile', choices=sorted(rp_names()),
                   help='opt-in visual profile from sim/render_profile.py (default: none = current behaviour). Changes '
                        'every camera image, so runs are a separate condition; not a registered bundle. The profile '
                        'name and hash go to manifest.json and every result row.')
    p.add_argument('--policies', nargs='+', default=['v5h'], choices=list(sp.POLICIES),
                   help='harness.zone_pair_v6_policy policies; there is no A-only policy on main')
    p.add_argument('--seeds', nargs='+', type=int, default=[911])
    p.add_argument('--nominal-seeds', nargs='+', type=int, default=[911, 912, 913])
    p.add_argument('--e2e-seeds', nargs='+', type=int)
    p.add_argument('--e2e-root', type=Path, default=E2E_DEFAULT)
    p.add_argument('--cells', nargs='+', help='subset of grid cell names (e.g. nominal along+/same)')
    p.add_argument('--legs', nargs='+', type=leg_arg,
                   help="carry: route leg indexes (0 = pickup to first waypoint); setdown: 'end' = destination zone "
                        "(default: legacy behaviour)")
    p.add_argument('--limit', type=int)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--case-timeout-s', type=float, default=1500.)
    p.add_argument('--execute', action='store_true', help='physical probes (MuJoCo); otherwise plan only')
    p.add_argument('--lock-owner', choices=('claude', 'codex', 'kiro'))
    p.add_argument('--worker-case', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--worker-out', type=Path, help=argparse.SUPPRESS)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.worker_case:
        case = json.loads(args.worker_case.read_text())
        row = run_case(case, args.worker_out)
        print(json.dumps(row, ensure_ascii=False, default=_jsonable))
        return 0
    if not args.stage or not args.output:
        p.error('--stage and --output are required')
    if args.output.exists():
        p.error('output must be new; raw results are never overwritten')
    if not 1 <= args.workers <= 8:
        p.error('workers must be 1..8')
    args.unavailable = []
    cases = build_cases(args)
    if len({c['case_id'] for c in cases}) != len(cases):
        p.error('duplicate case ids')
    from sim.workflow_manager import environment_identity, git_identity, source_fingerprint
    manifest = {'schema': sp.SCHEMA, 'workflow': WORKFLOW, 'labels': sp.LABELS, 'probe_version': sp.PROBE_VERSION,
                'research_result': False, 'e2e_success_claim': False, 'model_calls': 0,
                'stages': args.stage, 'criteria': {s: sp.CRITERIA[s] for s in args.stage},
                'stage_registry': {s: sp.STAGES[s] for s in sp.STAGES},
                'source': {**git_identity(ROOT), 'execution_tree': source_fingerprint(ROOT)},
                'environment': {**environment_identity(), 'loadavg_at_start': list(os.getloadavg())},
                'workers': args.workers, 'omp_num_threads_per_worker': 2,
                'cases': len(cases), 'cases_sha256': sp.digest(cases), 'unavailable_e2e': args.unavailable,
                'state': 'planned'}
    if args.render_profile:
        from sim import render_profile as rp
        manifest['render_profile'] = rp.profile_record(args.render_profile)
    if not args.execute:
        print(json.dumps({'state': 'planned', 'cases': len(cases), 'case_ids': [c['case_id'] for c in cases],
                          'unavailable_e2e': args.unavailable}, ensure_ascii=False, indent=1))
        return 0
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to(primary_root() / 'outputs'):
        p.error('physical raw output must be absolute under the primary checkout outputs/')
    if args.lock_owner is None:
        p.error('--execute requires --lock-owner')
    from scripts import agent_lock
    held = agent_lock.status(primary_root() / 'outputs/agent-locks')
    if not held or not held['pid_alive'] or held['owner'] != args.lock_owner:
        p.error('a live agent_lock held by --lock-owner is required for the probe grid')
    if git('status', '--porcelain', '--untracked-files=no'):
        p.error('tracked source must be clean (commit the probe source first)')
    manifest['lock'] = held
    args.output.mkdir(parents=True)
    (args.output / 'cases').mkdir()
    write_json(args.output / 'plan.json', {'labels': sp.LABELS, 'cases': cases})
    manifest['state'] = 'running'
    write_json(args.output / 'manifest.json', manifest)
    start = time.monotonic()
    rows = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool, (args.output / 'cases.jsonl').open('x') as sink:
        futures = {pool.submit(run_worker, c, args.output / 'cases' / safe_name(c['case_id']), args.case_timeout_s): c
                   for c in cases}
        for fut in cf.as_completed(futures):
            row = fut.result()
            rows.append(row)
            sink.write(json.dumps(row, ensure_ascii=False, default=_jsonable) + '\n')
            sink.flush()
            print(f"[{len(rows)}/{len(cases)}] {row['case_id']}: {row['category']} "
                  f"(stage {row.get('stage_sim_s')} SIM s, {row.get('wall_s')} wall s)", flush=True)
    summary = sp.summarize(rows)
    summary.update(wall_s_total=round(time.monotonic() - start, 1), unavailable_e2e=args.unavailable)
    write_json(args.output / 'summary.json', summary)
    manifest.update(state='completed', wall_s=summary['wall_s_total'],
                    source_after_sha256=source_fingerprint(ROOT)['sha256'])
    manifest['source_changed'] = manifest['source_after_sha256'] != manifest['source']['execution_tree']['sha256']
    manifest['environment']['loadavg_at_end'] = list(os.getloadavg())
    write_json(args.output / 'manifest.json', manifest)
    files = {str(q.relative_to(args.output)): {'bytes': q.stat().st_size, 'sha256': sp.sha_file(q)}
             for q in sorted(args.output.rglob('*')) if q.is_file() and q.name != 'artifacts.sha256.json'}
    write_json(args.output / 'artifacts.sha256.json', files)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
