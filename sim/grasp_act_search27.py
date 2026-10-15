"""Default-off command-feasible teacher planning and exact dependency certificates.

Visible/issued inputs only. MoveIt FixStartStateCollision separates invalid start;
Nav2 uses the real footprint; OMPL LazyPRM separates graph and edge validity.
We issue checked escape pulses instead of perturbing the robot's coordinates.
See experiments/2026-10-14-e2e18-grasp-rootcause/search27.md for evidence.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import time

import numpy as np

MODES = {'search_command_feasible': 'search_command_feasible_v1',
         'search_dependency_cache': 'search_dependency_cache_v1',
         'search_view_evidence': 'search_view_evidence_v1',
         'search27_frame': 'search27_frame_v1'}
# Reuse search20's bounded cache capacity; not an acceptance/safety threshold.
CACHE_SIZE = 4096


def enabled(t, key='search_command_feasible'):
    return t.search15_modes.get(key, 'off') != 'off'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=dict).encode()).hexdigest()


def stats(t, stage):
    if not hasattr(t, 'search27_stats'):
        t.search27_stats = {}
    return t.search27_stats.setdefault(stage, {'calls': 0, 'cache_hits': 0, 'computed': 0,
                                              'wall_s': 0., 'cpu_s': 0.})


def memo(t, stage, dependency, query, compute):
    """Exact dependencies, no rounding/TTL/bounded-motion approximation.

    Positive certificates depend on ALL obstacles, so an added obstacle cannot
    reuse a stale positive. Negative certificates conservatively do so too.
    Observation generations explicitly reopen validity after new measurements.
    Callers charge the same logical budget before both warm/cold lookups.
    """
    if not enabled(t, 'search_dependency_cache'):
        return compute()
    t.search27_stage=stage
    s = stats(t, stage); s['calls'] += 1
    if not hasattr(t, 'search27_cache'):
        t.search27_cache = OrderedDict()
    cache = t.search27_cache
    key = (stage, dependency, query)
    if key in cache:
        s['cache_hits'] += 1; cache.move_to_end(key)
        return deepcopy(cache[key])
    wall, cpu = time.perf_counter(), time.process_time()
    value = compute()  # Exceptions/incomplete stages are NEVER certificates.
    s['computed'] += 1
    s['wall_s'] += time.perf_counter()-wall; s['cpu_s'] += time.process_time()-cpu
    cache[key] = deepcopy(value)
    if len(cache) > CACHE_SIZE:
        cache.popitem(last=False)
    return value


def dependencies(nav, *, connector=False):
    obs = nav.world['visibility'][nav.rid].get('observations', {})
    data = {'discs': nav.discs, 'rects': nav.rects, 'bounds': nav.bounds,
            'target':nav.target,'issued_pose':list(nav.pose),
            'hard': __import__('sim.grasp_act_search25', fromlist=['hard_margins']).hard_margins(nav),
            'soft': [d['margin_m'] for d in nav.audit_details], 'fresh_target': nav.fresh_target,
            'generations': {k: m.get('seen_t') for k, m in obs.items()}}
    if connector:
        # Arm/view checks read heights, beam reconstruction, PWM and current
        # admission. Only absolute t is excluded; freshness remains explicit.
        data.update(objects=nav.world['objects'], robots=nav.world['robots'],
                    beam=nav.world['beam'], end=nav.end, pwm=nav.pwm,
                    observations=obs,
                    visible_probes=nav.world['visibility'][nav.rid].get('visible_probes'),
                    target_fresh=bool(obs.get('band_'+nav.end, {}).get('seen_t', -math.inf)
                                      >= nav.world['t']-1e-8))
    return digest(data)


def optical_pixel(q):
    """Use the authored asymmetric K-pinhole frame, without a fitted reserve.

    Intrinsics are measured camera-profile values, NOT a new FOV constant.
    GCP renderer parity must be recorded before enabling this candidate.
    """
    from sim.masterpi_camera_profile import CAMERA_FX_PX, CAMERA_FY_PX, CAMERA_CX_PX, CAMERA_CY_PX
    if q[2] <= 0:
        return None
    return (CAMERA_CX_PX+CAMERA_FX_PX*q[0]/q[2],
            CAMERA_CY_PX+CAMERA_FY_PX*q[1]/q[2])


def frame_pixels(q):
    from sim.masterpi_camera_profile import (CAMERA_FX_PX, CAMERA_FY_PX, CAMERA_CX_PX,
        CAMERA_CY_PX, CAMERA_FISHEYE_D)
    pinhole=optical_pixel(q)
    if pinhole is None:return None
    x,y=q[0]/q[2],q[1]/q[2];r=math.hypot(x,y);theta=math.atan(r)
    theta2=theta*theta
    radial=theta*(1+sum(k*theta2**(i+1) for i,k in enumerate(CAMERA_FISHEYE_D)))
    scale=radial/r if r else 1.
    return pinhole,(CAMERA_CX_PX+CAMERA_FX_PX*x*scale,CAMERA_CY_PX+CAMERA_FY_PX*y*scale)


def frame_clearance(q):
    from sim.masterpi_camera_profile import CAMERA_NATIVE_WIDTH as W, CAMERA_NATIVE_HEIGHT as H
    pixels=frame_pixels(q)
    if pixels is None:return float(q[2])
    return min(min(x,W-x,y,H-y) for x,y in pixels)


def in_frame(q):
    from sim.masterpi_camera_profile import CAMERA_NATIVE_WIDTH as W, CAMERA_NATIVE_HEIGHT as H
    pixels=frame_pixels(q)
    return pixels is not None and all(0<=x<W and 0<=y<H for x,y in pixels)


def provenance(nav):
    vis = nav.world['visibility'][nav.rid]
    m = vis.get('observations', {}).get('band_'+nav.end)
    return {'snapshot_id': digest(nav.world), 't': nav.world['t'],
            'issued_pose': list(nav.pose), 'issued_pwm': dict(nav.pwm),
            'rgb': vis.get('own_rgb'),
            'admitted_band': deepcopy(m), 'visible_probes': vis.get('visible_probes'),
            'body_discs': list(nav.discs), 'body_rects': list(nav.rects)}


def event(t, now, name, reason, audit=(), **fields):
    rows = [d for a in audit for d in a.get('blockers', [a]) if d.get('gap_m') is not None]
    nearest = min(rows, key=lambda d: d['gap_m']) if rows else None
    t.search20_log.append({'t': now, 'event': name, 'reason': reason,
        'category': 'start_geometry' if name.startswith('start_') else 'command_feasibility',
        'blocked_object': nearest['id'] if nearest else 'none:'+reason,
        'min_gap_m': nearest['gap_m'] if nearest else None,
        'gap_scope': 'visible body/arm signed clearance' if nearest else 'not applicable: '+reason,
        'checks': list(audit), **fields})


def start_state(t, world, before):
    """Exactly once per tick, outside every IRM/candidate loop."""
    from sim.grasp_act_search23 import BodyNavigation
    from sim.grasp_act_pregrasp import issued_sweep_reason
    nav = BodyNavigation(t, world)
    gaps, slack = nav.measure([nav.pose[:2]], nav.pose[2])
    audit = list(nav.last_blockers)
    arm = []
    reason = issued_sweep_reason(world, t.rid, nav.pose, before, before, (0., 0., 0.), audit=arm)
    bad = bool((slack < 0).any()) or reason is not None
    snap = provenance(nav)
    snap.update(min_gap_m=float(gaps.min()), body_invalid=bool((slack < 0).any()), arm_reason=reason)
    previous = getattr(t, 'search27_previous', None)
    if bad and not getattr(t, 'search27_invalid', False):
        event(t, world['t'], 'start_geometry_invalid', 'start_geometry_invalid', [*audit, *arm],
              previous=previous, current=snap,
              actual_next_observation=deepcopy(snap['admitted_band']),
              last_safe_command=deepcopy(getattr(t, 'search27_last_safe', None)),
              pose_changed=previous is not None and previous['issued_pose'] != snap['issued_pose'],
              observed_geometry_changed=previous is not None and
                  (previous['body_discs'] != snap['body_discs'] or previous['body_rects'] != snap['body_rects']))
    t.search27_previous = snap; t.search27_invalid = bad
    if not bad:
        return None
    t.approach_plan_valid = False
    # A stationary arm collision is not repaired by moving the body blindly.
    candidate = None if reason else escape(t, world, before, nav)
    if candidate is None:
        if t.approach_blocked_since is None:
            t.approach_blocked_since = world['t']
        if world['t']-t.approach_blocked_since >= t.APPROACH_BLOCKED_LIMIT_S:
            t._approach_handoff(world['t'])
        return t._hold(world['t'])
    t.approach_blocked_since = None
    event(t, world['t'], 'start_escape_issued', 'monotone_clearance_escape', command=candidate)
    return candidate


def pulse_segments(t, pose, value):
    from harness.grasp_act_visible_world import command_delta
    for mode in dict.fromkeys(('off', t.search15_modes['search17_odometry'])):
        prior = tuple(pose)
        times = sorted({0., .1, *(max(0., min(.1, d)) for d in value['duration_s'])})
        for a, b in zip(times, times[1:]):
            q0, q1 = (command_delta(value, tt, mode=mode) for tt in (a, b))
            dx, dy, da = (v-u for u, v in zip(q0, q1))
            si = math.sin(da)/da if abs(da) > 1e-10 else 1.
            co = (1-math.cos(da))/da if abs(da) > 1e-10 else 0.
            x, y = si*dx-co*dy, co*dx+si*dy
            c, s = math.cos(prior[2]), math.sin(prior[2])
            end = (prior[0]+c*x-s*y, prior[1]+s*x+c*y, prior[2]+da)
            yield mode, a, b, prior, end
            prior = end


def command_check(t, world, value, before, *, after=None, nav=None, allow_escape=False):
    """Same pure body/arm checker for IRM first pulse and final issuance.

    Includes start samples, both issued models and each wheel deadline. Never
    shrinks geometry, relaxes IK/jaw/READY, or modifies a pose/world coordinate.
    """
    from sim.grasp_act_search23 import BodyNavigation
    from sim.grasp_act_pregrasp import issued_sweep_reason
    from sim.grasp_act_search25 import segment_envelope
    nav = nav if nav is not None else BodyNavigation(t, world)
    after = before if after is None else after
    checks = []; progress = {m: False for m in ('off', t.search15_modes['search17_odometry'])}
    for mode, t0, t1, a, b in pulse_segments(t, nav.pose, value):
        ok = nav.pose_segment(a, b)
        if not ok and allow_escape and a == b and progress[mode]:
            # Wheel deadline expired: stationary tail preserves the improved
            # clearance; it must not introduce a fresh violation.
            ok=True
        if not ok and allow_escape and a[2] == b[2]:
            # Translation-only distance to a convex obstacle is convex. For
            # discs require a nonnegative initial directional derivative;
            # the signed bounds clearance must remain nonnegative. In
            # addition retain ALL existing samples and check every blocker.
            n = max(1, math.ceil(math.dist(a[:2], b[:2])/.002))
            u = np.linspace(0., 1., n+1)
            xy = np.asarray(a[:2])+u[:, None]*(np.asarray(b[:2])-a[:2])
            gaps, slack = nav.measure(xy, a[2])
            bad = slack[0] < 0
            good = ~bad
            env = segment_envelope(a, b, n)
            monotone = bool(bad.any() and (np.diff(slack[:, bad], axis=0) >= 0).all()
                            and (slack[-1, bad] > slack[0, bad]).all())
            # Disc signed distance to the oriented rectangle: exact derivative
            # of squared distance from centre to body box along translation.
            co, si = math.cos(a[2]), math.sin(a[2]);vx,vy=b[0]-a[0],b[1]-a[1]
            from sim.grasp_act_search18 import HALF_X, HALF_Y
            for j, (x, y, _) in enumerate(nav.discs):
                if not bad[j]:continue
                q=np.array((co*(x-a[0])+si*(y-a[1]),-si*(x-a[0])+co*(y-a[1])))
                v=np.array((co*vx+si*vy,-si*vx+co*vy))
                nearest=np.sign(q)*np.maximum(abs(q)-[HALF_X,HALF_Y],0.)
                monotone &= float(nearest @ -v) > 0
            # Rectangle/rectangle overlap has zero distance and no signed
            # penetration derivative. Do not authorize its escape here.
            monotone &= not bool(bad[len(nav.discs):].any())
            ok = monotone and bool((slack[:, good] > env).all())
            progress[mode] |= ok
        if not ok:
            checks.append({'reason': 'body_sweep_reject', 'mode': mode, 'from': a, 'to': b,
                'blockers': list(nav.last_blockers), 'min_gap_m': nav.last_segment_gap})
            return False, checks
        # Full arm trajectory for both models, same wheel-deadline intervals.
        pwm0 = {k: before[k]+t0/.1*(after[k]-before[k]) for k in before}
        pwm1 = {k: before[k]+t1/.1*(after[k]-before[k]) for k in before}
        c,s=math.cos(a[2]),math.sin(a[2]);dx,dy=b[0]-a[0],b[1]-a[1]
        arm=[]
        reason=issued_sweep_reason(world,t.rid,a,pwm0,pwm1,(c*dx+s*dy,-s*dx+c*dy,b[2]-a[2]),audit=arm)
        if reason:
            return False, [{'reason': reason, 'mode': mode, 'blockers': arm}]
    if allow_escape and not all(progress.values()):
        return False, [{'reason':'no_monotone_escape_progress','blockers':[]}]
    return True, checks


def escape(t, world, before, nav):
    # Existing search19 speed .025, no added speed/angle acceptance constant.
    # Translation-only cardinal primitives; no camera or arm transition.
    for dx, dy in ((-1,0),(0,-1),(0,1),(1,0)):
        value=t._continuous(world['t'],.025*dx,.025*dy,0.)
        ok,checks=command_check(t,world,value,before,nav=nav,allow_escape=True)
        if ok:return value
    return None


def first_command(nav, path, goal, point, before):
    from sim.grasp_act_visible_route import drive
    radius,discs,rects=nav.teacher._constraints(nav.world)
    target=nav.waypoint(nav.pose[:2],path,discs,rects,radius)
    if target is None:
        return False, {'reason':'first_command_no_waypoint','blocked_object':'none:no_waypoint',
                       'min_gap_m':None,'gap_scope':'not applicable: no waypoint'}
    value=nav.teacher._continuous(nav.world['t'],**drive(nav.pose,goal,target,point))
    ok,checks=command_check(nav.teacher,nav.world,value,before,nav=nav)
    return ok, {'reason':'admitted' if ok else 'first_command_invalid','command':value,
                'snapshot_id':digest(nav.world),'checks':checks}
