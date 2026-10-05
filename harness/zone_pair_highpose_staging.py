"""v98 DEV stage probes from staged states (test setup, never a case result).

Project stage-probe rule (2026-09-28): test each skill stage from a staged
state in short runs, so the stages after approach can be checked without the
approach/localization stages in front of them.

Boundary (same convention as harness/pair_stage_probe.py):
* Staging is TEST SETUP done by the sim harness BEFORE the controller exists:
  robots spawn at the catalogue grasp stations of the case's beam pose
  (sim.zone_model_conventions.station_offset, the v3 convention the v92 teacher
  stations use) and a fixed teacher arm pre-roll (the v92 loaded-schedule
  poses) runs. All of it is recorded (eval_only/staging.json, run record).
* The controller then receives only own RGB, the static map and its own
  issued commands. The staged pre-roll pulses become its initial own command
  history (initial_servo_command), exactly what it would have issued itself.
* Its localizer starts from the CASE START prior definition applied to the
  staged spawn pose (region mean, std 0.15 / max(0.15, row span) / 0.174533;
  is_fix false: it sets no fix time). The spawn pose is the one GT-derived
  staging input, as in every earlier stage probe.
* ``raise_high_align`` (coordinator 2026-10-04): spawn at the plan pre-station
  (approach end), keep the controller's normal opening look_around, and enter
  ``wait_approach`` -- what the real approach sets on arrival -- so the
  controller's own approach barrier leads it into align -> grasp -> raise.
* HIGH entries (``high_hold_staged``, ``carry_leg_staged``) skip the opening
  look_around (it would move the arm holding the beam; recorded). Their staged
  pre-roll is handed to the controller as its own ordered command history
  (pre-close posture, then the close and raise rows), so the localizer's
  loaded state comes from the same own-command rule as after a real close.
* The floor entries ``raise_high_staged``/``raise_high_closed`` are dropped
  (``DROPPED``): with the case-start prior, no look_around and 0 measurements
  at the floor pose they can never pass pair admission (std <= 0.05).
* TEST-SETUP GROUND TRUTH (``TEST_SETUP_GT``, reviewer 2026-10-04): the staged
  prior mean is the true staged spawn pose (station or plan pre-station), and the
  HIGH entries' ``gripped``/``lifted`` claims and HIGH anchor come from the
  teacher pre-roll, not from the controller's own perception. Both are labelled
  in the code, the controller log (``stage_probe_entry``) and
  ``stage_probe_staging.json``. They exist only in these staged DEV probes and
  must never be used by an E2E run, a cohort or as a case result.
* The align entry keeps the normal opening look_around: the pair admission
  then decides from the controller's real own-camera estimate (no gate is
  loosened), and the entry runs only after it, at the first controller tick.
* No controller, endpoint or admission gate is relaxed.
* The staged entry sets the controller fields its own skipped states would
  have set, logged as ``stage_probe_entry``. Controller logic and gates are
  unchanged.
"""
from __future__ import annotations

import functools
from types import MethodType

from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_grip as grip
from harness import zone_pair_highpose_runtime as rt
from harness.zone_final_pair_loaded_schedule import POSES
from harness.zone_final_pair_vision import grasp_postures

OPEN, CLOSED = 2000, 1500
ROLES = {'r1': 'end_neg', 'r2': 'end_pos'}
# Staged start prior = the real case-start prior definition
# (harness/zone_final_pair_runtime.py Runtime.__init__): mean = the public
# start region, per-axis std = (0.15, max(0.15, row span), 0.174533). For a
# staged start the region is the one staged station, so the row span is 0.
# Coordinator ruling 2026-10-03: no gate-driven value.
CASE_START_STD_X_M, CASE_START_STD_Y_MIN_M, CASE_START_STD_YAW_RAD = .15, .15, .174533
# Label on every staged value derived from the simulator's true state (spawn pose, teacher-staged grip/lift).
TEST_SETUP_GT = {'test_setup_ground_truth': True,
                 'scope': 'staged DEV stage probes only; never E2E, cohort or a case result'}

