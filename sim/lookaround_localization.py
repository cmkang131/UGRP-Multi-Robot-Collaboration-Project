"""setdown_lookaround_v1: where to look after a set-down, and what the look tells the own pose.

User 2026-10-14: "둘러보기 위해서 아래에 뒀으면, 진짜 좀 둘러봐야 할듯".

Inputs are the static map, the own pose estimate of the map code moved by own
issued commands, the own servo commands, and the own RGB frame. No simulator
state enters: the caller scores the estimate against truth in a separate
evaluation record.

- Landmarks: wall faces (base line), coloured zone edges and door jambs of the
  static map, sampled as points (sim/active_lookaround.jacobian_rows models).
- Visibility prediction for a candidate (body yaw, pan): camera pose from own
  commands (harness/servo_camera_fk, v3 chain), measured pinhole K at 640x480,
  image bounds, range, facing side and 2-D wall occlusion.
- View choice: sim/active_lookaround.plan_views (greedy expected information
  gain, canonical order).
- Detection reuses the existing OpenCV localisation modules unchanged: wall
  bands (harness/opencv_wall_observation.observations with the registered
  own-image gates), wall base endpoints (harness/zone_solo_cyan_amcl_sensor
  .endpoints), floor zone lines and doors (harness/zone_solo_cyan_landmarks).
  Scoring: zone lines/doors by the existing landmark_likelihood; wall points by
  the existing 1 cm distance raster (zone_solo_cyan_likelihood_field.Field) in
  the product form of the likelihood field model (see WALL_FIELD; the AMCL cubic
  accumulator is flat at cm scale). The pose is updated by scoring a local grid
  around the estimate times the Gaussian prior (Fox/Burgard/Thrun grid Markov
  localisation), then moment-matched back to a Gaussian.
"""
from __future__ import annotations

import copy
import math

import cv2
import numpy as np

from sim.active_lookaround import OwnPose, plan_views, wrap

OPTION = 'setdown_lookaround_v1'
MODES = ('setdown_lookaround_v1', 'setdown_lookaround_v2', 'setdown_global_v1')
LOOK_ARM = {3: 896, 4: 2035, 5: 1894}      # v1: harness/zone_pair_highpose.HIGH arm joints
# v2 (3635a226 diagnostic): HIGH tilts the camera 30 deg down, the floor is seen only 0.15-0.94 m ahead (FK), so
# walls 0.9-3 m away never enter the image and floor-tile edges were read as wall bases. The release teacher's own
# folded pose (FOLDED_BACKOFF) tilts it 10.9 deg down: floor from 0.37 m to the horizon, walls in view.
LOOK_ARM_V2 = {3: 820, 4: 2320, 5: 1320}
LOOK_ARMS = {'setdown_lookaround_v1': LOOK_ARM, 'setdown_lookaround_v2': LOOK_ARM_V2, 'setdown_global_v1': LOOK_ARM_V2}
# v2 data association and acceptance (standard tests, references in the PR):
# individual compatibility gate per wall point (chi2 1 dof 99 %), the point's mapped wall face must be one the
# static map predicts visible from the prior for that view, one joint update over all views, then a joint
# compatibility test of the correction against the own-command prior (chi2 3 dof 99 %), a covariance-shrink test
# and a posterior inlier ratio. Not enough gated evidence (or evidence from one view only) -> no correction.
V2 = {'gate_chi2_1': 6.63, 'joint_chi2_3': 11.34, 'min_wall_inliers': 12, 'min_features': 2, 'min_views': 2, 'min_per_view': 4, 'min_inlier_ratio': .7,
      'wall_range_m': 2.5, 'sigma0_m': .03, 'edge_px': 2., 'floor_gate_m': .2, 'floor_gate_deg': 10., 'door_gate_m': .3}
GRIPPER_OPEN = 2000                         # FK is qualified only with the gripper open (servo 1 > 1600)
WIDTH, HEIGHT = 640, 480                    # existing OpenCV modules (vis3 mp, check_frame) work at native size only
VIEW_SETTLE_S = .8                          # every view: command, then 0.8 s (pan <=1000 pulses at 2000 pulse/s + 0.3 s settle)
ARM_MOVE_S = 1.0                            # into / out of the look arm pose
YAW_RATE_RAD_S = .35                        # sim/visible_belief nominal 0.35-duty yaw rate (free robot unmeasured)
PULSE_MAX_S = .15
WHEEL = .35
SAMPLE_WALL_M, SAMPLE_EDGE_M = .25, .20
RANGE_WALL_M, RANGE_EDGE_M, RANGE_DOOR_M = 3.0, 2.5, 3.0
SIGMA_WALL_M, SIGMA_EDGE_M, SIGMA_DOOR_M = .05, .04, .10
IMAGE_MARGIN_PX = 12
GRID = {'xy_half_sigma': 3., 'xy_step_m': .01, 'yaw_half_sigma': 3., 'yaw_step_rad': math.radians(.5), 'max_poses': 120000}
PAN_DEG_PER_PULSE = 180./2000.


