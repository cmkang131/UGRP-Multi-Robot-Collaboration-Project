"""Opt-in execution experiments for the frozen-scene student runner."""
from dataclasses import asdict, dataclass
import json
import math
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Options:
    physics_dt_ms: float | None = None
    noslip_iterations: int | None = None
    solver_iterations: int | None = None
    solver_tolerance: float | None = None
    physics_until_act: bool = False
    render_offsamples: int | None = None
    render_segments: int | None = None
    robot_render_every: int | None = None
    overhead_every: int | None = None
    overhead_empty_tiles: bool = False
    verify_overhead_tiles: bool = False
    wheel_deadlines: bool = False
    # idle-tick trims (DEFAULT off; the control laws are untouched, only stand-still ticks and the redundant part of a sweep go)
    sign_scan_early_stop: bool = False   # destination-sign sweep ends once the sign is in the place memory
    align_fast: bool = False             # face alignment waits 2 ticks after a pulse instead of 3
    survey_fast: bool = False            # look-around: 3 settle ticks per pan pose (was 5), 1 restore tick (was 7)
    act_hold_short: bool = False         # grasp end rule: 25 held rows (was 45), then 1.5 s settle (was 3.1 s) before the carry
    # multi-carry repairs (DEFAULT off; 2026-11-19)
    zone_close_fix: bool = False         # --zone-confirm-close accepts a sign card whose top border is cut off by the picture edge, read up to 2.6 m
    zone_close_far: bool = False         # with --zone-close-fix: the first close look is taken 2.3 m (not 1.5 m) from the floor point in front of the sign, readings up to 3.3 m
    return_pose_fallback: bool = False   # way back after a delivery starts from the dead-reckoned pose when the ceiling cameras lost the robot
    door_lane_fix: bool = False          # two robots face to face at the door: the one with the higher number backs away from the lane so the other passes
    oracle_return_face: bool = False     # --fixed oracle --multi-carry: the way back ends facing the next assigned box (the plan's place for it), not the middle of the remembered boxes
    oracle_wide_pick: bool = False       # --fixed oracle --multi-carry: a second carry accepts a listed box of the right colour within 1.0 m of the plan's place (0.30 m for the first carry)
    look_turn: bool = False              # a look-around repeated because the assigned box was not listed first turns the robot 40 deg right, then 80 deg left, then 120 deg right
    act_done_exit: bool = False          # --approach-survey-v1 with --regrasp-max N: the learned done bit raised 100 rows in a row in the grasp skill, the end rule not fired, is a failed grasp (empty-gripper path)

    def settings(self):
        return {name: value for name, value in asdict(self).items() if value is not None and value is not False}

    def model_settings(self):
        physics = {'timestep': None if self.physics_dt_ms is None else self.physics_dt_ms / 1000,
                   'noslip_iterations': self.noslip_iterations, 'iterations': self.solver_iterations,
                   'tolerance': self.solver_tolerance}
        quality = {'offsamples': self.render_offsamples, 'numslices': self.render_segments,
                   'numstacks': self.render_segments}
        return [{k: v for k, v in group.items() if v is not None} for group in (physics, quality)]

    def transform(self, xml):
        physics, quality = self.build_settings()
        if not (physics or quality):
            return xml
        root = ET.fromstring(xml)

        def child(parent, name):
            elem = parent.find(name)
            return ET.SubElement(parent, name) if elem is None else elem

        if physics:
            child(root, 'option').attrib.update({k: str(v) for k, v in physics.items()})
        if quality:
            child(child(root, 'visual'), 'quality').attrib.update({k: str(v) for k, v in quality.items()})
        return ET.tostring(root, encoding='unicode')

    def build_settings(self):
        physics, quality = self.model_settings()
        return ({} if self.physics_until_act else physics), quality

    def compiled_settings(self, model):
        """Check the compiled model after all frozen dependency transforms."""
        result = {}
        for group, owner in zip(self.build_settings(), (model.opt, model.vis.quality)):
            for name, expected in group.items():
                actual = type(expected)(getattr(owner, name))
                if actual != expected:
                    raise ValueError(f'compiled {name}={actual}, requested {expected}')
                result[name] = actual
        return result

    def start_before_act(self, world):
        fast, _ = self.model_settings()
        opt = world.model.opt
        saved = {k: type(v)(getattr(opt, k)) for k, v in fast.items()}
        state = {'original': saved, 'requested': fast, 'start_world_s': float(world.data.time), 'restore_world_s': None}
        for k, v in fast.items():
            setattr(opt, k, v)
        world._exec_before_act = state
        return state


