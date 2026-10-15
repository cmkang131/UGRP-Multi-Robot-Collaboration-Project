"""Default-off release23 teacher candidates. No simulator/world-state access.

Calibration: experiments/2026-10-14-e2e18-grasp-rootcause/release23-baseline-rejections.json.
All acceptance uses delivered same-round scalars; sweep uses each own RGB fix,
issued-command FK and fixed geometry. The ACT student interface is unchanged.
"""
from __future__ import annotations
import math
import numpy as np
from sim import release14, release15, release17, release18, release20, release21
from sim import release_global_observation as global_obs
from sim.visible_belief import odometry
from sim.settle_pulse import proportional_pulse

MARGIN = 'margin_common_mode_v1'
LEG = 'release_leg_budget_v1'
LATERAL = 'lateral_rate_cal_v1'
YAW = 'release_yaw_budget_v1'
COMPUTE = 'compute_budget_v1'
OPTIONS = dict(margin_common_mode=MARGIN, release_leg_budget=LEG,
               lateral_rate_cal=LATERAL, release_yaw_budget=YAW,
               release_plan_budget=COMPUTE)
# gcp1 saved 194 same-round pairs, 388 ends: maximum absolute residual
# after equality projection; empirical bound, NOT a probabilistic guarantee.
ERROR_BOUND_M = .04704375885875689
# Audit R02: sum deficit .072 + 3*.027 ~= .153 m; requested candidate .15.
# Bias clamp -.10 is the explicitly requested candidate, not a measured bound.
SUM_LIMIT_M = .15
BIAS_MIN_M = -.10
# R03: 110/110 axial legs saturated, max initial center offset .797 m.
# Three .30 m legs cover .90 m; no change to the 180 SIM s episode cap.
MAX_SHIFT_M = .30
MAX_CORRECTIONS = 3
# Saved completed cycles n=115, higher p95=48.30 s. Additional .10/.129
# command travel for the .30 m candidate. Final tail max=6.70 SIM s.
LEG_COST_S = 49.07519379730747
TAIL_S = 6.699999999843726
MOTION_CAP = np.array([.10, .10, math.radians(18)])  # unchanged release17


def validate(profile, record_training, options, plan):
    for key, mode in OPTIONS.items():
        if options.get(key,'off') not in ('off',mode): raise ValueError('unknown '+key)
    if any(options.get(k,'off')!='off' for k in OPTIONS):
        if options.get('release21')!=release21.MODE or options.get('command_motion')!='yaw_cal_v1':
            raise ValueError('release23 requires release21_v1 and yaw_cal_v1')
    release21.validate(profile, record_training, options, plan)


def rejection(reason, obj, gap=None, unit='m', **extra):
    return dict(reason_category=reason, blocking_object=obj, minimum_gap=gap,
                gap_unit=unit, **({'gap_unknown_reason':'not observable from permitted input'} if gap is None else {}), **extra)


