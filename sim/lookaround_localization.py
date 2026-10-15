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
LOOK_ARM = {3: 896, 4: 2035, 5: 1894}      # harness/zone_pair_highpose.HIGH arm joints: camera sees walls (column model domain)
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


def look_servo(pan_deg):
    return {1: GRIPPER_OPEN, **LOOK_ARM, 6: pan_pulse(pan_deg)}


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


def visible_fn_for(static, camera, *, margin_px=IMAGE_MARGIN_PX):
    rects = wall_rects(static)

    def visible(pose, body_yaw_deg, pan_deg, lm):
        cam, _ = camera.pose(look_servo(pan_deg))
        if cam is None:
            return False
        origin, rot = cam
        yaw = pose[2]+math.radians(body_yaw_deg); c, s = math.cos(yaw), math.sin(yaw)
        cw = (pose[0]+c*origin[0]-s*origin[1], pose[1]+s*origin[0]+c*origin[1])
        lx, ly = lm['xy']
        if math.dist(cw, (lx, ly)) > lm['range']:
            return False
        if not lm.get('two_sided') and (cw[0]-lx)*lm['normal'][0]+(cw[1]-ly)*lm['normal'][1] <= 0:
            return False
        dx, dy = lx-pose[0], ly-pose[1]
        body = np.array([c*dx+s*dy, -s*dx+c*dy, 0.])
        q = rot.T@(body-origin)
        if q[2] <= .05:
            return False
        u, v = (camera.K@q)[:2]/q[2]
        if not (margin_px <= u <= WIDTH-margin_px and margin_px <= v <= HEIGHT-margin_px):
            return False
        L = math.dist(cw, (lx, ly)); back = ((lx-cw[0])/L, (ly-cw[1])/L)
        end = (lx-.03*back[0], ly-.03*back[1])            # stop short of the landmark's own wall face
        return not any(_segment_hits_rect(cw, end, r) for r in rects)
    return visible