def pan_pulse(pan_deg):
    return int(round(1500+pan_deg/PAN_DEG_PER_PULSE))


def look_servo(pan_deg, arm=None):
    return {1: GRIPPER_OPEN, **(LOOK_ARM if arm is None else arm), 6: pan_pulse(pan_deg)}


def wall_rects(static):
    out = []
    for o in static['obstacles']:
        if o.get('kind') == 'wall':
            (x, y), (dx, dy) = o['center_m'], o['half_extents_m']
            out.append((o['id'], x-dx, x+dx, y-dy, y+dy))
    return out


def map_landmarks(static):
    """Static-map landmark samples. group = the physical feature (one wall face, one zone edge, one door)."""
    rects = wall_rects(static); lms = []
    (bx0, bx1, by0, by1) = static['bounds_m']

    def inside_other(p, own):
        return any(a-.01 < p[0] < b+.01 and c-.01 < p[1] < d+.01 for i, a, b, c, d in rects if i != own)

    for wid, a, b, c, d in rects:
        faces = {'s': ((a, c), (b, c), (0., -1.)), 'n': ((a, d), (b, d), (0., 1.)),
                 'w': ((a, c), (a, d), (-1., 0.)), 'e': ((b, c), (b, d), (1., 0.))}
        for face, (p, q, n) in faces.items():
            length = math.dist(p, q); k = max(1, int(length/SAMPLE_WALL_M))
            for j in range(k):
                f = (j+.5)/k; pt = (p[0]+(q[0]-p[0])*f, p[1]+(q[1]-p[1])*f)
                probe = (pt[0]+.03*n[0], pt[1]+.03*n[1])
                if not (bx0 < probe[0] < bx1 and by0 < probe[1] < by1) or inside_other(probe, wid):
                    continue
                lms.append({'id': f'{wid}:{face}:{j}', 'group': f'{wid}:{face}', 'type': 'wall', 'model': 'line_point',
                            'xy': pt, 'normal': n, 'sigma': SIGMA_WALL_M, 'range': RANGE_WALL_M})
    for name, r in static['regions'].items():
        (x, y), (a, b) = r['center_m'], r['half_extents_m']
        corners = [(x-a, y-b), (x+a, y-b), (x+a, y+b), (x-a, y+b)]
        for j in range(4):
            p, q = corners[j], corners[(j+1) % 4]; d = (q[0]-p[0], q[1]-p[1]); L = math.hypot(*d)
            n = (-d[1]/L, d[0]/L); k = max(1, int(L/SAMPLE_EDGE_M))
            for i in range(k):
                f = (i+.5)/k; pt = (p[0]+d[0]*f, p[1]+d[1]*f)
                if inside_other(pt, None):
                    continue
                lms.append({'id': f'{name}:e{j}:{i}', 'group': f'{name}:e{j}', 'type': 'zone_edge', 'model': 'line_point',
                            'xy': pt, 'normal': n, 'sigma': SIGMA_EDGE_M, 'range': RANGE_EDGE_M, 'two_sided': True})
    for door in static.get('passages', []):
        if door.get('kind') != 'door':
            continue
        (x, y), w = door['center_m'], float(door['width_m'])
        ax = (0., 1.) if door.get('axis') == 'x' else (1., 0.)   # opening runs along the wall line
        for side, s in (('a', -1.), ('b', 1.)):
            pt = (x+s*ax[0]*w/2, y+s*ax[1]*w/2)
            lms.append({'id': f"{door['id']}:{side}", 'group': door['id'], 'type': 'door', 'model': 'point',
                        'xy': pt, 'sigma': SIGMA_DOOR_M, 'range': RANGE_DOOR_M, 'two_sided': True})
    return lms


def _segment_hits_rect(p, q, rect):
    """Liang-Barsky clip of segment p->q against an axis-aligned rectangle."""
    _, a, b, c, d = rect; t0, t1 = 0., 1.; dx, dy = q[0]-p[0], q[1]-p[1]
    for pk, qk in ((-dx, p[0]-a), (dx, b-p[0]), (-dy, p[1]-c), (dy, d-p[1])):
        if abs(pk) < 1e-12:
            if qk < 0:
                return False
            continue
        r = qk/pk
        if pk < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