def restore_at_first_act(world):
    state = world._exec_before_act
    if state['restore_world_s'] is None:
        for k, v in state['original'].items():
            setattr(world.model.opt, k, v)
        state['restore_world_s'] = float(world.data.time)


def add_arguments(parser):
    p = parser.add_argument_group('execution experiments (default off)')
    p.add_argument('--physics-dt-ms', type=float, choices=(0.25, 0.5, 1.0), help='physics step in milliseconds')
    p.add_argument('--noslip-iterations', type=int, help='post-solver friction iterations, including zero')
    p.add_argument('--solver-iterations', type=int, help='main solver iteration limit')
    p.add_argument('--solver-tolerance', type=float, help='main solver early stopping tolerance')
    p.add_argument('--physics-until-act', action='store_true',
                   help='use requested physics only during approach; restore the original world options at the first ACT command')
    p.add_argument('--render-offsamples', type=int, choices=(0, 1, 2, 4, 8), help='offscreen MSAA samples')
    p.add_argument('--render-segments', type=int, choices=(8, 12, 16, 24, 32),
                   help='slices and stacks for rendered primitives, including robot and ceiling cameras')
    p.add_argument('--robot-render-every', type=int, help='fresh own RGB every N control ticks, including ACT')
    p.add_argument('--overhead-every', type=int, help='ceiling update period in control ticks, after first fix')
    p.add_argument('--overhead-empty-tiles', action='store_true', help='omit ceiling tiles outside every top card')
    p.add_argument('--verify-overhead-tiles', action='store_true',
                   help='also detect on all tiles at the same tick and require identical poses')
    p.add_argument('--wheel-deadlines', action='store_true', help='rewrite wheel commands only at lease boundaries')
    p.add_argument('--sign-scan-early-stop', action='store_true',
                   help='end the destination-sign sweep at the first look window after which the sign is accepted into the place memory')
    p.add_argument('--align-fast', action='store_true', help='face alignment: 2 stand-still ticks after each pulse instead of 3')
    p.add_argument('--survey-fast', action='store_true',
                   help='look-around: 3 settle ticks after each pan command instead of 5, 1 restore tick instead of 7 (frames are read on the same rule)')
    p.add_argument('--act-hold-short', action='store_true',
                   help='grasp end rule asks for 25 held end-posture rows instead of 45 and the carry starts 1.5 s after it instead of 3.1 s')
    p.add_argument('--zone-close-fix', action='store_true',
                   help='with --zone-confirm-close: the close look accepts a destination sign whose top border is cut off by the picture edge (the code corners must lie inside) '
                        'and reads it from up to 2.6 m instead of 2.0 m')
    p.add_argument('--zone-close-far', action='store_true',
                   help='with --zone-confirm-close --zone-close-fix: take the first close look 2.3 m from the floor point in front of the sign (1.5 m otherwise) and read the sign up to 3.3 m: '
                        'the code is found reliably only while the card top, 0.255 m above the floor, is inside the picture of the downward looking carrying camera (measured on frames of MC6-P2_N03_S02 r3)')
    p.add_argument('--return-pose-fallback', action='store_true',
                   help='--multi-carry: the way back starts from the dead-reckoned pose (the last measured pose plus the planned rows) when the ceiling cameras have not read the robot for 1.5 s')
    p.add_argument('--oracle-return-face', action='store_true',
                   help='--fixed oracle --multi-carry (reference plan only): the way back leaves the door toward, and ends facing, the place the plan names for the next box. '
                        'Without it the robot faces the middle of the boxes it remembers; in P2_N03_S07 r3 stood 2.6 m from its box at 67 degrees and never saw it')
    p.add_argument('--oracle-wide-pick', action='store_true',
                   help='--fixed oracle --multi-carry (reference plan only): at a second carry the plan takes the listed box of the right colour nearest to its place within 1.0 m, '
                        'not within 0.30 m. A box 2-3 m away is read 0.3-0.5 m off (range error); in P2_N03_S09 r3 the blue box e was listed 0.51 m off and the run finished without it')
    p.add_argument('--look-turn', action='store_true',
                   help='--multi-carry: a look-around the planner repeats because its box was not listed (the same place gives the same list) first turns the robot '
                        '40 degrees right, then 80 degrees left, then 120 degrees right (the box was at 67 degrees, the edge of the survey, in P2_N03_S07 r3)')
    p.add_argument('--door-lane-fix', action='store_true',
                   help='--multi-carry: two robots face to face at the door (each the obstacle beyond the door of the other) end the deadlock: the robot with the higher number '
                        'backs away from the door lane, the other passes (without it both wait 20 times and give up); a robot waits up to 90 s at a busy door instead of 40 s, '
                        'a lower-numbered robot has the right of way only within 2.0 m of the door, a robot the ceiling cameras missed keeps its last place for 5 s, '
                        'a stop too close to the door for another look is checked for heading and offset like any look stop, '
                        'and a way back that failed at the door is tried again (twice)')
    p.add_argument('--act-done-exit', action='store_true',
                   help='grasp failure exit (with --regrasp-max 1 or more, like the box-not-seen exit): the learned done bit raised for 100 control rows in a row (10 s) in the grasp skill, '
                        'the grasp end rule not fired, is reported as a failed grasp: empty gripper, look around and choose again, or the robot ends when no try is left. '
                        'Without it the done bit is ignored there and a robot whose box is gone stands until the cap (a work record)')


