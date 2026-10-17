"""Default-off known-map AMCL, own RGB/issued commands only.

No evaluation, spawn or simulator dependencies. Own observations remain a
separate causal local map; the sensor model reads authored static walls only.
"""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt
from harness.mapbuild_amcl_vendor import algorithms as nav2
from harness.e2e_rgb_vo import compose

OPTION = 'selfmap_map_correction_v1'
METHOD = 'static_amcl_v1'


class StaticField:
    """Nav2 occupancy-cell distance field; UGRP authored rectangle adapter.

    Resolution .01m and max distance 2m are unchanged existing AMCL ports.
    Free cell list is the ENTIRE authored bounds minus authored wall interiors.
    """
    def __init__(self, static_map, *, full_wall_extent=False):
        self.res = .01
        x0, x1, y0, y1 = static_map['bounds_m']
        self.origin = np.array([x0, y0], float)
        nx, ny = int(math.ceil((x1-x0)/self.res))+1, int(math.ceil((y1-y0)/self.res))+1
        iy, ix = np.indices((ny, nx))
        x, y = x0+ix*self.res, y0+iy*self.res
        occupied = np.zeros((ny, nx), bool)
        for o in static_map['obstacles']:
            if 'wall' not in o['id']:
                continue
            cx, cy = o['center_m']; hx, hy = o['half_extents_m']
            c, s = math.cos(o.get('yaw_rad', 0)), math.sin(o.get('yaw_rad', 0))
            dx, dy = x-cx, y-cy
            occupied |= (abs(c*dx+s*dy)<=hx+1e-12)&(abs(-s*dx+c*dy)<=hy+1e-12)
        if not occupied.any():
            raise ValueError('STATIC_WALLS_REQUIRED')
        self.dist = np.minimum(2., distance_transform_edt(~occupied)*self.res)
        inside = (x>x0)&(x<x1)&(y>y0)&(y<y1)&~occupied
        self.free = np.column_stack((x[inside], y[inside]))
        if not len(self.free):
            raise ValueError('STATIC_FREE_SPACE_REQUIRED')
        if full_wall_extent:
            # Authored bounds are NAVIGATION limits passing through the outer
            # wall centres, not a complete occupancy-grid extent. Build the
            # same truncated Euclidean field over ALL authored wall rectangles
            # plus the existing Nav2 max_occ_dist=2m support. This is a map
            # adapter correction, not a new likelihood/matcher or GT fit.
            # Keep the original free list byte-identical: padded cells never
            # become allowed poses and paired RNG proposals remain identical.
            vertices=[]
            for o in static_map['obstacles']:
                if 'wall' not in o['id']:continue
                hx,hy=o['half_extents_m'];c,s=math.cos(o.get('yaw_rad',0)),math.sin(o.get('yaw_rad',0))
                R=np.array([[c,-s],[s,c]])
                vertices.extend(np.array([[-hx,-hy],[hx,-hy],[hx,hy],[-hx,hy]])@R.T+o['center_m'])
            vertices=np.asarray(vertices)
            lower=self.origin-np.ceil(np.maximum(0,self.origin-vertices.min(0)+2.)/self.res)*self.res
            upper=np.array([x1,y1])+np.ceil(np.maximum(0,vertices.max(0)+2.-[x1,y1])/self.res)*self.res
            nx,ny=np.rint((upper-lower)/self.res).astype(int)+1
            iy,ix=np.indices((ny,nx));x,y=lower[0]+ix*self.res,lower[1]+iy*self.res
            occupied=np.zeros((ny,nx),bool)
            for o in static_map['obstacles']:
                if 'wall' not in o['id']:continue
                cx,cy=o['center_m'];hx,hy=o['half_extents_m'];c,s=math.cos(o.get('yaw_rad',0)),math.sin(o.get('yaw_rad',0))
                dx,dy=x-cx,y-cy
                occupied|=(abs(c*dx+s*dy)<=hx+1e-12)&(abs(-s*dx+c*dy)<=hy+1e-12)
            self.origin=lower;self.dist=np.minimum(2.,distance_transform_edt(~occupied)*self.res)

    def distances(self, points):
        ij = np.floor((np.asarray(points)-self.origin)/self.res+.5).astype(int)
        x, y = ij[..., 0], ij[..., 1]
        ok = (x>=0)&(y>=0)&(x<self.dist.shape[1])&(y<self.dist.shape[0])
        out = np.full(x.shape, 2.)
        out[ok] = self.dist[y[ok], x[ok]]
        return out