class Camera:
    """Own-command camera pose (body frame) and measured pinhole K at 640x480."""
    def __init__(self):
        from harness.servo_camera_fk import transform_from_commands, OPTION as FK
        from sim.masterpi_camera_profile import scaled_camera_matrix
        self._fk, self._opt = transform_from_commands, FK
        self.K = scaled_camera_matrix(WIDTH, HEIGHT); self._cache = {}

    def pose(self, servo):
        key = tuple(sorted(servo.items()))
        if key not in self._cache:
            out, reason = self._fk(servo, camera_pose=self._opt)
            self._cache[key] = (out, reason)
        return self._cache[key]


def visible_fn_for(static, camera, arm=None, wall_range=None):
    rects = wall_rects(static)

    def visible(pose, body_yaw_deg, pan_deg, lm):
        cam, _ = camera.pose(look_servo(pan_deg, arm))
        if cam is None:
            return False
        origin, rot = cam
        yaw = pose[2]+math.radians(body_yaw_deg); c, s = math.cos(yaw), math.sin(yaw)
        cw = (pose[0]+c*origin[0]-s*origin[1], pose[1]+s*origin[0]+c*origin[1])
        lx, ly = lm['xy']
        if math.dist(cw, (lx, ly)) > (wall_range if (wall_range and lm['type'] == 'wall') else lm['range']):
            return False
        if not lm.get('two_sided') and (cw[0]-lx)*lm['normal'][0]+(cw[1]-ly)*lm['normal'][1] <= 0:
            return False
        dx, dy = lx-pose[0], ly-pose[1]
        body = np.array([c*dx+s*dy, -s*dx+c*dy, 0.])
        q = rot.T@(body-origin)
        if q[2] <= .05:
            return False
        u, v = (camera.K@q)[:2]/q[2]
        if not (IMAGE_MARGIN_PX <= u <= WIDTH-IMAGE_MARGIN_PX and IMAGE_MARGIN_PX <= v <= HEIGHT-IMAGE_MARGIN_PX):
            return False
        L = math.dist(cw, (lx, ly)); back = ((lx-cw[0])/L, (ly-cw[1])/L)
        end = (lx-.03*back[0], ly-.03*back[1])            # stop short of the landmark's own wall face
        return not any(_segment_hits_rect(cw, end, r) for r in rects)
    return visible