def from_args(parser, args):
    options = Options(**{name: getattr(args, name) for name in Options.__dataclass_fields__})
    for name in ('solver_iterations', 'robot_render_every', 'overhead_every'):
        value = getattr(options, name)
        if value is not None and value < 1:
            parser.error('--' + name.replace('_', '-') + ' must be positive')
    if options.noslip_iterations is not None and options.noslip_iterations < 0:
        parser.error('--noslip-iterations must be nonnegative')
    if options.solver_tolerance is not None and not (math.isfinite(options.solver_tolerance) and options.solver_tolerance >= 0):
        parser.error('--solver-tolerance must be finite and nonnegative')
    if options.physics_until_act and not options.model_settings()[0]:
        parser.error('--physics-until-act needs at least one physics override')
    if (options.overhead_every or options.overhead_empty_tiles or options.verify_overhead_tiles) and not args.overhead:
        parser.error('ceiling switches require --overhead')
    return options if options.settings() else None


def advance_wheel_deadlines(world, requests, until):
    # Each request owns its port until the next yield. The v7 wheel setter
    # only assigns motor_command. tick() can issue a new stop/hold tuple.
    # Reapply after such a write even if the requested lease did not expire.
    issued = [None] * len(requests)
    due = [-math.inf] * len(requests)
    while float(world.data.time) < until - 1e-8:
        now = float(world.data.time)
        for i, req in enumerate(requests):
            port = req['port']
            port.tick(now)
            if req['wheels'] is not None and (now >= due[i] or issued[i] is not port._motor_commands):
                deadlines = req['deadlines']
                port._set_motors(tuple(w if now < end else 0. for w, end in zip(req['wheels'], deadlines)))
                issued[i] = port._motor_commands
                due[i] = min((end for end in deadlines if now < end), default=math.inf)
        world._physics_step_for(requests[0]['robot'])


def read_tiles(cameras, needed, capture, reader, verify, stats):
    """Keep overlapping tiles in the reader's original order, including area ties."""
    pictures = {name: capture(name) for name, _ in cameras if verify or name in needed}
    selected = {name: pic for name, pic in pictures.items() if name in needed}
    result = reader.read(selected)
    stats['selected'] += len(selected)
    stats['omitted'] += len(cameras) - len(selected)
    if verify:
        full = reader.read(pictures)
        stats['checks'] += 1
        if full != result:
            stats['mismatches'] += 1
            raise ValueError(f'ceiling tile poses differ: selected={result}, full={full}')
    return result