_FLOOR = {**grasp_postures()[1][-1]}
if any(_FLOOR[k] != POSES['floor_grasp'][k] for k in (3, 4, 5)):
    raise ValueError('v3 floor grasp posture differs from the v92 teacher floor_grasp pose')

# Teacher pre-roll (t relative to reset end, pulses per servo; 6 = pan look).
PREROLLS = {
    'none': {'end_s': 0., 'visits': []},
    'floor_open': {'end_s': 3., 'visits': [(0., 'stage_floor_grasp_open', {**_FLOOR, 1: OPEN})]},
    'floor_closed': {'end_s': 3.5, 'visits': [(0., 'stage_floor_grasp_open', {**_FLOOR, 1: OPEN}),
                                              (2., 'stage_close', {1: CLOSED})]},
    # v92 loaded schedule (HIGH = edge_view_150), the bilateral teacher lift
    # already exercised by the v92 loaded collection; 8 s settle as there.
    'high_held': {'end_s': 32., 'visits': [(0., 'stage_floor_grasp_open', {**_FLOOR, 1: OPEN}),
                                           (2., 'stage_close', {1: CLOSED}),
                                           (4., 'stage_controller_hover', POSES['controller_hover']),
                                           (16., 'stage_transition_110', POSES['transition_110']),
                                           (20., 'stage_transition_130', POSES['transition_130']),
                                           (24., 'stage_high', POSES['edge_view_150'])]},
}
if POSES['edge_view_150'] != pose.HIGH:
    raise ValueError('teacher HIGH differs from the v98 HIGH carry pose')

# entry: controller state at stage entry; terminal: event that ends the stage.
PROBE_SPECS = {
    'raise_high_align': {'preroll': 'none', 'spawn': 'prestation', 'opening_look_around': True,
        'entry': 'wait_approach', 'cap_s': 150.,
        'terminal_event': 'high_carry_pose', 'barrier': None,
        'covers': 'staged approach end (plan pre-station) + normal opening look_around -> own approach barrier -> '
                  'own-RGB align -> open descent -> close barrier -> grasp -> low lift -> raise to HIGH'},
    # Coordinator 2026-10-04: continuation probe. Same entry as raise_high_align, then the controller's own
    # HIGH hold and carry leg until delivery (both robots reach state 'done') or a failure. No harness-injected
    # loaded state: hold and carry start from the state the controller itself reached.
    'align_to_carry': {'preroll': 'none', 'spawn': 'prestation', 'opening_look_around': True,
        'entry': 'wait_approach', 'cap_s': 900.,       # = CASE_CAP_S (v98-cap-3, user 2026-10-04)
        'terminal_event': 'state', 'terminal_state': 'done', 'barrier': None,
        'covers': 'raise_high_align entry -> align -> blind final approach -> close -> lift -> raise to HIGH -> '
                  'HIGH hold -> carry barrier -> carry leg -> lower -> release -> done (delivery or failure)'},
    'high_hold_staged': {'preroll': 'high_held', 'spawn': 'station', 'opening_look_around': False,
        'entry': 'wait_carry', 'cap_s': 60.,
        'terminal_event': 'barrier_go', 'barrier': 'carry',
        'covers': 'staged teacher-held beam at HIGH -> carry barrier GO from own command history + partner status'},
    'carry_leg_staged': {'preroll': 'high_held', 'spawn': 'station', 'opening_look_around': False,
        'entry': 'wait_carry', 'cap_s': 150.,
        'terminal_event': 'checkpoint_high_reobserved', 'barrier': None,
        'covers': 'staged teacher-held beam at HIGH -> carry leg to the first checkpoint -> HIGH stop + re-observe (needs localization)'},
}

# Parked 2026-10-04 (coordinator): code kept, not run and not counted. A HIGH entry would need a look_around in a
# loaded pose, i.e. more test-setup ground truth; align_to_carry covers hold/carry from a reached state instead.
PARKED = {
    'high_hold_staged': 'HIGH staged entry: no measurement at HIGH (look_around skipped) -> pair admission gate_ok false '
                        '(b37c9270 x1200, 0865a788 x1200); a loaded-pose look_around would add test-setup ground truth',
    'carry_leg_staged': 'same as high_hold_staged (b37c9270 x3000, 0865a788 x3000)',
}