def pair_choice(reports, robots, now, *, margin_common_mode='off', release_leg_budget='off',
                goal_region='off', **kwargs):
    if margin_common_mode=='off' and release_leg_budget=='off':
        return release18.pair_choice(reports,robots,now,goal_region=goal_region,**kwargs)
    rows=[reports[r] or {} for r in robots]; adapted=reports; meta={}
    if margin_common_mode==MARGIN and all(r.get('kind')=='localized_margin' for r in rows):
        epochs=[r.get('observation_epoch') for r in rows]
        times=[r.get('observed_at') for r in rows]
        if None in epochs or len(set(epochs))!=1 or any(t is None or not math.isfinite(t) or t>now for t in times):
            return dict(action='observe',reason='margin_epoch_mismatch',t=now,
                        **rejection('observation_consistency','same-round pair reports'))
        m=np.array([r['margin_m'] for r in rows],float)
        theta=np.array([r.get('axis_error_rad',math.nan) for r in rows])
        widths=[r.get('zone_axis_width_m') for r in rows]
        if (not np.isfinite(m).all() or not np.isfinite(theta).all() or None in widths
                or not all(math.isfinite(w) and w>0 for w in widths) or widths[0]!=widths[1]):
            return dict(action='observe',reason='margin_geometry_unobserved',t=now,
                        **rejection('observation_geometry','fixed beam/zone dimensions'))
        slack=widths[0]-.60*float(np.abs(np.cos(theta)).mean())
        residual=float(m.sum()-slack)
        if not -SUM_LIMIT_M<=residual<=0:
            return dict(action='observe',reason='margin_common_mode_domain',t=now,
                        **rejection('margin_consistency','known beam length constraint',min(-residual,SUM_LIMIT_M+residual)),
                        raw_margins_m=m.tolist(),sum_residual_m=residual)
        bias=max(BIAS_MIN_M,min(0.,residual/2)); corrected=m-bias; lower=corrected-ERROR_BOUND_M
        adapted={r:dict(v,margin_m=float(lower[i]),expected_slack_m=slack-2*ERROR_BOUND_M)
                 for i,(r,v) in enumerate(zip(robots,rows))}
        meta=dict(raw_margins_m=m.tolist(),corrected_margins_m=corrected.tolist(),
                  margin_lower_bounds_m=lower.tolist(),common_bias_m=bias,
                  sum_residual_m=residual,error_bound_m=ERROR_BOUND_M,observation_epoch=epochs[0])
    choice=release18.pair_choice(adapted,robots,now,goal_region=goal_region,**kwargs)
    if choice.get('reason')=='localized_margin_correction' and choice['action']=='shift':
        m=[adapted[r]['margin_m'] for r in robots]
        shift=(m[1]-m[0])/2
        if margin_common_mode==MARGIN and goal_region==release18.GOAL_REGION:
            lo,hi=global_obs.MARGIN_M-m[0],m[1]-global_obs.MARGIN_M
            if lo>hi:
                return dict(action='observe',reason='margin_goal_interval_empty',t=now,**meta,
                            **rejection('margin_goal','both end margin lower bounds',hi-lo))
            shift=min(max(0.,lo),hi)  # closest point in the feasible goal interval
            choice['admissible_shift_m']=[lo,hi]
        limit=MAX_SHIFT_M if release_leg_budget==LEG else global_obs.MAX_SHIFT_M
        choice['shift_m']=max(-limit,min(limit,shift))
    if choice['action'] in ('observe','stop'):
        choice.update(rejection(choice['reason'],'delivered release margin constraints'))
    return dict(choice,**meta)


def leg_admission(remaining_s, corrections):
    gap=remaining_s-(LEG_COST_S+TAIL_S)
    if corrections>=MAX_CORRECTIONS:
        return dict(accepted=False,**rejection('correction_count','release correction budget',MAX_CORRECTIONS-corrections,'legs'))
    return dict(accepted=gap>=0,remaining_sim_s=remaining_s,expected_leg_s=LEG_COST_S,tail_s=TAIL_S,
                **rejection('leg_time_available' if gap>=0 else 'insufficient_leg_time','remaining episode SIM budget',gap,'SIM s'))


def _hull(points):
    points=sorted(set(map(tuple,points)))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    parts=[]
    for seq in (points,list(reversed(points))):
        row=[]
        for p in seq:
            while len(row)>=2 and cross(row[-2],row[-1],p)<=0:row.pop()
            row.append(p)
        parts.append(row[:-1])
    return parts[0]+parts[1]


def _polygon_gap(a,b):
    from harness.static_keepouts import _axes
    # SAT separation; a positive value certifies a separating axis, negative
    # values record penetration. No new clearance threshold is introduced.
    return max(max(min(x*ax+y*ay for x,y in b)-max(x*ax+y*ay for x,y in a),
                   min(x*ax+y*ay for x,y in a)-max(x*ax+y*ay for x,y in b)) for ax,ay in (*_axes(a),*_axes(b)))