def reused_frame_reason(idle_reason, every, tick, previous_frame):
    if previous_frame is None:
        return None
    if idle_reason is None and every and tick % every:
        return 'cadence'
    return idle_reason


class DecisionTrace:
    """Observe arguments at the actual planner interface, after task setup."""

    def __init__(self, brain, path):
        self.brain = brain
        self.boxes = {}
        self.path = path
        path.touch(exist_ok=False)

    def __getattr__(self, name):
        return getattr(self.brain, name)

    def tell(self, rid, facts):
        if 'seen_boxes' in facts:
            self.boxes[rid] = facts['seen_boxes']
        return self.brain.tell(rid, facts)

    def decide(self, rid, now_s, point, options):
        row = {'rid': rid, 't': now_s, 'point': point, 'options': options, 'boxes': self.boxes.get(rid, [])}
        with self.path.open('a') as stream:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
        return self.brain.decide(rid, now_s, point, options)


class DeliveryAudit:
    """Evaluation side only. Time the last uninterrupted physical setdown in a zone."""

    def __init__(self, world, layout, zones, criteria, scoring_keys):
        import numpy as np

        m = world.model
        self.criteria = criteria
        self.zones = zones
        self.boxes = {}
        self.scoring_keys = {box['id']: scoring_keys[box['body']] for box in layout}
        self.fingers = {m.geom(rid + '__' + side + '_finger').id for rid in world.controllers
                        for side in ('left', 'right')}
        for box in layout:
            body = m.body(box['body']).id
            geoms = np.flatnonzero((m.geom_bodyid == body) & (m.geom_contype != 0))
            if not len(geoms):
                raise ValueError('no collision geometry for delivery audit: ' + box['id'])
            self.boxes[box['id']] = (body, geoms)
        self.current = {}
        self.last_s = None
        self.samples = 0

    def sample(self, world, now):
        import mujoco
        import numpy as np

        d, m, limits = world.data, world.model, self.criteria
        finger_load = {}
        wrench = np.empty(6)
        for contact_index in range(d.ncon):
            contact = d.contact[contact_index]
            a, b = int(contact.geom1), int(contact.geom2)
            if a in self.fingers or b in self.fingers:
                mujoco.mj_contactForce(m, d, contact_index, wrench)
                finger, other = (a, b) if a in self.fingers else (b, a)
                pair = (int(m.geom_bodyid[other]), finger)
                finger_load[pair] = finger_load.get(pair, 0.) + abs(wrench[0])
        loaded = {body for (body, _), force in finger_load.items() if force >= limits['finger_max_n']}
        for key, (body, geoms) in self.boxes.items():
            x, y = d.xpos[body, :2]
            zone = next((z for z, (x0, x1, y0, y1) in self.zones.items() if x0 <= x <= x1 and y0 <= y <= y1), None)
            if zone is not None and body not in loaded:
                # Same box support height, upright angle and speed as the student evaluator.
                z_bottom = (d.geom_xpos[geoms, 2] - (np.abs(d.geom_xmat[geoms, 6:9]) * m.geom_size[geoms]).sum(axis=1)).min()
                lo, hi = limits['clearance_m']
                mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, body, wrench, 0)
                if (not lo <= z_bottom <= hi or d.xmat[body, 8] < math.cos(math.radians(limits['tilt_deg']))
                        or np.linalg.norm(wrench[3:]) > limits['linear_speed_m_s']):
                    zone = None
            else:
                zone = None
            if key not in self.current or self.current[key][0] != zone:
                self.current[key] = (zone, now)
        self.last_s = now
        self.samples += 1

    def record(self):
        held = self.criteria['hold_s']
        settled = {key: {'zone': zone, 'at_s': round(start + held, 1)}
                   for key, (zone, start) in self.current.items()
                   if zone is not None and self.last_s - start >= held - 1e-8}
        return {'samples': self.samples, 'last_s': self.last_s, 'criteria': self.criteria,
                'scoring_keys': self.scoring_keys, 'settled': settled}