class StaticAMCL:
    def __init__(self, static_map, calibration, requirements, *, option='off', method=METHOD, seed=20261017, profile='calibrated_kld_v1', initial_prior_option='off', initial_prior=None):
        if option not in ('off', OPTION) or method != METHOD:
            raise ValueError('UNKNOWN_AMCL_OPTION')
        if calibration.get('truth_inputs') != 0:
            raise ValueError('OWN_CALIBRATION_REQUIRED')
        nav2_profiles=('nav2_defaults_v1','nav2_rgb_field_v1')
        if profile not in ('calibrated_kld_v1','fixed_population_v1','nav2_sigma_fixed_v1','likelihood_product_v1',*nav2_profiles):
            raise ValueError('UNKNOWN_AMCL_PROFILE')
        if initial_prior_option not in ('off', 'start_zone_prior_v1'):
            raise ValueError('UNKNOWN_INITIAL_PRIOR_OPTION')
        if initial_prior_option == 'off' and initial_prior is not None:
            raise ValueError('EXPLICIT_START_ZONE_TOGGLE_REQUIRED')
        if initial_prior_option != 'off' and (initial_prior is None or profile not in nav2_profiles):
            raise ValueError('COARSE_START_ZONE_AND_NAV2_DEFAULTS_REQUIRED')
        self.initial_prior_option = initial_prior_option
        self.start_zone_id = initial_prior.get('zone_id') if isinstance(initial_prior, dict) else None
        self.profile=profile
        # Controlled standard settings, not a new matcher: min=max=100000
        # is Nav2's fixed-population MCL setting. .2m is its documented sigma.
        self.minimum_particles=2000 if profile=='calibrated_kld_v1' else 100000
        self.maximum_particles=100000
        # Nav2 official configuring_amcl: min/max=500/2000, sigma=.2,
        # recovery alpha slow/fast=0/0. This new explicit profile leaves
        # historical settings unchanged; no GT fitting or beam cap
        # invented here. Upstream cubic sum can use 96 beams on 96 slots.
        # https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/
        if profile in nav2_profiles:
            self.minimum_particles, self.maximum_particles = 500, 2000
        self.alpha_slow, self.alpha_fast = ((0., 0.) if profile in nav2_profiles else (.001, .1))
        self.option = option; self.method = method
        self.field = StaticField(static_map,full_wall_extent=profile=='nav2_rgb_field_v1'); self.rng = np.random.default_rng(seed)
        self.alphas = np.asarray(calibration['alphas'], float)
        if self.alphas.shape != (4,) or not np.isfinite(self.alphas).all() or (self.alphas<0).any():
            raise ValueError('INVALID_MOTION_ALPHAS')
        # 20.2 mm: maximum P95 of the four prior scan diagnostics, treated as
        # sigma directly (not fitted to these replays). It is NOT a confidence
        # bound or proof of sensor Gaussianity. The prior diagnostic used GT
        # only to measure scan error, not to fit motion or initialize poses.
        self.sigma_hit = .2 if profile in ('nav2_sigma_fixed_v1', *nav2_profiles) else .0202
        # Existing virtual_scan rejects source ranges >=4m. Nav2's node uses
        # this sensor limit in z_rand/range_max, not the configured ceiling100.
        self.range_max=4. if profile=='nav2_rgb_field_v1' else 100.
        self.requirements = requirements
        if initial_prior_option != 'off':
            from harness.mapbuild_start_zone import sample
            initial = sample(self.field, static_map, initial_prior, self.rng, self.maximum_particles)
            self.particles = initial if option != 'off' else None
        else:
            self.particles = self.uniform_free(self.maximum_particles) if option != 'off' else None
        self.weights = np.ones(len(self.particles))/len(self.particles) if self.particles is not None else None
        self.odom = np.zeros(3); self.sensor_odom = np.zeros(3)
        self.slow = self.fast = 0.; self.last_t = None; self.updated = False
        self.local_map = []; self.ledger = []; self.last_map_t = -math.inf
        self.last_servo = None; self.current = None

    def uniform_free(self, n):
        xy = self.field.free[self.rng.integers(len(self.field.free), size=n)]
        return np.column_stack((xy, self.rng.uniform(-math.pi, math.pi, n)))

    def belief(self):
        p, w = self.particles, self.weights
        xy = w@p[:, :2]
        c, s = float(w@np.cos(p[:, 2])), float(w@np.sin(p[:, 2]))
        yaw = math.atan2(s, c)
        dyaw = nav2.wrap(p[:, 2]-yaw)
        delta = np.column_stack((p[:, :2]-xy, dyaw))
        cov = (w[:, None]*delta).T@delta
        # Navigation readiness uses the FROZEN handoff budget, not arbitrary
        # AMCL cluster constants. 95% convention is inherited requirements P95;
        # report global weighted quantiles (not just a winning cluster).
        def quantile(v):
            order = np.argsort(v, kind='stable')
            return float(v[order[min(np.searchsorted(np.cumsum(w[order]), .95), len(v)-1)]])
        radius = np.linalg.norm(delta[:, :2], axis=1)
        xy95 = quantile(radius); yaw95 = quantile(abs(dyaw))
        req = self.requirements['handoff']
        coupled = yaw95+math.atan2(xy95, req['nominal_target_range_m']-xy95)
        ess = float(1/np.sum(w*w))
        # ESS>=N/2 is ROS selective resampling's published criterion. Even a
        # compact wrong mode can pass: independent evaluator must count it.
        ready = bool(xy95<=req['position_error_m'] and coupled<=req['yaw_error_rad'] and ess>=len(w)/2)
        return dict(candidate_pose=[float(xy[0]), float(xy[1]), yaw], covariance=cov.tolist(),
            xy_p95_m=xy95, yaw_p95_rad=yaw95, direction_coupled_p95_rad=coupled,
            ess=ess, samples=len(w), converged=ready, ready_for_handoff=False,
            runtime_qualified=False,
            circular_resultant=math.hypot(c, s))

    def step(self, t, frame_id, delta, scan, *, servo=None):
        if self.last_t is not None and t<=self.last_t:
            raise ValueError('NONCAUSAL_FRAME')
        self.last_t = t
        self.odom = compose(self.odom, delta)
        segments = np.asarray(scan.get('segments', []), float).reshape(-1, 2, 2)
        # Keep own mapping independent from static likelihood. No scan-to-own-
        # map correction, neither before nor after convergence in this mode.
        if len(segments) and t-self.last_map_t>=1.-1e-8:
            self.local_map.append(dict(t=t, frame_id=frame_id, own_odom_pose=self.odom.tolist(),
                local_segments=segments.tolist(), static_pose_if_converged=None))
            self.last_map_t=t
        row = dict(t=t, frame_id=frame_id, reason='no_visible_wall', category='static_amcl',
            blocked_object='own_observed_wall', minimum_gap_m=None, gap_status='not_measured',
            attempted=False, converged=False, ready_for_handoff=False, adopted_pose=None,
            method=self.method, profile=self.profile, truth_inputs=0, top_inputs=0, held_world_reads=0,
            work=dict(particles=0, point_checks=0, wall_seconds_used_as_gate=0))
        if self.option == 'off':
            row['reason']='off'; self.ledger.append(row); return row
        from harness.e2e_rgb_vo import between
        accumulated = between(self.sensor_odom, self.odom)
        # Exact Nav2 motion gate .25m/.2rad; new commanded camera pose is a
        # genuinely different sensor view. No repeated 10Hz static-image votes.
        key = tuple(sorted(servo.items())) if servo else None
        moved = np.any(abs(accumulated[:2])>.25) or abs(accumulated[2])>.2
        new_view = key != self.last_servo
        if not len(segments):
            self.ledger.append(row); return row
        if self.updated and not moved and not new_view:
            row['reason']='nav2_motion_gate'; self.ledger.append(row); return row
        nav2.motion(self.particles, accumulated, self.alphas, self.rng)
        self.sensor_odom = self.odom.copy(); self.last_servo=key; self.updated=True
        # One endpoint per actually returned bearing; zero invented max range.
        camera = np.asarray(scan.get('camera') or [0., 0.])
        columns = scan.get('columns', [])
        # Nav2 strides the ORIGINAL scan slots, then skips NaNs. Packing valid
        # RGB returns first changes which bearings the probability model uses.
        points = np.array([camera+v['range_m']*np.array([math.cos(v['bearing_rad']), math.sin(v['bearing_rad'])])
            if v.get('status')=='hit' and v.get('range_m') is not None else [np.nan,np.nan]
            for v in columns], float).reshape(-1, 2)
        if not columns:
            # Generic adapter (e.g. saved segment-only source): segment ends
            # already observed. No interpolation between separated detections.
            points = np.unique(segments.reshape(-1, 2), axis=0)
        sensor=nav2.likelihood_product if self.profile=='likelihood_product_v1' else nav2.likelihood
        values = sensor(self.field, self.particles, points, self.sigma_hit,
            **({'range_max':self.range_max} if self.profile=='nav2_rgb_field_v1' else {}))
        total = float(self.weights@values); avg = total/len(self.weights)
        self.weights *= values; self.weights /= total
        # Published augmented-MCL defaults in existing UGRP port, .001/.1.
        self.slow = avg if self.slow==0 else self.slow+self.alpha_slow*(avg-self.slow)
        self.fast = avg if self.fast==0 else self.fast+self.alpha_fast*(avg-self.fast)
        injection = max(0., 1-self.fast/self.slow) if self.slow>0 else 0.
        ess = float(1/np.sum(self.weights*self.weights))
        row.update(attempted=True, reason='posterior_unresolved', pre_resample_ess=ess,
            recovery_probability=injection, work=dict(particles=len(self.particles),
                point_checks=len(self.particles)*int(np.isfinite(points[::max(1,math.ceil(len(points)/60) if self.profile=='likelihood_product_v1' else (len(points)-1)//59)]).all(axis=1).sum()), wall_seconds_used_as_gate=0))
        # Standard adaptive resampling each sensor update, Nav2 interval=1.
        self.particles, stats = nav2.resample(self.particles, self.weights, self.rng,
            self.uniform_free, injection, minimum=self.minimum_particles, maximum=self.maximum_particles)
        self.weights = np.ones(len(self.particles))/len(self.particles)
        if injection>0:
            self.slow=self.fast=0.
        row['resample']=stats
        self.current = self.belief()
        # Post-resample equal weights cannot establish effective sample size:
        # use the measured posterior BEFORE resampling for the ESS gate.
        self.current['post_resample_ess']=self.current['ess']
        self.current['ess']=ess
        self.current['converged']=bool(self.current['converged'] and ess>=row['work']['particles']/2)
        self.current['ready_for_handoff']=False  # all offline profiles failed; no live admission
        row.update(self.current)
        if row['converged']:
            row['reason']='posterior_converged_unqualified'
            # Narrow belief alone produced a 4.69m false convergence in R3.
            # Keep it a diagnostic proposal until a future offline/actual-route
            # admission exists; this failed method supplies NO adopted pose.
            row['proposal_pose']=row['candidate_pose']
        self.ledger.append(row)
        return row