def sweep(localizers, teachers, plans, now, *, computation_budget='off'):
    """Exact convex translation sweeps, both robots and both beam hypotheses.

    Each hypothesis uses its own RGB pose and issued FK end; .60 x .04 m
    fixed beam, .18 m robot envelope from the existing map model. Retain the
    existing covariance halo max(.02, 2 sigma); it is not a new fitted value.
    No partner RGB/pose is fed to a robot and no held-object world read occurs.
    """
    from harness.static_keepouts import disc_footprint, polygon_at, rect_corners
    checks=[]
    # An authored finite problem, not a load-dependent wall deadline. On mode
    # audits exactly two shapes per robot against bounds + every obstacle.
    budget=sum(2*(1+len(localizers[r].global_matcher.static.get('obstacles',[]))) for r in teachers)
    for rid,t in teachers.items():
        loc=localizers[rid]; static=loc.global_matcher.static
        if not loc.map_pose_known or not (loc.decision or {}).get('accepted'):
            return dict(accepted=False,checks=checks,**rejection('sweep_pose_unknown',rid+' own RGB map fix'))
        pose=np.asarray(loc.own.x,float);P=np.asarray(loc.own.P,float)
        if not np.isfinite(pose).all() or not np.isfinite(P).all():
            return dict(accepted=False,checks=checks,**rejection('sweep_pose_invalid',rid+' own RGB map fix'))
        halo=max(.02,2*math.sqrt(max(0.,np.linalg.eigvalsh(P[:2,:2]).max())))
        vertices=disc_footprint(.18); beam_vertices=[]
        (ex,ey),(ox,oy),_=t.end_and_outward(now)
        center=np.array([ex,ey])-.30*np.array([ox,oy]); normal=np.array([-oy,ox])
        for along in (-.30,.30):
            for width in (-.02,.02):beam_vertices.append(tuple(center+along*np.array([ox,oy])+width*normal))
        position=pose.copy(); robot_points=polygon_at(position,vertices); beam_points=polygon_at(position,beam_vertices)
        for wheels,durations in plans[rid]:
            motion=odometry([w*d/.1 for w,d in zip(wheels,durations)],.1,t.odometry_profile)
            # This guard covers translations. Axis turns keep their existing
            # separate bounded checker; never silently approximate rotation.
            if abs(motion[2])>1e-9:
                return dict(accepted=False,checks=checks,**rejection('sweep_nontranslation',rid+' issued yaw',-abs(motion[2]),'rad'))
            c,s=math.cos(position[2]),math.sin(position[2]);dx,dy=motion[:2]
            position[:2]+=[c*dx-s*dy,s*dx+c*dy]
            robot_points+=polygon_at(position,vertices);beam_points+=polygon_at(position,beam_vertices)
        for name,points in ((rid,_hull(robot_points)),(rid+' beam from own commands',_hull(beam_points))):
            x0,x1,y0,y1=static['bounds_m'];gap=float(min(min(x-x0,x1-x,y-y0,y1-y) for x,y in points)-halo)
            checks.append(dict(body=name,**rejection('static_sweep','map bounds',gap),accepted=gap>0))
            for obstacle in static.get('obstacles',[]):
                rect=(*obstacle['center_m'],*obstacle['half_extents_m'],obstacle.get('yaw_rad',0.))
                gap=float(_polygon_gap(points,rect_corners(rect,margin=halo)))
                checks.append(dict(body=name,**rejection('static_sweep',obstacle['id'],gap),accepted=gap>0))
    worst=min(checks,key=lambda v:v['minimum_gap'])
    assert computation_budget in ('off',COMPUTE)
    if computation_budget==COMPUTE and len(checks)>budget:raise RuntimeError('sweep_computation_budget')
    return dict(accepted=all(c['accepted'] for c in checks),checks=checks,
                **{k:worst[k] for k in ('reason_category','blocking_object','minimum_gap','gap_unit')},
                computation_checks=len(checks),computation_budget=budget if computation_budget==COMPUTE else None,
                budget_basis='finite issued-plan convex hull and authored obstacle count')