# Dropped 2026-10-04 (coordinator): structurally unable to pass pair admission.
DROPPED = {
    'raise_high_staged': 'floor entry: case-start prior std 0.15 m, opening look_around skipped and 0 measured updates '
                         'at the floor pose -> pair admission gate_ok false for the whole cap (7623c4dc, 1800 tries)',
    'raise_high_closed': 'floor entry: same admission block as raise_high_staged (7623c4dc, 1800 tries)',
}


def stations(static, beam_xyyaw):
    from sim.zone_model_conventions import station_offset
    return {rid: [float(beam_xyyaw[0])+off[0], float(beam_xyyaw[1])+off[1], float(off[2])]
            for rid, role in ROLES.items() for off in [station_offset(static, 'long_beam', role)]}


def spawn_poses(static, beam_xyyaw, stage):
    """Staged spawn per robot: the grasp station, or the plan pre-station (approach end) for an align entry."""
    st = stations(static, beam_xyyaw)
    if PROBE_SPECS[stage]['spawn'] == 'station':
        return st
    from scripts import run_m2_pair as m2
    return {rid: [float(v) for v in m2.pa.prestation(pose_, m2.study.PRESTATION_BACK_M)] for rid, pose_ in st.items()}


def own_history(name, final):
    """Ordered own command rows that hand a staged pre-roll to the controller.

    No close in the pre-roll: one initial_servo_command with the final pulses (as before). With a close: the
    pre-close posture as initial_servo_command, then the close and later rows in order, so LoadState sets
    'loaded' by its own rule (gripper commanded closed at grasp height) exactly as after a real close. The last
    row leaves the same pulses as ``final``.
    """
    visits = PREROLLS[name]['visits']
    close = [i for i, (_, _, pulses) in enumerate(visits) if pulses.get(1) == CLOSED]
    if not close:
        return [{'kind': 'initial_servo_command', 'pulses': dict(final)}]
    key = type(next(iter(final)))
    before = dict(final)
    for _, _, pulses in visits[:close[0]]:
        before.update({key(k): v for k, v in pulses.items()})
    rows = [{'kind': 'initial_servo_command', 'pulses': before}]
    end = dict(before)
    for _, _, pulses in visits[close[0]:]:
        for sid, pulse in pulses.items():
            rows.append({'kind': 'look', 'pan_pulse': pulse} if sid == 6 else
                        {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
            end[key(sid)] = pulse
    if end != dict(final):
        raise ValueError('staged own history does not end at the staged pulses')
    return rows


def preroll_actions(name):
    spec = PREROLLS[name]
    rows = []
    for t, phase, pulses in spec['visits']:
        for rid in ROLES:
            for sid, pulse in pulses.items():
                action = ({'kind': 'look', 'pan_pulse': pulse} if sid == 6 else
                          {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
                rows.append({'t': t, 'phase': phase, 'robot_id': rid, 'action': action})
    return rows


def run_preroll(backend, name):
    """Teacher pre-roll on the backend (TEST SETUP). Returns the staging record part."""
    spec, t0 = PREROLLS[name], backend.now
    backend.set_deadline(t0+spec['end_s'])
    issued = []
    for row in preroll_actions(name):
        backend.advance_to(t0+row['t'])
        backend.issue(row['robot_id'], row['action'])
        issued.append({**row, 'sim_s': backend.now})
    backend.advance_to(t0+spec['end_s'])
    close = [r['sim_s'] for r in issued if r['action'].get('servo_id') == 1 and r['action']['pulse'] == CLOSED]
    return {'preroll': name, 'start_sim_s': t0, 'end_sim_s': backend.now, 'teacher_commands': issued,
            'close_issued_at_s': max(close) if close else None,
            'issued_pulses_after': {rid: dict(backend.commands[rid]) for rid in ROLES}}


def stated_prior(station):
    rows = [float(station[1])]
    std = [CASE_START_STD_X_M, max(CASE_START_STD_Y_MIN_M, max(rows)-min(rows)), CASE_START_STD_YAW_RAD]
    return {'kind': 'gaussian', 'mean_xyyaw': list(station), 'std_per_axis': std, 'is_fix': False,
            'definition': 'case start prior (zone_final_pair_runtime.Runtime: public start region mean, '
                          'std (0.15, max(0.15, row span), 0.174533)); staged region = one station',
            'source': 'staged start: case-start prior definition at the staged station (staging input)',
            'mean_is': 'true staged spawn pose', **TEST_SETUP_GT}


def enter(ctl, execution, stage, staging, now):
    """Set what the skipped states would have set, then enter the stage state."""
    spec = PROBE_SPECS[stage]
    own = execution.own
    report = own.last_report
    driver = getattr(ctl, 'driver', None)
    if driver is not None:
        driver.outcome = 'arrived'
    ctl.arm.commanded.update({k: v for k, v in own.servo.items() if k in ctl.arm.commanded})
    if spec['entry'] == 'wait_approach':
        # What the real approach records on arrival (run_m2_pair M2Student._approach): own PF estimate.
        est = driver.loc.estimate()
        ctl.claims['at_prestation'] = {'estimate': [round(est['x'], 4), round(est['y'], 4), round(est['yaw'], 4)],
                                       'std_xy_m': round(est['std_xy_m'], 4), 'looks': 0, 'sim_time': now,
                                       'source': 'stage probe entry: own PF estimate at the staged pre-station'}
        ctl.log(ctl.rid, 'stage_probe_entry', now, stage=stage, entry_state=spec['entry'],
                issued_servo=dict(own.servo), own_report=None if report is None else report.as_dict(),
                source='staged test setup; controller logic unchanged',
                ground_truth_inputs=['prior mean = true staged spawn pose (plan pre-station)'], **TEST_SETUP_GT)
        return ctl.set('wait_approach', now, stage_probe_entry=True)
    from harness.zone_final_pair_vision import GRASP_RADIUS_M
    ctl.grip_base = [float(GRASP_RADIUS_M), 0.]      # the fixed v3 aligned posture (static constant)
    ctl.hover, path = grasp_postures()
    ctl.grasp_pose = path[-1]
    # v98 _queue_open_descent bookkeeping (new grasp epoch, no anchors).
    ctl.high_raising, ctl.high_ready = False, False
    ctl.grip_epoch = getattr(ctl, 'grip_epoch', 0)+1
    ctl.pose_anchors, ctl.transit, ctl.floor_return_verified = {}, None, False
    ctl.pregrasp_done = True
    ctl.pregrasp_started_at = now
    ctl.grasp_estimate = None if report is None else [report.x_m, report.y_m, report.yaw_rad]
    ctl.claims['grasp_pose_estimate'] = {'xyyaw': ctl.grasp_estimate, 'sim_time': now,
                                         'source': 'stage probe entry: own PF report (stated prior)'}
    close_t = staging.get('close_issued_at_s')
    if spec['entry'] in ('grasp', 'wait_carry'):
        ctl.close_started_at = ctl.close_issued_at = close_t
    if spec['entry'] == 'wait_carry':
        ctl.grip_closed_epoch = ctl.grip_epoch
        ctl.claims['gripped'] = {'source': 'stage probe entry: teacher-staged close (own issued history)',
                                 'sim_time': close_t, **TEST_SETUP_GT}
        ctl.claims['lifted'] = {'decided_by': 'stage probe entry: teacher-staged HIGH', 'sim_time': now,
                                **TEST_SETUP_GT}
        obs = ctl.look(now)
        ctl.anchor = rt.m2.study.ob.held_signature(obs['image'])
        ctl.anchor_kind = 'lime_v1'
        ctl.anchor_full = rt.m2.hv3.hold_view_mask(obs['image'])
        ctl._anchor('high', obs, now)
        ctl.high_ready = True
    ctl.log(ctl.rid, 'stage_probe_entry', now, stage=stage, entry_state=spec['entry'],
            staged_close_issued_at_s=close_t, issued_servo=dict(own.servo),
            own_report=None if report is None else report.as_dict(),
            source='staged test setup; controller logic unchanged',
            ground_truth_inputs=['prior mean = true staged spawn pose']+(
                ['gripped/lifted claims and HIGH anchor = teacher pre-roll'] if spec['entry'] == 'wait_carry' else []),
            **TEST_SETUP_GT)
    return ctl.set(spec['entry'], now, stage_probe_entry=True)


def install(ctl, execution, stage, staging):
    orig = ctl.tick
    state = {'entered': False}

    def tick(now):
        if not state['entered']:
            state['entered'] = True
            enter(ctl, execution, stage, staging, now)
            if ctl.state == 'failed':
                return
        return orig(now)

    ctl.tick = tick
    return ctl


class StagedTeam(rt.Team):
    def __init__(self, executors, calibration, static_task, *, stage, staging):
        super().__init__(executors, calibration, static_task)

        def make_execution(own, status, arguments, plan, params, factory, *, policy):
            execution = rt.Execution(own, status, arguments, plan, params, calibration=calibration)
            install(execution.controller, execution, stage, staging)
            return execution
        self.start = MethodType(rt.bind(rt.previous.pair.PairTeam.start,
            make_plan=rt.previous.make_plan, PairExecution=make_execution), self)


class StagedRuntime(rt.Runtime):
    """v98 Runtime with a staged entry; no opening look_around (it would move the arm)."""
    def __init__(self, static, calibration_path, calibration_sha, *, seed, stage, staging, provider_factory=None):
        from harness.vision_pose_source_highpose import build_provider
        from harness.zone_pair_highpose_contract import CASE_CAP_S
        team = functools.partial(StagedTeam, stage=stage, staging=staging)
        initialize = rt.bind(rt.PreviousRuntime.__init__, Team=team)
        order = iter(ROLES)
        base_factory = provider_factory or build_provider

        def staged_provider(*args, **kwargs):
            # The parent sets the public dock prior once per provider (r1, r2
            # order); the staged run states its own prior at that same call.
            provider = base_factory(*args, **kwargs)
            prior, original = staging['priors'][next(order)], provider.init_prior

            def init_prior(*_dock, **_source):
                return original(tuple(prior['mean_xyyaw']), tuple(prior['std_per_axis']), source=prior['source'])
            provider.init_prior = init_prior
            return provider
        initialize(self, static, calibration_path, calibration_sha, seed=seed, provider_factory=staged_provider)
        self.job_sim_limit_s = CASE_CAP_S
        for actor in self.actors.values():
            actor.job_sim_limit_s = CASE_CAP_S
        # Same v98 frame gate as rt.Runtime (this class bypasses rt.Runtime.__init__).
        self.own_image_gates = rt.adopt_v98_frame_gate(self)
        # Same v98 look recovery; it needs a finished look_around, so HIGH entries (no opening look) never re-look.
        self.look_recovery = rt.adopt_look_recovery(self)
        self.stage, self.staging = stage, staging
        # HIGH entries skip the opening look_around (it would move the arm holding the beam); the align entry
        # keeps the normal one (coordinator 2026-10-04).
        look = PROBE_SPECS[stage]['opening_look_around']
        staging['skipped_opening_look_around'] = not look
        if not look:
            self.started = True

    def initial_commands(self, now, commands):
        """Hand the staged pre-roll to each robot as its own ordered command history (``own_history``)."""
        name = PROBE_SPECS[self.stage]['preroll']
        handed = {}
        for rid in ROLES:
            rows = own_history(name, commands[rid])
            for row in rows:
                self.actors[rid].on_command({'t': now, **row})
            # The provider applies commands after its fixed delay; record what its own LoadState rule gives for
            # these rows (a fresh instance of the same class), not a premature read of the live localizer.
            rule = type(self.providers[rid].provider.loc.load)()
            for row in rows:
                rule.command(row)
            handed[rid] = {'rows': len(rows), 'loaded_by_rule': bool(rule.loaded)}
        self.staging['own_history'] = {'preroll': name, 'robots': handed,
                                       'rule': 'LoadState own-command rule (close at grasp height)'}

    def record(self):
        value = super().record()
        value['stage_probe_staging'] = {'stage': self.stage, **self.staging}
        return value