class LookaroundLocalizer:
    """One robot's own-pose estimate, look plan and image updates (no simulator input)."""

    def __init__(self, static, estimate, *, sigma_xy=.05, sigma_yaw=math.radians(2.), odometry_profile='off',
                 mode='setdown_lookaround_v1', map_pose_known=True, localization_support='off'):
        if mode not in MODES:
            raise ValueError(mode)
        from sim.global_landmark_localization import SUPPORT_MODES
        if localization_support not in SUPPORT_MODES or (localization_support != 'off' and mode != 'setdown_global_v1'):
            raise ValueError('localization support requires global landmark localization')
        self.localization_support = localization_support
        self.mode, self.arm = mode, LOOK_ARMS[mode]
        self.map_pose_known = bool(map_pose_known)
        self.v2 = mode == 'setdown_lookaround_v2'
        from harness import vision_loc_protocol as vp
        from harness import zone_pair_highpose_contract as contract
        from harness.zone_solo_cyan_likelihood_field import Field
        from harness.zone_solo_cyan_landmarks import MapFeatures
        self.static = static
        self.own = OwnPose(estimate, sigma_xy, sigma_yaw)
        self.command_own = OwnPose(estimate, sigma_xy, sigma_yaw)
        self.global_matcher = None
        if mode == 'setdown_global_v1':
            from sim.global_landmark_localization import GlobalLandmarkMatcher
            self.global_matcher = GlobalLandmarkMatcher(static, localization_support=localization_support)
        self.profile = odometry_profile
        self.camera = Camera()
        self.landmarks = map_landmarks(static)
        self.visible = visible_fn_for(static, self.camera, self.arm, V2['wall_range_m'] if self.v2 else None)
        self.vl = vp.load_vis3()[0]
        self.gates = contract.own_image_gates()
        self.field = Field(static); self.mapped = MapFeatures(static)
        self.views, self.plan = [], None
        self.pending, self.decision = [], None

    # --- own motion ---
    def propagate(self, wheels, seconds):
        from sim.visible_belief import odometry
        if seconds > 0 and any(wheels):
            self.own.propagate(*odometry(wheels, seconds, self.profile))
            self.command_own.propagate(*odometry(wheels, seconds, self.profile))

    # --- view plan ---
    def make_plan(self, start_pan_pulse=1500):
        if not self.map_pose_known or self.global_matcher is not None:
            # Start global acquisition with a body-relative panorama. The
            # legacy unknown-pose path still only records the detections.
            self.plan = {'expected_gain_nats': None, 'rotated': False, 'expected_landmarks': [],
                         'views': [{'body_yaw_deg': 0., 'pan_deg': p, 'pan_pulse': pan_pulse(p), 'expected': []}
                                   for p in (-60., 0., 60.)],
                         'pose_estimate_at_plan': [float(z) for z in self.own.x],
                         'pose_frame': 'map' if self.map_pose_known else 'arbitrary_command_start',
                         'map_pose_known': self.map_pose_known}
            return self.plan
        start = (start_pan_pulse-1500)*PAN_DEG_PER_PULSE
        # v2: no body rotation (free-robot yaw rate unmeasured; the one rotated run lost its re-grasp)
        plan = plan_views(tuple(self.own.x), self.own.P, self.landmarks, self.visible, start_pan=start,
                          **({'body_yaws': (0.,)} if self.v2 else {}))
        self.plan = {'expected_gain_nats': plan['expected_gain_nats'], 'rotated': plan['rotated'],
                     'expected_landmarks': plan['expected_landmarks'],
                     'views': [{'body_yaw_deg': v['body_yaw_deg'], 'pan_deg': v['pan_deg'], 'pan_pulse': pan_pulse(v['pan_deg']),
                                'expected': v['landmarks']} for v in plan['views']],
                     'pose_estimate_at_plan': [float(z) for z in self.own.x],
                     'sigma_at_plan': [float(math.sqrt(self.own.P[i, i])) for i in range(3)]}
        return self.plan

    def script(self, restore=None):
        """Fixed-timing command script for the plan: arm to look pose, (rotate), views, (rotate back), (restore arm)."""
        steps = []; yaw_now = 0.
        views = self.plan['views'] if self.plan else []
        first = views[0]['pan_pulse'] if views else 1500
        steps.append({'servo': look_servo((first-1500)*PAN_DEG_PER_PULSE, self.arm), 'wait': ARM_MOVE_S, 'capture': False, 'label': 'arm_to_look'})
        for v in views:
            if v['body_yaw_deg'] != yaw_now:
                steps.append({'wheels': rotate_plan(math.radians(v['body_yaw_deg']-yaw_now), self.profile), 'wait': .3, 'capture': False,
                              'label': f"rotate_{v['body_yaw_deg']:+.0f}"})
                yaw_now = v['body_yaw_deg']
            steps.append({'servo': look_servo(v['pan_deg'], self.arm), 'wait': VIEW_SETTLE_S, 'capture': True,
                          'label': f"view_{v['body_yaw_deg']:+.0f}_{v['pan_deg']:+.0f}"})
        if yaw_now:
            steps.append({'wheels': rotate_plan(math.radians(-yaw_now), self.profile), 'wait': .3, 'capture': False, 'label': 'rotate_back'})
        if restore:    # v2: back to the exact pre-look arm pose, so what follows starts as without the look
            steps.append({'servo': dict(restore), 'wait': ARM_MOVE_S, 'capture': False, 'label': 'restore_arm'})
        return steps

    # --- detection + update ---
    def observe(self, now, raw_rgb, servo):
        """raw_rgb: own fisheye frame (H, W, 3) uint8 RGB at 640x480. Returns the view record (no truth)."""
        from harness.opencv_wall_observation import observations, DETECTOR
        from harness.vision_pose_source_final import measured_column_model
        from harness.zone_solo_cyan_amcl_sensor import endpoints
        from harness.zone_solo_cyan_landmarks import floor_features, door_features, ground
        rec = {'t': float(now), 'pan_pulse': int(servo[6]), 'prior': [float(z) for z in self.own.x],
               'prior_sigma': [float(math.sqrt(self.own.P[i, i])) for i in range(3)]}
        if self.global_matcher is not None:
            rec['command_pose'] = self.command_own.x.tolist()
            rec['servo'] = dict(servo)
        cam, reason = self.camera.pose(servo)
        if cam is None:
            rec.update(status='camera_unqualified', reason=reason); self.views.append(rec); return rec
        if raw_rgb.shape != (HEIGHT, WIDTH, 3):
            raise ValueError(f'LOOKAROUND_FRAME_SIZE {raw_rgb.shape}')
        mp = self.vl.mp
        cm = measured_column_model(mp, {'origin_m': cam[0], 'rotation': cam[1]},
                                   mp.column_positions(DETECTOR['columns'], int(DETECTOR['strip_half_px'])))   # same columns as the PF
        bgr = np.ascontiguousarray(cv2.cvtColor(raw_rgb, cv2.COLOR_RGB2BGR))
        obs = observations(self.vl, bgr, cm, self.gates['values'])
        walls = endpoints(cm, obs)
        und = mp.undistort(bgr)
        yy, xx = np.indices((HEIGHT, WIDTH))
        _, valid, _ = ground(cm, np.c_[xx.ravel(), yy.ravel()], mp.K_INV)
        clear = valid.reshape(HEIGHT, WIDTH)
        base = np.full(WIDTH, -1.)
        cols = np.asarray(obs.columns, float); ok = (obs.b_kind == 1) & np.isfinite(obs.b_lo)
        if ok.any():
            base = np.interp(np.arange(WIDTH), cols[ok], obs.b_lo[ok], left=-1., right=-1.)
        clear &= yy > base[None, :]                     # floor only below the detected wall base
        floors = floor_features(und, cm, mp.K_INV, self.mapped, clear)
        doors = door_features(und, cm, obs, np.linalg.inv(mp.K_INV), clear)
        rec.update(status='measured', wall_points=int(len(walls)), floor_lines=len(floors), doors=len(doors),
                   features=copy.deepcopy(floors+doors))
        if not self.map_pose_known or self.global_matcher is not None:
            rec.update(wall_points_body=np.asarray(walls).reshape(-1, 2).tolist(), seen_groups=[],
                       map_pose_known=self.map_pose_known,
                       update_skipped='global_consensus_pending' if self.global_matcher is not None else 'map_pose_unknown')
            self.views.append(rec)
            return rec
        if self.v2:
            self._gate(walls, floors, doors, servo, cam, rec)
            rec['seen_groups'] = self.seen_groups(walls, floors, doors)
            self.views.append(rec)
            return rec
        if len(walls)+len(floors)+len(doors):
            self._grid_update(walls, floors+doors, rec)
        rec['posterior'] = [float(z) for z in self.own.x]
        rec['posterior_sigma'] = [float(math.sqrt(self.own.P[i, i])) for i in range(3)]
        rec['seen_groups'] = self.seen_groups(walls, floors, doors)
        self.views.append(rec)
        return rec

    # --- v2: gated detections, one joint update with acceptance tests ---
    def _gate(self, walls, floors, doors, servo, cam, rec):
        x0, P = self.own.x, self.own.P; c, s = math.cos(x0[2]), math.sin(x0[2])
        pan = (int(servo[6])-1500)*PAN_DEG_PER_PULSE; h = float(cam[0][2]); f = float(self.camera.K[1, 1])
        expected = {l['group'] for l in self.landmarks if l['type'] == 'wall' and self.visible(tuple(x0), 0., pan, l)}
        walls = np.asarray(walls, float).reshape(-1, 2)
        sig_xy = math.sqrt(.5*(P[0, 0]+P[1, 1])); sig_t = math.sqrt(P[2, 2])
        keep, sig, why = [], [], {'range': 0, 'gate': 0, 'not_predicted': 0}
        for qx, qy in walls:
            r = math.hypot(qx-cam[0][0], qy-cam[0][1])
            if r > V2['wall_range_m']:
                why['range'] += 1; continue
            wx, wy = x0[0]+c*qx-s*qy, x0[1]+s*qx+c*qy
            d = float(self.field.distances(np.array([[wx, wy]]))[0])
            sm = math.hypot(V2['sigma0_m'], V2['edge_px']*r*r/(f*h))          # ground-projection error grows with r^2
            sd = math.sqrt(sm*sm+sig_xy**2+(math.hypot(qx, qy)*sig_t)**2)
            if d*d > V2['gate_chi2_1']*sd*sd:
                why['gate'] += 1; continue
            g = min(((abs((wx-l['xy'][0])*l['normal'][0]+(wy-l['xy'][1])*l['normal'][1])+
                      .2*max(0., math.dist((wx, wy), l['xy'])-SAMPLE_WALL_M), l['group'])
                     for l in self.landmarks if l['type'] == 'wall'))[1]
            if g not in expected:
                why['not_predicted'] += 1; continue
            keep.append((qx, qy)); sig.append(sm)
        feats = []
        for ft in floors:
            mx, my = np.mean(ft['endpoints'], axis=0); wx, wy = x0[0]+c*mx-s*my, x0[1]+s*mx+c*my
            ang = x0[2]+math.atan2(ft['normal'][1], ft['normal'][0]); ok = False
            for e in self.mapped.edges:
                hd = abs(e['hue']-ft['hue']); hd = min(hd, 180-hd)
                if hd > 12:
                    continue
                v = e['b']-e['a']; fr = np.clip(((np.array([wx, wy])-e['a'])@v)/(v@v), 0, 1); q = e['a']+fr*v
                da = abs(wrap(ang-math.atan2(e['normal'][1], e['normal'][0])))
                if math.dist((wx, wy), q) <= V2['floor_gate_m'] and math.degrees(da) <= V2['floor_gate_deg']:
                    ok = True; break
            if ok:
                feats.append(ft)
        for ft in doors:
            mx, my = ft['center']; wx, wy = x0[0]+c*mx-s*my, x0[1]+s*mx+c*my
            if any(math.dist((wx, wy), d['center']) <= V2['door_gate_m'] for d in self.mapped.doors):
                feats.append(ft)
        self.pending.append({'walls': keep, 'sigmas': sig, 'features': feats})
        rec['gate'] = {'wall_in': len(keep), 'wall_out': why, 'features_in': len(feats),
                       'features_out': len(floors)+len(doors)-len(feats), 'expected_wall_groups': sorted(expected)}
        rec['wall_points_body'] = [[round(float(a), 3), round(float(b), 3)] for a, b in walls]

    def finalize(self):
        """v2: one joint update over every view's gated detections; keep the prior unless every test passes."""
        if getattr(self, 'global_matcher', None) is not None:
            self.decision = self.global_matcher.fit(self.views, self.command_own.x)
            # A failed fresh observation revokes release authorization. The old
            # map estimate may still propagate, but cannot authorize placement.
            if self.decision['accepted']:
                self.own.x = np.array(self.decision['proposed'])
                self.own.P = np.diag(np.array(self.decision['sigma'])**2)
                self.map_pose_known = True
            return self.decision
        if not self.map_pose_known:
            self.decision = {'accepted': False, 'reason': 'map_pose_unknown', 'views_with_evidence':
                             sum(bool(v.get('wall_points', 0)+v.get('floor_lines', 0)+v.get('doors', 0)) for v in self.views)}
            return self.decision
        if not self.v2:
            return None
        walls = [p for v in self.pending for p in v['walls']]; sig = [x for v in self.pending for x in v['sigmas']]
        feats = [f for v in self.pending for f in v['features']]
        dec = {'wall_inliers': len(walls), 'features': len(feats), 'prior': [float(z) for z in self.own.x],
               'prior_sigma': [float(math.sqrt(self.own.P[i, i])) for i in range(3)]}
        views = sum(1 for v in self.pending if len(v['walls'])+2*len(v['features']) >= V2['min_per_view'])
        dec['views_with_evidence'] = views
        if len(walls) < V2['min_wall_inliers'] and len(feats) < V2['min_features']:
            dec.update(accepted=False, reason='insufficient_evidence'); self.decision = dec; return dec
        if views < V2['min_views']:     # one direction alone: no correction (avoid single-view over-correction)
            dec.update(accepted=False, reason='single_view'); self.decision = dec; return dec
        rec = {}
        x_new, P_new = self._grid_update(np.asarray(walls).reshape(-1, 2), feats, rec, sigmas=np.asarray(sig), commit=False)
        delta = x_new-self.own.x; delta[2] = wrap(delta[2])
        d2 = float(delta@np.linalg.inv(self.own.P)@delta)
        shrink = float(np.linalg.det(P_new)) < float(np.linalg.det(self.own.P))
        ratio = None
        if walls:
            c, s = math.cos(x_new[2]), math.sin(x_new[2]); q = np.asarray(walls)
            d = self.field.distances(np.c_[x_new[0]+c*q[:, 0]-s*q[:, 1], x_new[1]+s*q[:, 0]+c*q[:, 1]])
            ratio = float(np.mean(d <= 2*np.asarray(sig)))
        tests = {'joint_chi2': d2, 'joint_ok': d2 <= V2['joint_chi2_3'], 'cov_shrinks': shrink,
                 'inlier_ratio': ratio, 'inlier_ok': ratio is None or ratio >= V2['min_inlier_ratio']}
        ok = tests['joint_ok'] and tests['cov_shrinks'] and tests['inlier_ok']
        dec.update(accepted=bool(ok), tests=tests, grid=rec.get('grid'), proposed=[float(z) for z in x_new],
                   reason='accepted' if ok else ','.join(k for k in ('joint_ok', 'cov_shrinks', 'inlier_ok') if not tests[k]))
        if ok:
            self.own.x, self.own.P = x_new, P_new
        dec['posterior'] = [float(z) for z in self.own.x]
        dec['posterior_sigma'] = [float(math.sqrt(self.own.P[i, i])) for i in range(3)]
        self.decision = dec
        return dec

    def _grid_update(self, walls, features, rec, sigmas=None, commit=True):
        from harness.zone_solo_cyan_landmarks import landmark_likelihood
        x0 = self.own.x; P = self.own.P
        sx, sy, st = (math.sqrt(P[i, i]) for i in range(3))
        hx = max(GRID['xy_step_m'], GRID['xy_half_sigma']*sx); hy = max(GRID['xy_step_m'], GRID['xy_half_sigma']*sy)
        ht = max(GRID['yaw_step_rad'], GRID['yaw_half_sigma']*st)
        step_xy, step_t = GRID['xy_step_m'], GRID['yaw_step_rad']
        while (2*hx/step_xy+1)*(2*hy/step_xy+1)*(2*ht/step_t+1) > GRID['max_poses']:
            step_xy, step_t = step_xy*1.25, step_t*1.25      # coarser, same extent (grid size bound)
        gx = np.arange(-hx, hx+1e-9, step_xy); gy = np.arange(-hy, hy+1e-9, step_xy)
        gt = np.arange(-ht, ht+1e-9, step_t)
        D = np.stack(np.meshgrid(gx, gy, gt, indexing='ij'), -1).reshape(-1, 3)
        px = x0+D
        Pi = np.linalg.inv(P)
        logw = -.5*np.einsum('ni,ij,nj->n', D, Pi, D)
        like = np.ones(len(px))
        if len(walls):
            logw = logw+wall_loglik(self.field, px, walls, sigmas)
        if features:
            like = like*landmark_likelihood(self.mapped, px, features)
        logw = logw+np.log(np.maximum(like, 1e-300))
        w = np.exp(logw-logw.max()); w /= w.sum()
        mean_d = w@D; dd = D-mean_d
        cov = (w[:, None]*dd).T@dd+np.diag([step_xy**2/12]*2+[step_t**2/12])
        x_new = x0+mean_d; x_new[2] = wrap(x_new[2])
        rec['grid'] = {'poses': int(len(px)), 'steps': [step_xy, step_t], 'half_extent': [hx, hy, ht], 'effective_n': float(1/np.sum(w*w)),
                       'shift': [float(z) for z in mean_d]}
        if commit:
            self.own.x, self.own.P = x_new, cov
        return x_new, cov

    def seen_groups(self, walls, floors, doors):
        """Which mapped features the detections fall on, given the updated estimate (association report only)."""
        x, y, a = self.own.x; c, s = math.cos(a), math.sin(a); groups = set()
        for qx, qy in np.asarray(walls).reshape(-1, 2):
            wx, wy = x+c*qx-s*qy, y+s*qx+c*qy
            best = min(((abs((wx-l['xy'][0])*l['normal'][0]+(wy-l['xy'][1])*l['normal'][1])+
                         .2*max(0., math.dist((wx, wy), l['xy'])-SAMPLE_WALL_M), l['group'])
                        for l in self.landmarks if l['type'] == 'wall'), default=None)
            if best and best[0] < .10:
                groups.add(best[1])
        for f in floors:
            mx, my = np.mean(f['endpoints'], axis=0); wx, wy = x+c*mx-s*my, y+s*mx+c*my
            best = min(((math.dist((wx, wy), l['xy']), l['group']) for l in self.landmarks if l['type'] == 'zone_edge'), default=None)
            if best and best[0] < .4:
                groups.add(best[1])
        for f in doors:
            mx, my = f['center']; wx, wy = x+c*mx-s*my, y+s*mx+c*my
            best = min(((math.dist((wx, wy), l['xy']), l['group']) for l in self.landmarks if l['type'] == 'door'), default=None)
            if best and best[0] < .6:
                groups.add(best[1])
        return sorted(groups)

    def record(self):
        return {'option': self.mode, 'plan': self.plan, 'views': self.views, 'odometry_profile': self.profile, 'decision': self.decision,
                'localization_support': self.localization_support,
                'command_pose': self.command_own.x.tolist(),
                'map_pose_known': self.map_pose_known, 'pose_frame': 'map' if self.map_pose_known else 'arbitrary_command_start',
                'final_estimate': [float(z) for z in self.own.x],
                'final_sigma': [float(math.sqrt(self.own.P[i, i])) for i in range(3)],
                'constants': {'look_arm': self.arm, 'v2': V2 if self.v2 else None, 'view_settle_s': VIEW_SETTLE_S, 'arm_move_s': ARM_MOVE_S,
                              'yaw_rate_rad_s': YAW_RATE_RAD_S, **({'profile_yaw_rate_rad_s': _profile_yaw_rate(self.profile)} if self.profile == 'yaw_cal_v1' else {}), 'grid': GRID, 'wall_field': WALL_FIELD,
                              'sigmas': [SIGMA_WALL_M, SIGMA_EDGE_M, SIGMA_DOOR_M]},
                'own_image_gates_sha256': self.gates['sha256'],
                'scope': 'own commands, own RGB and static map only; truth error is in the caller evaluation record'}