class LookaroundLocalizer:
    """One robot's own-pose estimate, look plan and image updates (no simulator input)."""

    def __init__(self, static, estimate, *, sigma_xy=.05, sigma_yaw=math.radians(2.), odometry_profile='off'):
        from harness import vision_loc_protocol as vp
        from harness import zone_pair_highpose_contract as contract
        from harness.zone_solo_cyan_likelihood_field import Field
        from harness.zone_solo_cyan_landmarks import MapFeatures
        self.static = static
        self.own = OwnPose(estimate, sigma_xy, sigma_yaw)
        self.profile = odometry_profile
        self.camera = Camera()
        self.landmarks = map_landmarks(static)
        self.visible = visible_fn_for(static, self.camera)
        self.vl = vp.load_vis3()[0]
        self.gates = contract.own_image_gates()
        self.field = Field(static); self.mapped = MapFeatures(static)
        self.views, self.plan = [], None
        self.require_fix_acceptance = False  # opt-in carry; legacy byte output unchanged

    # --- own motion ---
    def propagate(self, wheels, seconds):
        from sim.visible_belief import odometry
        if seconds > 0 and any(wheels):
            self.own.propagate(*odometry(wheels, seconds, self.profile))

    # --- view plan ---
    def make_plan(self, start_pan_pulse=1500):
        start = (start_pan_pulse-1500)*PAN_DEG_PER_PULSE
        if getattr(self, 'rank_aware_v1', False):
            from sim.solo_carry6 import rank_aware_plan, MARGIN_PX
            plan = rank_aware_plan(tuple(self.own.x), self.planning_covariance, self.landmarks,
                visible_fn_for(self.static, self.camera, margin_px=MARGIN_PX), start_pan=start,
                retry=getattr(self, 'rank_retry', 0))
        else:
            plan = plan_views(tuple(self.own.x), getattr(self, 'planning_covariance', self.own.P),
                          self.landmarks, self.visible, start_pan=start,
                          **({'body_yaws': (0.,)} if getattr(self, 'pan_only', False) else {}))
        self.plan = {'expected_gain_nats': plan['expected_gain_nats'], 'rotated': plan['rotated'],
                     'expected_landmarks': plan['expected_landmarks'],
                     'views': [{'body_yaw_deg': v['body_yaw_deg'], 'pan_deg': v['pan_deg'], 'pan_pulse': pan_pulse(v['pan_deg']),
                                'expected': v['landmarks']} for v in plan['views']],
                     'pose_estimate_at_plan': [float(z) for z in self.own.x],
                     'sigma_at_plan': [float(math.sqrt(self.own.P[i, i])) for i in range(3)]}
        if 'rank_aware' in plan:
            self.plan['rank_aware'] = plan['rank_aware']
        return self.plan

    def script(self):
        """Fixed-timing command script for the plan: arm to look pose, (rotate), views, (rotate back)."""
        steps = []; yaw_now = 0.
        views = self.plan['views'] if self.plan else []
        first = views[0]['pan_pulse'] if views else 1500
        steps.append({'servo': look_servo((first-1500)*PAN_DEG_PER_PULSE), 'wait': ARM_MOVE_S, 'capture': False, 'label': 'arm_to_look'})
        for v in views:
            if v['body_yaw_deg'] != yaw_now:
                steps.append({'wheels': rotate_plan(math.radians(v['body_yaw_deg']-yaw_now)), 'wait': .3, 'capture': False,
                              'label': f"rotate_{v['body_yaw_deg']:+.0f}"})
                yaw_now = v['body_yaw_deg']
            steps.append({'servo': look_servo(v['pan_deg']), 'wait': VIEW_SETTLE_S, 'capture': True,
                          'label': f"view_{v['body_yaw_deg']:+.0f}_{v['pan_deg']:+.0f}"})
        if yaw_now:
            steps.append({'wheels': rotate_plan(math.radians(-yaw_now)), 'wait': .3, 'capture': False, 'label': 'rotate_back'})
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
        if len(walls)+len(floors)+len(doors):
            prior, covariance = self.own.x.copy(), self.own.P.copy()
            self._grid_update(walls, floors+doors, rec)
            if self.require_fix_acceptance:
                rec['fix_acceptance'] = self.fix_acceptance(walls, floors, doors, prior, covariance)
                if not rec['fix_acceptance']['accepted']:
                    partial = None
                    if getattr(self, 'rank_aware_v1', False):
                        from sim.solo_carry6 import partial_posterior
                        partial = partial_posterior(prior, covariance, self.own.x, self.own.P,
                                                    self._acceptance_rows, rec['fix_acceptance'])
                    self.own.x, self.own.P = prior, covariance
                    if partial is not None:
                        self.own.x, self.own.P, rec['partial_update'] = partial
        rec['posterior'] = [float(z) for z in self.own.x]
        rec['posterior_sigma'] = [float(math.sqrt(self.own.P[i, i])) for i in range(3)]
        rec['seen_groups'] = self.seen_groups(walls, floors, doors)
        self.views.append(rec)
        return rec

    def fix_acceptance(self, walls, floors, doors, prior, covariance):
        """Gate a proposed grid posterior using the existing map feature models.

        A grid is a computation, not evidence. Reuse the localizer's wall/zone/
        door residuals and OwnPose's 99% scalar chi-square gate. Require at least
        two independent feature groups and full pose rank; a lone wall cannot
        renew a complete SE(2) fix. Caller rolls back a rejected posterior.
        """
        from sim.active_lookaround import GATE_CHI2_1, MIN_GAIN
        from harness.zone_solo_cyan_landmarks import PARAMS
        x, y, a = self.own.x; c, s = math.cos(a), math.sin(a)
        rot = np.array([[c, -s], [s, c]])
        rows, errors, groups = [], [], set()

        def line_row(point, normal):
            q = rot @ np.asarray(point)
            return [*normal, float(np.asarray(normal) @ [-q[1], q[0]])]

        for q in np.asarray(walls).reshape(-1, 2):
            world = np.array([x, y])+rot@q
            matches = [(abs((world-np.asarray(l['xy']))@l['normal'])+
                        .2*max(0., math.dist(world, l['xy'])-SAMPLE_WALL_M), i)
                       for i, l in enumerate(self.landmarks) if l['type'] == 'wall']
            if not matches:
                errors.append(math.inf); continue
            distance, i = min(matches); lm = self.landmarks[i]
            error = (distance/SIGMA_WALL_M)**2; errors.append(error)
            if error <= GATE_CHI2_1:
                rows.append(line_row(q, lm['normal'])); groups.add(lm['group'])
        for f in floors:
            points = np.asarray(f['endpoints']); world = np.array([x, y])+points@rot.T
            angle = a+math.atan2(f['normal'][1], f['normal'][0])
            matches = []
            for i, edge in enumerate(self.mapped.edges):
                hd = abs(edge['hue']-f['hue'])
                if min(hd, 180-hd) > PARAMS['hue_tolerance']:
                    continue
                vec = edge['b']-edge['a']
                u = np.clip((world-edge['a'])@vec/(vec@vec), 0., 1.)
                distance = float(np.sqrt(np.mean(np.sum((world-edge['a']-u[:, None]*vec)**2, axis=1))))
                da = wrap(angle-math.atan2(edge['normal'][1], edge['normal'][0]))
                e = [(distance/PARAMS['sigma_line_m'])**2, (da/PARAMS['sigma_line_angle_rad'])**2]
                matches.append((sum(e), i, e))
            if not matches:
                errors.append(math.inf); continue
            _, i, e = min(matches); edge = self.mapped.edges[i]; errors.extend(e)
            if max(e) <= GATE_CHI2_1:
                rows.extend([line_row(points.mean(0), edge['normal']), [0., 0., 1.]])
                groups.add('floor:'+str(i))
        for f in doors:
            q = np.asarray(f['center']); world = np.array([x, y])+rot@q
            matches = [(math.dist(world, d['center']), i) for i, d in enumerate(self.mapped.doors)]
            if not matches:
                errors.append(math.inf); continue
            distance, i = min(matches)
            e = [(distance/PARAMS['sigma_range_m'])**2,
                 ((f['width']-self.mapped.doors[i]['width'])/PARAMS['sigma_width_m'])**2]
            errors.extend(e)
            if max(e) <= GATE_CHI2_1:
                rows.extend([line_row(q, (1., 0.)), line_row(q, (0., 1.))]); groups.add('door:'+str(i))
        shift = self.own.x-prior; shift[2] = wrap(shift[2])
        finite = bool(np.isfinite(self.own.x).all() and np.isfinite(self.own.P).all())
        chi2 = float(shift @ np.linalg.solve(covariance+self.own.P, shift)) if finite else math.inf
        gain = float(np.linalg.slogdet(covariance)[1]-np.linalg.slogdet(self.own.P)[1]) if finite else -math.inf
        rank = int(np.linalg.matrix_rank(np.asarray(rows))) if rows else 0
        if getattr(self, 'rank_aware_v1', False):
            self._acceptance_rows = rows
        fraction = sum(e <= GATE_CHI2_1 for e in errors)/max(1, len(errors))
        accepted = (finite and len(errors) >= 3 and len(groups) >= 2 and rank == 3
                    and fraction >= .8 and chi2 <= 11.345 and gain >= MIN_GAIN)
        return {'accepted': bool(accepted), 'residual_count': len(errors), 'inlier_fraction': fraction,
                'groups': sorted(groups), 'pose_rank': rank, 'innovation_chi2': chi2,
                'innovation_chi2_limit': 11.345, 'residual_chi2_limit': GATE_CHI2_1,
                'information_gain': gain, 'minimum_information_gain': MIN_GAIN}

    def _grid_update(self, walls, features, rec):
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
            logw = logw+wall_loglik(self.field, px, walls)
        if features:
            like = like*landmark_likelihood(self.mapped, px, features)
        logw = logw+np.log(np.maximum(like, 1e-300))
        w = np.exp(logw-logw.max()); w /= w.sum()
        mean_d = w@D; dd = D-mean_d
        cov = (w[:, None]*dd).T@dd+np.diag([step_xy**2/12]*2+[step_t**2/12])
        self.own.x = x0+mean_d; self.own.x[2] = wrap(self.own.x[2]); self.own.P = cov
        rec['grid'] = {'poses': int(len(px)), 'steps': [step_xy, step_t], 'half_extent': [hx, hy, ht], 'effective_n': float(1/np.sum(w*w)),
                       'shift': [float(z) for z in mean_d]}

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
        return {'option': OPTION, 'plan': self.plan, 'views': self.views, 'odometry_profile': self.profile,
                'final_estimate': [float(z) for z in self.own.x],
                'final_sigma': [float(math.sqrt(self.own.P[i, i])) for i in range(3)],
                'constants': {'look_arm': LOOK_ARM, 'view_settle_s': VIEW_SETTLE_S, 'arm_move_s': ARM_MOVE_S,
                              'yaw_rate_rad_s': YAW_RATE_RAD_S, 'grid': GRID, 'wall_field': WALL_FIELD,
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


def wall_loglik(field, px, points):
    px = np.asarray(px, float); co, si = np.cos(px[:, 2]), np.sin(px[:, 2]); out = np.zeros(len(px))
    norm = 1/(math.sqrt(2*math.pi)*WALL_FIELD['sigma_hit_m']); rand = WALL_FIELD['z_rand']/WALL_FIELD['max_dist_m']
    for qx, qy in np.asarray(points, float).reshape(-1, 2):
        d = field.distances(np.column_stack((px[:, 0]+co*qx-si*qy, px[:, 1]+si*qx+co*qy)))
        out += WALL_FIELD['temper']*np.log(WALL_FIELD['z_hit']*norm*np.exp(-.5*(d/WALL_FIELD['sigma_hit_m'])**2)+rand)
    return out


def rotate_plan(angle):
    """In-place rotation by own wheel pulses (mix t = (-w0+w1-w2+w3)/4), duty 0.35, pulses <= 0.15 s."""
    level = WHEEL if angle > 0 else -WHEEL
    remaining = abs(angle)/YAW_RATE_RAD_S; plan = []
    while remaining > 1e-6:
        on = min(.1, remaining); plan.append(([-level, level, -level, level], [min(PULSE_MAX_S, on)]*4)); remaining -= on
    if plan and plan[-1][1][0] < .04:
        plan[-1] = (plan[-1][0], [.04]*4)
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