def rejection_ledger(report):
    """Complete diagnostic categories, retaining unknown legacy numeric gaps."""
    rows=[]
    for c in report.get('code_decisions',[]):
        if c.get('action') in ('observe','stop'):
            rows.append(dict(c,**({} if c.get('blocking_object') else rejection(c.get('reason') or 'unobserved','release margin observation'))))
    for check in report.get('line_rechecks',[]):
        for e in check['events']:
            if 'blocked' in e['event'] or 'reject' in e['event'] or e.get('accepted') is False:
                if e.get('blocking_object'):rows.append(dict(e,robot=check['robot']));continue
                fov='fov' in e['event'] or e.get('action')=='recenter'
                gap=release21.margin(e['points']) if e.get('points') and fov else None
                rows.append(dict(e,robot=check['robot'],**rejection(e.get('reason') or e['event'],
                    'own camera FOV boundary' if fov else 'issued motion / static map candidate',gap,'pixel' if fov else 'm')))
    for key in ('release23_sweep_checks','release23_leg_admissions'):
        rows.extend(v for v in report.get(key,[]) if not v['accepted'])
    outcome=report.get('release_outcome')
    if outcome and outcome!='teacher_done' and not rows:
        rows.append(rejection(outcome,'episode SIM cap' if outcome in ('cap_end','release_timeout') else 'release controller terminal guard'))
    return rows


class LineAlign(release21.LineAlign):
    """At the unchanged cap, compare a lateral pulse and fresh stationary RGB."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.budget_reobservations=0

    def choose_step(self,f,period,now):
        step=super().choose_step(f,period,now)
        if step.get('aligned') or step.get('kind')!='line_ibvs':return step
        w,d,actual,_=self.pulse((step['forward'],step['left'],step['yaw']))
        if np.all(self.motion+abs(actual)<=MOTION_CAP+1e-9):return step
        gap=float(np.min(MOTION_CAP-self.motion-abs(actual)))
        self.records.append(dict(t=now,event='release23_yaw_budget_reject',
            **rejection('issued_motion_budget','cumulative absolute yaw 18deg',gap,'rad'),
            cumulative=self.motion.tolist(),proposed=actual.tolist(),remaining=(MOTION_CAP-self.motion).tolist()))
        model=release20.polar_jacobian(self.camera,self.teacher.pwm);error=np.array(step['error']);column=model[:,0]
        correction=np.array([proportional_pulse(float(e),0.,quantize=False) for e in error])
        left=float(np.clip(-column@correction/(column@column),-.004,.004))
        w,d=release14.pulse_for(0.,left,0.,self.teacher.odometry_profile)
        w,d,_=release17.floor_pulse(w,d)
        actual=np.array(odometry([a*b/.1 for a,b in zip(w,d)],.1,self.teacher.odometry_profile))
        improvement=float(np.linalg.norm(error/np.array([.025,.06]))-np.linalg.norm((error+model@actual[1:])/np.array([.025,.06])))
        accepted=any(d) and improvement>0 and self.allowed(f,actual)
        self.records.append(dict(t=now,event='release23_budget_alternative',action='lateral_only',accepted=bool(accepted),
            predicted_merit_improvement=improvement,proposed=actual.tolist(),
            **rejection('allowed' if accepted else 'no_safe_improving_lateral','line merit / cumulative motion / static map / own FOV',improvement,'normalized line merit')))
        if accepted:
            self._pending_errors=error.tolist()
            return dict(step,forward=0.,left=float(actual[1]),yaw=0.,allocated_pulse=(w,d))
        # Three fresh 100ms samples are the existing 0.3s stability window;
        # no image is reused and no tolerance or yaw budget is enlarged.
        self.budget_reobservations+=1
        if self.budget_reobservations>3:
            raise ValueError('release23_budget_no_safe_improving_alternative')
        self.records.append(dict(t=now,event='release23_budget_alternative',action='reobserve',accepted=True,
            **rejection('fresh_rgb_reobserve','own camera',3-self.budget_reobservations,'samples')))
        return dict(step,forward=0.,left=0.,yaw=0.,allocated_pulse=([0.]*4,[0.]*4))


map_motion_clear=release21.map_motion_clear
backoff_plan=release21.backoff_plan
approach_plan=release21.approach_plan