# Wall base points: product-form likelihood field (Probabilistic Robotics Table 6.3; Nav2
# likelihood_field_prob), not the AMCL cubic accumulator (sigma 0.2 m, flat at cm scale:
# its max/min score ratio over a +-15 cm grid was < 1.1 in tests). sigma from the ground projection
# of the wall-base row at 1 m (about 8.5 mm/px at h 0.19 m, f 622 px) times a few px of edge error.
# Adjacent columns are correlated: each point's log-likelihood is tempered by WALL_TEMPER
# (about one independent point per 5 columns). DEV candidate, not tuned on outcomes.
WALL_FIELD = {'sigma_hit_m': .05, 'z_hit': .9, 'z_rand': .1, 'max_dist_m': 2., 'temper': .2}


def wall_loglik(field, px, points, sigmas=None):
    """sigmas: per-point measurement sigma (v2, range dependent); None = WALL_FIELD sigma_hit_m (v1)."""
    px = np.asarray(px, float); co, si = np.cos(px[:, 2]), np.sin(px[:, 2]); out = np.zeros(len(px))
    rand = WALL_FIELD['z_rand']/WALL_FIELD['max_dist_m']; pts = np.asarray(points, float).reshape(-1, 2)
    sig = np.full(len(pts), WALL_FIELD['sigma_hit_m']) if sigmas is None else np.asarray(sigmas, float)
    for (qx, qy), sg in zip(pts, sig):
        d = field.distances(np.column_stack((px[:, 0]+co*qx-si*qy, px[:, 1]+si*qx+co*qy)))
        norm = 1/(math.sqrt(2*math.pi)*sg)
        out += WALL_FIELD['temper']*np.log(WALL_FIELD['z_hit']*norm*np.exp(-.5*(d/sg)**2)+rand)
    return out


def _profile_yaw_rate(profile):
    from sim.visible_belief import rates
    return rates(profile)[2]


def rotate_plan(angle, odometry_profile='off'):
    """In-place rotation by own wheel pulses (mix t = (-w0+w1-w2+w3)/4), duty 0.35, pulses <= 0.15 s."""
    from sim.visible_belief import rates
    rates(odometry_profile)  # reject unknown profiles; preserve older planners
    if odometry_profile in ('yaw_cal_v1', 'lateral_rate_cal_v1'):
        rate = rates(odometry_profile)[2]  # release17: calibrated sign and ~3x magnitude
    else:
        rate = -YAW_RATE_RAD_S if odometry_profile == 'native_yaw_v1' else YAW_RATE_RAD_S
    level = WHEEL if angle/rate > 0 else -WHEEL
    remaining = abs(angle/rate); plan = []
    while remaining > 1e-6:
        on = min(.1, remaining); plan.append(([-level, level, -level, level], [min(PULSE_MAX_S, on)]*4)); remaining -= on
    if plan and plan[-1][1][0] < .04:
        # yaw_cal_v1: a tail under 20 ms is dropped (dead band, <= 0.021 rad); else one 40 ms pulse, never shorter
        plan[-1] = (plan[-1][0], [.04]*4) if odometry_profile not in ('yaw_cal_v1', 'lateral_rate_cal_v1') or plan[-1][1][0] >= .02 else None
        plan = [p for p in plan if p is not None]
    return plan


class ScriptRunner:
    """Executes one robot's look script on the simulation clock (same order, same timing every run)."""

    def __init__(self, steps, start):
        self.steps, self.i, self.t_step = list(steps), 0, None
        self.start = start; self.done = not self.steps; self.log = []; self.waiting_from = None; self.end = start if self.done else None

    def tick(self, now, *, set_servo, set_wheels, wheels_idle, capture):
        while not self.done:
            step = self.steps[self.i]
            if self.t_step is None:
                self.t_step = now; self.waiting_from = None if step.get('wheels') else now
                if step.get('servo'):
                    set_servo(step['servo'], now)
                if step.get('wheels'):
                    set_wheels(list(step['wheels']), now)
                self.log.append({'label': step['label'], 't': float(now)})
                return
            if step.get('wheels') and not wheels_idle():
                return
            if self.waiting_from is None:
                self.waiting_from = now
            if now-self.waiting_from < step['wait']-1e-9:
                return
            if step.get('capture'):
                capture(now)
            self.i += 1; self.t_step = None
            if self.i >= len(self.steps):
                self.done = True; self.end = now
