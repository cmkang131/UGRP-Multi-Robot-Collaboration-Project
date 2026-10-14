"""Carry look-around safety probe on VM3. Weld OFF, normal physics.

The frozen grasp teacher (unchanged) reaches a joint hold. Afterwards one robot
issues bounded look commands: servo-6 pan sweeps (mode ``pan``) or short
in-place body yaw pulses with native wheel magnitude 0 or 0.31-0.40 (mode
``yaw``). Loaded formation motion (G1/G7): ``rotate_center`` (both robots rotate
the held beam about its centre), ``pivot_end`` (rotation about the actor's grip
point) and ``carry_straight`` (axial and lateral carry legs). Formation motion is
open loop: per-wheel 0.35 pulses whose durations come from one shared scale so
both robots get the same commanded body rate. ``setdown_look`` (G2/G6): lower
together, open after a code GO/ACK delay, step back, look with the start arm
pose and a pan sweep, then approach and re-grasp with the visible_only release
teacher primitives (sim/grasp_act_release_teacher.py). Simulator truth is used ONLY for evaluation metrics written to this
run's own files (slip, tilt, finger force, partner twist, visibility ratios).
Nothing here is a student input and nothing feeds back into a command.
"""
from __future__ import annotations
import argparse,base64,io,json,math,os,platform,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from harness.grasp_act_contract_v4 import SERVOS,command   # prefix uses the preserved v4 observable_v2 teacher
from scripts.run_grasp_act_teacher import write,apply,snapshot,compress_logs

# Provisional safety thresholds (evaluation only; first measurement, no prior basis).
LIMITS={'finger_min_n':.5,'grip_loss_s':.15,'slip_axis_mm':5.,'slip_perp_mm':3.,'tilt_deg':5.,
        'partner_shift_mm':10.,'partner_yaw_deg':3.,'beam_floor_z_m':.005}
PAN_STEPS=(20,40,80,120,180,270,400)          # PWM; 2000/180 PWM per degree
PAN_REPEAT=((40,8),(120,8))                   # ratchet check: same amplitude repeated
YAW_DURATIONS=(.1,.2,.3,.5,.8)                # s; native wheel level 1/3 (0.31-0.40 band)
YAW_EFFORT=.25                                # +1/12 kinetic feedforward -> 0.333, breakaway 0.35
# Loaded formation motion (G1 rotation, G7 carry). Open loop; rates use the provisional
# own-command calibration in sim/visible_belief.py, and the realized motion is logged
# against it (this probe doubles as calibration data for those constants).
WHEEL=.35
DUTY_PERIOD_S=.15                             # = pulse cap; min/max realizable duration ratio 0.04/0.15
MIN_PULSE_S=.04
GRIP_X_M=.203                                 # base -> grip site along the body x axis (station distance)
BEAM_GRIP_HALF_M=.27                          # beam centre -> band centre (grip)
ROTATE_STEP_DEG=15.
ROTATE_TOTAL_DEG=90.
ROBOT_RADIUS_M=.18                            # plan footprint radius (make_grasp_act_release_plan)
CARRY_LEGS=(('axial',.20,1.),('axial',-.20,1.),('axial',.20,.5),('axial',-.20,.5),('lateral',.15,1.),('lateral',-.15,1.))
FORMATION_MODES=('rotate_center','pivot_end','carry_straight')
SETDOWN_PANS=(1500,1000,500,2000,2500)        # look sweep after set-down (servo 6 range 500-2500)
SETDOWN_DWELL_S=.6
REGRASP_HOLD_S=1.
BAND_HSV={'teal':((70,120,90),(90,255,255)),'blue':((110,120,60),(130,255,255))}   # OpenCV HSV of sim/grasp_act_scene COLORS


def rotation_efforts(radius_m,omega=1.,odometry='off'):
    """Wheel efforts (level units) for body rotation at omega about the body-frame point (radius, 0).

    Body velocity of the base: forward 0, lateral -omega*radius, turn omega.
    Wheel mix (f-l-t, f+l+t, f+l-t, f-l+t) as harness.grasp_act_contract.wheel_mix."""
    from sim.visible_belief import rates
    _,LAT,YAW=rates(odometry)
    l=-omega*radius_m/LAT*WHEEL;t=omega/YAW*WHEEL
    return (-l-t,l+t,l-t,-l+t)


def body_levels(levels,durations,period=DUTY_PERIOD_S):
    """Time-averaged body (forward, left, turn) level over one period."""
    from sim.visible_belief import wheel_to_body
    return wheel_to_body([w*d/period for w,d in zip(levels,durations)])


def pair_duty(efforts,*,period=DUTY_PERIOD_S,min_pulse=MIN_PULSE_S,odometry='off'):
    """Shared-scale per-wheel 0.35 pulses for several robots.

    One scale for all robots keeps the commanded body rates equal. A pulse
    shorter than ``min_pulse`` is zeroed (recorded); the robot's remaining
    wheels are then rescaled so its turn level matches the intended one, and
    the realized rotation point is reported. Raises if not realizable."""
    from sim.visible_belief import rates
    _,LAT,YAW=rates(odometry)
    top=max(abs(w) for e in efforts.values() for w in e)
    if top<=0:raise ValueError('zero motion')
    out={}
    for rid,e in efforts.items():
        dur=[period*abs(w)/top for w in e];lev=[math.copysign(WHEEL,w) if w else 0. for w in e]
        intended=body_levels(lev,dur,period)
        zeroed=[i for i,d in enumerate(dur) if 0<d<min_pulse]
        for i in zeroed:dur[i]=0.;lev[i]=0.
        got=body_levels(lev,dur,period)
        ref=2 if abs(intended[2])>1e-12 else (0 if abs(intended[0])>1e-12 else 1)
        if zeroed and abs(got[ref])>1e-12:
            k=intended[ref]/got[ref];dur=[d*k for d in dur]
        if any(d>period+1e-9 for d in dur):raise ValueError(f'{rid}: not realizable after min-pulse rescale')
        dur=[round(d,4) for d in dur];got=body_levels(lev,dur,period)
        pivot=None
        if abs(got[2])>1e-12:
            pivot=-(got[1]/WHEEL*LAT)/(got[2]/WHEEL*YAW)
        out[rid]={'levels':lev,'durations':dur,'zeroed_wheels':zeroed,'body_levels':list(got),'realized_pivot_x_m':pivot}
    return out


def rotation_plan(mode,actor,partner,*,step_deg=ROTATE_STEP_DEG,sign=1.,odometry='off'):
    """Per-period wheel plan and period count for one rotation increment."""
    from sim.visible_belief import rates
    YAW=rates(odometry)[2]
    if mode=='rotate_center':radii={actor:GRIP_X_M+BEAM_GRIP_HALF_M,partner:GRIP_X_M+BEAM_GRIP_HALF_M}
    elif mode=='pivot_end':radii={actor:GRIP_X_M,partner:GRIP_X_M+2*BEAM_GRIP_HALF_M}
    else:raise ValueError(mode)
    duty=pair_duty({rid:rotation_efforts(r,sign,odometry) for rid,r in radii.items()},odometry=odometry)
    omega=duty[actor]['body_levels'][2]/WHEEL*YAW
    periods=max(1,round(math.radians(step_deg)/(abs(omega)*DUTY_PERIOD_S)))
    return {'duty':duty,'commanded_rad_s':omega,'periods':periods,'commanded_step_deg':math.degrees(abs(omega)*DUTY_PERIOD_S*periods),
            'intended_pivot_x_m':radii}


def carry_plan(kind,distance_m,duty,actor,partner,odometry='off'):
    """Formation translation: robots face each other along the beam axis.

    axial: actor forward, partner backward; lateral: actor left, partner right.
    All four wheels at 0.35 for duty*period each period."""
    from sim.visible_belief import rates
    AX,LAT,_=rates(odometry)
    if not 0<duty<=1:raise ValueError('duty in (0, 1]')
    d=round(DUTY_PERIOD_S*duty,4)
    if d<MIN_PULSE_S:raise ValueError('pulse below minimum')
    sgn=1. if distance_m>0 else -1.
    if kind=='axial':f={actor:(1.,1.,1.,1.),partner:(-1.,-1.,-1.,-1.)};speed=AX
    elif kind=='lateral':f={actor:(-1.,1.,1.,-1.),partner:(1.,-1.,-1.,1.)};speed=LAT
    else:raise ValueError(kind)
    plan={rid:{'levels':[sgn*WHEEL*x for x in v],'durations':[d]*4} for rid,v in f.items()}
    periods=max(1,round(abs(distance_m)/(speed*duty*DUTY_PERIOD_S)))
    return {'duty':plan,'periods':periods,'commanded_m':speed*duty*DUTY_PERIOD_S*periods*sgn}


def swept_space(samples,center0):
    """Truth-only: space the formation needed (robot footprints + beam ends)."""
    radius=0.;xs=[];ys=[]
    for s in samples:
        for xy in s['bases']:
            radius=max(radius,math.dist(xy,center0)+ROBOT_RADIUS_M)
            xs+=[xy[0]-ROBOT_RADIUS_M,xy[0]+ROBOT_RADIUS_M];ys+=[xy[1]-ROBOT_RADIUS_M,xy[1]+ROBOT_RADIUS_M]
        for xy in s['ends']:
            radius=max(radius,math.dist(xy,center0));xs.append(xy[0]);ys.append(xy[1])
    return {'swept_radius_m':radius,'bbox_m':[min(xs),max(xs),min(ys),max(ys)] if xs else None,
            'bbox_size_m':[max(xs)-min(xs),max(ys)-min(ys)] if xs else None}


def setdown_look(world,inst,roles,scene,plan,ports,qw,band,points,base0,window,measure_fn,frame,pwm_origin,ev):
    """G2/G6 set-down-and-look cycle. Commands come only from own geometry, own
    commands and currently visible things; truth is used here for evaluation and
    to give the relative pose of the own band only while it is visible."""
    from sim.grasp_act_release_teacher import (ReleaseTeacher,QuantizedWheels,LOWER_Z_M,RAISE_Z_M,OBSERVE_BACKOFF_M,
        REACH_MID_M,SIGNAL_DELAY_S,GO_SETTLE_S)
    from sim.visible_belief import relative
    from harness.visual_arm_v3 import solve_grip_site_ik,MOUNT_X_M
    from scripts.make_setdown_probe_plan import door_points
    data=world.data;R=tuple(roles);t0=float(data.time)
    for rid in R:qw[rid]=QuantizedWheels(ports[rid])
    rel={rid:ReleaseTeacher(rid,roles[rid],{s_:int(ports[rid]._servo_pulses[s_]) for s_ in SERVOS},
        handoff_pose_estimate=[0.,0.,0.],zone_rect=(0.,0.,1.,1.)) for rid in R}   # zone priors unused here
    sched={rid:[] for rid in R};plan_w={rid:[] for rid in R};timeline=[]
    def pose_of(rid):return [*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])]
    def set_servo(rid,pose,now):
        for sid,v in pose.items():
            if rel[rid].pwm.get(sid)!=v:
                ports[rid].apply({'kind':'look','pan_pulse':v} if sid==6 else {'kind':'arm','servo_id':sid,'pulse':v},now);rel[rid].pwm[sid]=v
    def every(poses,dt):return [(dt*(k+1),q) for k,q in enumerate(poses)]
    def step(seconds,label):
        """Advance with scheduled servo poses and wheel pulses; dead-reckon from issued levels only."""
        rows=[];end=float(data.time)+seconds
        while float(data.time)<end-1e-8:
            now=float(data.time)
            for rid in R:
                while sched[rid] and sched[rid][0][0]<=now+1e-9:set_servo(rid,sched[rid].pop(0)[1],now)
                if plan_w[rid] and all(now>=u-1e-9 for u in qw[rid].until):
                    w,d=plan_w[rid].pop(0);qw[rid].command(w,d,now)
            issued={rid:[lv*max(0.,min(.05,u-now))/.05 if lv else 0. for lv,u in zip(qw[rid].levels,qw[rid].until)] for rid in R}
            rows+=window(.05,label)
            for rid in R:rel[rid].dead_reckon(issued[rid],.05)
        return rows
    def busy():return any(sched.values()) or any(plan_w.values()) or any(any(qw[r].levels) for r in R)
    def until_idle(label,extra=0.,cap=20.):
        rows=[];start=float(data.time)
        while busy() and float(data.time)-start<cap:rows+=step(.05,label)
        return rows+(step(extra,label) if extra else [])
    def mark(name):timeline.append({'phase':name,'t':float(data.time)-t0})
    def observe_band(rid,now):
        m=band.measure(data,rid,roles[rid])
        if m['visible_probes']>=3:
            b=data.body(inst.body);rot=b.xmat.reshape(3,3);g=data.geom_xpos[band.bands[roles[rid]]]
            rel[rid].belief.observe('band',relative(pose_of(rid),(float(g[0]),float(g[1])),math.atan2(rot[1,0],rot[0,0])),now)
        return m['visible_probes']
    pre=measure_fn(world,inst,roles,scene)
    # 1. lower together; 2. code GO/ACK (message delay + settle) then open together
    mark('lower')
    for rid in R:sched[rid]=[(float(data.time)+dt,q) for dt,q in every(rel[rid].arm_waypoints(LOWER_Z_M,8),.2)]
    rows=until_idle('setdown:lower',.6);mark('go_ack');rows+=step(SIGNAL_DELAY_S+GO_SETTLE_S,'setdown:go_ack')
    mark('open');now=float(data.time)
    for rid in R:set_servo(rid,{1:2000},now)
    rows+=step(1.2,'setdown:open');landed=measure_fn(world,inst,roles,scene);frame('setdown_open')
    # 3. raise, step back with own-command pulses
    mark('back_off')
    for rid,t in rel.items():
        t.released_here(float(data.time));sched[rid]=[(float(data.time)+dt,q) for dt,q in every(t.arm_waypoints(RAISE_Z_M,3),.2)]
    rows+=until_idle('setdown:raise')
    for rid,t in rel.items():plan_w[rid]=t.shift_plan(OBSERVE_BACKOFF_M,-1.)
    rows+=until_idle('setdown:back_off',.3)
    # 4. look: start arm pose, pan sweep; visibility of door jambs, destination zone, partner, own band
    mark('look');static=scene.config['static_map']
    door=plan.get('door');dpts=door_points(door) if door else {'west':[],'east':[]}
    zone=region_points(static['regions'][plan.get('destination_region','zone_A')])
    look={rid:[] for rid in R}
    for pan in SETDOWN_PANS:
        now=float(data.time)
        for rid in R:set_servo(rid,{**{k:pwm_origin[rid][k] for k in (3,4,5)},6:pan},now)
        rows+=step(SETDOWN_DWELL_S,f'setdown:look:{pan}')
        for rid in R:
            peer=[p_ for p_ in R if p_!=rid]
            look[rid].append({'pan':pan,'door_west':points.points_visible(data,rid,dpts['west']),'door_east':points.points_visible(data,rid,dpts['east']),
                'door_N_per_face':len(dpts['west']),'zone':points.points_visible(data,rid,zone),'zone_N':len(zone),
                'partner':any(band.body_visible(data,rid,p_+'__robot') for p_ in peer),
                'own_band_probes':band.measure(data,rid,roles[rid])['visible_probes']})
        frame(f'setdown_look_{pan}')
    # 5. approach to mid-reach (visible band if seen, else own-command memory), re-grasp, lift
    mark('approach');now=float(data.time)
    for rid,t in rel.items():
        set_servo(rid,{6:1500},now);observe_band(rid,now)
        plan_w[rid]=t.approach_plan(now)
        if plan_w[rid]:sched[rid]=[(now,{k:int(v) for k,v in solve_grip_site_ik((MOUNT_X_M+REACH_MID_M,0.,.095)).items() if k in (3,4,5,6)})]
    rows+=until_idle('setdown:approach',.3)
    mark('regrasp');now=float(data.time);source={};seen={}
    try:
        dur=0.
        for rid,t in rel.items():
            seen[rid]=observe_band(rid,now);source[rid]=t.pick_target(now)[1]
            seq,d=t.pick_schedule(now);sched[rid]=[(now+.2+dt,q) for dt,q in seq];dur=max(dur,d)
        rows+=step(.2+dur,'setdown:regrasp');error=None
    except ValueError as e:
        error=str(e)
    mark('hold');hold=step(REGRASP_HOLD_S,'setdown:hold');post=measure_fn(world,inst,roles,scene);frame('setdown_regrasp')
    held=error is None and all(min(r[rid]['finger_n'])>=LIMITS['finger_min_n'] for r in hold for rid in R) and all(r['beam_min_z']>=.012 for r in hold)
    def pose_delta(a,b):
        return {'move_m':math.dist(a['beam_xyz'][:2],b['beam_xyz'][:2]),'yaw_deg':((b['beam_yaw_deg']-a['beam_yaw_deg'])+180)%360-180}
    regrip={rid:{'axial_mm':1000*(post[rid]['grip_in_beam_m'][0]-base0[rid]['grip_in_beam_m'][0]),
                 'perp_mm':1000*math.hypot(post[rid]['grip_in_beam_m'][1]-base0[rid]['grip_in_beam_m'][1],post[rid]['grip_in_beam_m'][2]-base0[rid]['grip_in_beam_m'][2])} for rid in R}
    fail=[] if held else (['regrasp_unreachable'] if error else ['regrasp_not_held'])
    out={'held':held,'fail':fail,'error':error,'timeline':timeline,'cycle_sim_s':float(data.time)-t0,
         'setdown_displacement':pose_delta(pre,landed),'total_displacement':pose_delta(pre,post),
         'landed_tilt_deg':max(abs(landed['beam_pitch_deg']),abs(landed['beam_roll_deg'])),'post_tilt_deg':max(abs(post['beam_pitch_deg']),abs(post['beam_roll_deg'])),
         'regrip_vs_first_grasp':regrip,'pick_target_source':source,'band_probes_at_pick':seen,'look':look,
         'look_best':{rid:{k:max(x[k] for x in look[rid]) for k in ('door_west','door_east','zone','own_band_probes')}|{'partner_any':any(x['partner'] for x in look[rid])} for rid in R},
         'scope':'own-command and visible-only commands; truth for evaluation and visible-band relative pose'}
    ev.write(json.dumps({'kind':'setdown_summary',**{k:v for k,v in out.items() if k!='look'}})+'\n')
    return out


def band_pixels(rgb,role):
    """Own-camera slip proxy (what map code could compute with OpenCV): own end band pixels."""
    import cv2,numpy as np
    hsv=cv2.cvtColor(np.asarray(rgb,dtype=np.uint8),cv2.COLOR_RGB2HSV);lo,hi=BAND_HSV[role]
    mask=cv2.inRange(hsv,np.array(lo),np.array(hi));ys,xs=np.nonzero(mask)
    if not len(xs):return {'area_px':0,'centroid':None,'top_v':None,'bottom_v':None}
    return {'area_px':int(len(xs)),'centroid':[float(xs.mean()),float(ys.mean())],'top_v':int(ys.min()),'bottom_v':int(ys.max())}


def beam_frame(world,inst):
    import numpy as np
    b=world.data.body(inst.body);return np.array(b.xpos),np.array(b.xmat).reshape(3,3)


def grip_xyz(world,rid):
    try:return world.data.site(f'{rid}__grip_site').xpos.copy()
    except KeyError:return world.robot(rid).site_xyz('grip_site')


def measure(world,inst,roles,scene,base=None):
    """Truth-only evaluation sample."""
    import numpy as np
    from scripts.cargo_formation_teacher import FormationTeacher
    from types import SimpleNamespace
    pos,rot=beam_frame(world,inst)
    forces=FormationTeacher.finger_forces(SimpleNamespace(world=world,inst=inst,roles=roles))
    row={'t':float(world.data.time),'beam_xyz':pos.tolist(),
         'beam_pitch_deg':math.degrees(math.asin(max(-1.,min(1.,rot[2,0])))),
         'beam_roll_deg':math.degrees(math.atan2(rot[2,1],rot[2,2])),
         'beam_yaw_deg':math.degrees(math.atan2(rot[1,0],rot[0,0]))}
    snap=snapshot(world,inst,roles,scene);row['beam_min_z']=snap['beam']['min_z']
    row['beam_ends_xy']=[list(map(float,v[:2])) for v in snap['beam']['ends'].values()]
    for rid in roles:
        local=rot.T@(grip_xyz(world,rid)-pos)
        xyz=world.robot(rid).base_xyz();yaw=float(world.robot(rid).base_rpy()[2])
        row[rid]={'finger_n':list(forces[rid]),'grip_in_beam_m':local.tolist(),
                  'base_xy':[float(xyz[0]),float(xyz[1])],'base_yaw_deg':math.degrees(yaw)}
    if base is not None:
        row['delta']=delta(row,base,roles)
    return row


def delta(row,base,roles):
    d={'tilt_pitch_deg':abs(row['beam_pitch_deg']-base['beam_pitch_deg']),
       'tilt_roll_deg':abs(row['beam_roll_deg']-base['beam_roll_deg']),
       'beam_yaw_deg':abs(((row['beam_yaw_deg']-base['beam_yaw_deg'])+180)%360-180)}
    for rid in roles:
        g,g0=row[rid]['grip_in_beam_m'],base[rid]['grip_in_beam_m']
        d[rid]={'slip_axis_mm':1000*abs(g[0]-g0[0]),'slip_perp_mm':1000*math.hypot(g[1]-g0[1],g[2]-g0[2]),
                'finger_min_n':min(row[rid]['finger_n']),
                'base_shift_mm':1000*math.dist(row[rid]['base_xy'],base[rid]['base_xy']),
                'base_yaw_deg':abs(((row[rid]['base_yaw_deg']-base[rid]['base_yaw_deg'])+180)%360-180)}
    return d


def verdict(samples,roles,actor,*,formation=False):
    """Worst case over one test window, relative to the pre-test hold."""
    worst={'tilt_deg':0.,'beam_min_z':math.inf}
    for rid in roles:worst[rid]={'slip_axis_mm':0.,'slip_perp_mm':0.,'finger_min_n':math.inf,'base_shift_mm':0.,'base_yaw_deg':0.,
                                 'dropout_samples':0,'longest_low_force_s':0.}
    runs={rid:0. for rid in roles};last_t=None
    for s in samples:
        dt=.05 if last_t is None else max(0.,s.get('t',0.)-last_t);last_t=s.get('t',last_t)
        for rid in roles:
            low=s['delta'][rid]['finger_min_n']<LIMITS['finger_min_n']
            worst[rid]['dropout_samples']+=low;runs[rid]=runs[rid]+dt if low else 0.
            worst[rid]['longest_low_force_s']=max(worst[rid]['longest_low_force_s'],runs[rid])
        d=s['delta'];worst['tilt_deg']=max(worst['tilt_deg'],d['tilt_pitch_deg'],d['tilt_roll_deg'])
        worst['beam_min_z']=min(worst['beam_min_z'],s['beam_min_z'])
        for rid in roles:
            for k in ('slip_axis_mm','slip_perp_mm','base_shift_mm','base_yaw_deg'):worst[rid][k]=max(worst[rid][k],d[rid][k])
            worst[rid]['finger_min_n']=min(worst[rid]['finger_min_n'],d[rid]['finger_min_n'])
    reasons=[]
    if worst['tilt_deg']>LIMITS['tilt_deg']:reasons.append('tilt')
    if worst['beam_min_z']<LIMITS['beam_floor_z_m']:reasons.append('beam_touches_floor')
    for rid in roles:
        w=worst[rid]
        if w['longest_low_force_s']>=LIMITS['grip_loss_s']-1e-9:reasons.append(rid+':grip_force')
        if w['slip_axis_mm']>LIMITS['slip_axis_mm']:reasons.append(rid+':slip_axis')
        if w['slip_perp_mm']>LIMITS['slip_perp_mm']:reasons.append(rid+':slip_perp')
        if formation:continue                     # both robots move on purpose
        if rid!=actor and w['base_shift_mm']>LIMITS['partner_shift_mm']:reasons.append(rid+':partner_dragged')
        if rid!=actor and w['base_yaw_deg']>LIMITS['partner_yaw_deg']:reasons.append(rid+':partner_twisted')
    return worst,reasons


class PointVisibility:
    """Evaluation-only floor/body point exposure in the actual runtime camera."""
    def __init__(self,band):self.band=band
    def points_visible(self,data,rid,points):
        import cv2,mujoco,numpy as np
        b=self.band;cid=b.cameras[rid];seen=0
        for point in np.asarray(points,dtype=float):
            p=((point-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
            if p[2]<=b.near:continue
            uv=p[:2]/p[2]*np.diag(b.K)[:2]+b.K[:2,2]
            raw,_=cv2.fisheye.projectPoints(p.reshape(1,1,3),np.zeros(3),np.zeros(3),b.K,b.D)
            if not (0<=uv[0]<640 and 0<=uv[1]<480 and 0<=raw[0,0,0]<640 and 0<=raw[0,0,1]<480):continue
            delta=point-data.cam_xpos[cid];dist=float(np.linalg.norm(delta));direction=delta/dist
            skip=b.near*dist/p[2];origin=data.cam_xpos[cid]+skip*direction;hit=np.array([-1],dtype=np.int32)
            ray=mujoco.mj_ray(b.model,data,origin,direction,b.groups,True,-1,hit)
            if hit[0]<0 or ray<0 or ray>=dist-skip-.01:seen+=1   # nothing in front of the floor point
        return seen


def region_points(region,z=.002):
    (cx,cy),(hx,hy)=region['center_m'],region['half_extents_m']
    return [(cx+sx*hx*.8,cy+sy*hy*.8,z) for sx in (-1,0,1) for sy in (-1,0,1)]


def run(plan,out,*,mode,actor,grasp_cap_s=45.,teacher_profile='observable_v2',destination='zone_A',pair_odometry='off'):
    if platform.system()=='Darwin':raise RuntimeError('Mac physics/render disabled; use VM3')
    from sim.grasp_act_scene import make_scene
    from sim.grasp_act_teacher import GraspTeacher
    from sim.masterpi_drive_friction_v7 import build_world,PROFILE
    from sim.grasp_act_port import ContinuousActPort
    from harness.static_keepouts import keepout_rects
    from scripts.audit_grasp_act_visibility import BandVisibility
    from collections import deque
    from PIL import Image
    out.mkdir(parents=True,exist_ok=False);write(out/'plan.json',plan)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):raise RuntimeError('committed source required')
    write(out/'RUN_META.json',{'class':'dev','pr':484,'branch':'claude/grasp-act-release','sha':sha,'batch':plan['batch']+'-lookaround-'+mode})
    report={'status':'running','source_sha':sha,'mode':mode,'actor':actor,'weld':'off','pair_odometry':pair_odometry,'limits':LIMITS,
            'scope':'evaluation-only truth metrics; probe commands are fixed schedules, not truth-corrected',
            'loadavg_at_start':os.getloadavg()}
    write(out/'result.json',report);world=None;start=time.monotonic();streams=[]
    try:
        os.environ['UGRP_SIM_OBSERVER_WIDTH']='320';os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
        scene=make_scene(plan)
        world=build_world(scene,drive_profile=PROFILE,seed=plan['seed'],width=320,height=240,render=True,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
        if teacher_profile=='observable_v2':
            from sim.s2_realism_camera_binding import bind_camera
            for controller in world.controllers.values():bind_camera(controller)
        scene.setup(world)
        from sim.zone_cargo import place,CargoInstance
        place(world,[CargoInstance('beam_1','long_beam',tuple(plan['beam_pose']))])
        (out/'scene.xml').write_text(world.scene_xml)
        roles=plan['roles'];ports={rid:ContinuousActPort(world,rid,allow_reverse=True,allow_mecanum=True) for rid in roles}
        qw={}
        for rid,port in ports.items():port.apply({'kind':'look','pan_pulse':plan['initial_pan'][rid]},float(world.data.time))
        def advance(target):
            while float(world.data.time)<target-1e-8:
                now=float(world.data.time)
                if world.data.eq_active.any():raise RuntimeError('WELD_ACTIVE')
                for port in ports.values():port.tick(now)
                for w in qw.values():w.tick(now)
                world._physics_step_for(world.robot('r1'))
        advance(float(world.data.time)+.5)
        origin=float(world.data.time);inst=next(x for x in scene.cargo if x.item_id=='beam_1')
        band=BandVisibility(world.model);points=PointVisibility(band)
        static=scene.config['static_map'];dest=region_points(static['regions'][destination])
        object_bodies={c.item_id:c.body for c in scene.cargo if c.item_id!='beam_1'}
        object_bodies.update({i:c['body_name'] for i,c in scene.config['setup_only']['objects'].items()})
        teachers={};previous={}
        pwm_origin={rid:{s_:int(ports[rid]._servo_pulses[s_]) for s_ in SERVOS} for rid in roles}
        for rid,end in roles.items():
            pwm={str(s):int(ports[rid]._servo_pulses[s]) for s in SERVOS}
            previous[rid]=command({'t':origin,'drive':[0.,0.,0.],'duration_s':0.,'pwm':pwm})
            teachers[rid]=GraspTeacher(rid,end,pwm,bounds=static['bounds_m'],rects=keepout_rects(static),profile=teacher_profile)
        ev=(out/'eval-only.jsonl').open('w');streams.append(ev)
        for rid in roles:(out/'eval-own'/rid).mkdir(parents=True)
        def frame(tag):
            for rid in roles:
                jpg=base64.b64decode(ports[rid].capture()['image'])
                Image.open(io.BytesIO(jpg)).resize((320,240)).save(out/'eval-own'/rid/f'{tag}.jpg',quality=86)
        # --- phase A: frozen grasp teacher until a 1 s joint hold ---
        i=0;both_since=None;held_at=None
        while float(world.data.time)-origin<grasp_cap_s:
            now=float(world.data.time);truth=snapshot(world,inst,roles,scene)
            truth['visibility']={rid:band.measure(world.data,rid,end) for rid,end in roles.items()}
            if teacher_profile=='observable_v2':
                for rid in roles:
                    truth['visibility'][rid]['objects']=[k for k,b in object_bodies.items() if band.body_visible(world.data,rid,b)]
                    truth['visibility'][rid]['peers']=[p for p in ('r1','r2','r3') if p!=rid and band.body_visible(world.data,rid,p+'__robot')]
            if i%10==0:frame(f'grasp-{i:05d}')
            both=all(min(truth['contacts'][rid])>=.5 for rid in roles) and truth['beam']['min_z']>=.012
            both_since=(now if both_since is None else both_since) if both else None
            done=all(t.outcome=='success' for t in teachers.values())
            if done and both_since is not None and now-both_since>=1.:held_at=now;break
            if any(t.outcome not in (None,'success') for t in teachers.values()):break
            permit=all(x.phase in ('ready','pick','verify','done') for x in teachers.values())
            if teacher_profile=='observable_v2':
                permit=permit and all(x.phase!='ready' or truth['visibility'][rid]['visible_probes']>=3 for rid,x in teachers.items())
            for rid,t in teachers.items():
                clean,_=t.step(truth,now,permit_pick=permit)
                apply(ports[rid],clean,now,previous[rid]);previous[rid]=clean
            i+=1;advance(origin+i*.1)
        report['grasp']={'held':held_at is not None,'held_sim_s':None if held_at is None else held_at-origin,
                         'outcomes':{r:t.outcome for r,t in teachers.items()}}
        if held_at is None:
            report.update(status='complete',probe='not_reached');return report
        frame('held')
        # --- phase B: settle hold, all wheels zero, last issued arm pose kept ---
        for port in ports.values():port.stop()
        advance(float(world.data.time)+2.)
        base=base0=measure(world,inst,roles,scene);ev.write(json.dumps({'kind':'baseline',**base})+'\n')
        p0=int(ports[actor]._servo_pulses[6]);tests=[];failures=0
        def window(seconds,label):
            rows=[];end=float(world.data.time)+seconds
            while float(world.data.time)<end-1e-8:
                advance(float(world.data.time)+.05);s=measure(world,inst,roles,scene,base)
                s['label']=label;rows.append(s);ev.write(json.dumps(s)+'\n')
            return rows
        def look_vis(rid):
            peer=[p for p in roles if p!=rid]
            return {'destination_points':points.points_visible(world.data,rid,dest),'destination_N':len(dest),
                    'partner':[band.body_visible(world.data,rid,p+'__robot') for p in peer],
                    'obstacles':sorted(k for k,b in object_bodies.items() if band.body_visible(world.data,rid,b)),
                    'obstacle_N':len(object_bodies),'own_end_probes':band.measure(world.data,rid,roles[rid])['visible_probes']}
        vis={'p0':look_vis(actor)}
        if mode=='pan':
            for amp in PAN_STEPS:
                rows=[];vis_amp={}
                for k,target in enumerate((p0+amp,p0,p0-amp,p0)):
                    target=max(500,min(2500,target))
                    ports[actor].apply({'kind':'look','pan_pulse':target},float(world.data.time))
                    rows+=window(1.,f'pan{amp}:{k}')
                    if target!=p0:vis_amp[str(target-p0)]=look_vis(actor);frame(f'pan{amp:03d}_{"p" if target>p0 else "m"}')
                worst,reasons=verdict(rows,roles,actor)
                tests.append({'cumulative_after':delta(measure(world,inst,roles,scene),base0,roles),'pan_pwm':amp,'pan_deg':amp*180/2000,'worst':worst,'fail':reasons,'visibility':vis_amp})
                failures+=bool(reasons)
                if any('grip_force' in r or r=='beam_touches_floor' for r in reasons) or failures>=2:break
                base=measure(world,inst,roles,scene)   # re-zero after a recovered sweep
        elif mode=='pan_repeat':
            for amp,reps in PAN_REPEAT:
                for rep in range(reps):
                    rows=[]
                    for k,target in enumerate((p0+amp,p0,p0-amp,p0)):
                        ports[actor].apply({'kind':'look','pan_pulse':max(500,min(2500,target))},float(world.data.time))
                        rows+=window(1.,f'rep{amp}:{rep}:{k}')
                    worst,reasons=verdict(rows,roles,actor)
                    tests.append({'cumulative_after':delta(measure(world,inst,roles,scene),base0,roles),'pan_pwm':amp,'rep':rep,
                                  'worst':worst,'fail':reasons})
                    if any('grip_force' in r or r=='beam_touches_floor' for r in reasons):break
                    base=measure(world,inst,roles,scene)
                frame(f'rep{amp:03d}')
        elif mode in FORMATION_MODES:
            from sim.grasp_act_release_teacher import QuantizedWheels
            partner=next(r for r in roles if r!=actor)
            for rid in roles:qw[rid]=QuantizedWheels(ports[rid])
            c0=base0['beam_xyz'][:2];space_rows=[];stop=False;n_px=0
            def band_px():
                out={}
                for rid in roles:
                    jpg=base64.b64decode(ports[rid].capture()['image'])
                    out[rid]=band_pixels(Image.open(io.BytesIO(jpg)).convert('RGB'),roles[rid])
                return out
            def drive(plan_m,label):
                nonlocal n_px
                rows=[]
                for k in range(plan_m['periods']):
                    now=float(world.data.time)
                    for rid in roles:
                        d=plan_m['duty'][rid];qw[rid].command(d['levels'],d['durations'],now)
                    rows+=window(DUTY_PERIOD_S,label+':on')
                    if k%3==0:rows[-1]['band_px']=band_px();n_px+=1;ev.write(json.dumps({'kind':'band_px','t':rows[-1]['t'],'label':label,**rows[-1]['band_px']})+'\n')
                for w in qw.values():w.stop()
                return rows+window(1.,label+':hold')
            def realized(before,after):
                out={'beam_yaw_deg':((after['beam_yaw_deg']-before['beam_yaw_deg'])+180)%360-180,
                     'beam_move_m':math.dist(after['beam_xyz'][:2],before['beam_xyz'][:2])}
                for rid in roles:
                    out[rid]={'base_move_m':math.dist(after[rid]['base_xy'],before[rid]['base_xy']),
                              'base_yaw_deg':((after[rid]['base_yaw_deg']-before[rid]['base_yaw_deg'])+180)%360-180}
                return out
            if mode=='carry_straight':
                legs=[(kind,dist,duty,carry_plan(kind,dist,duty,actor,partner,pair_odometry)) for kind,dist,duty in CARRY_LEGS]
                for kind,dist,duty,plan_m in legs:
                    before=measure(world,inst,roles,scene)
                    rows=drive(plan_m,f'carry:{kind}:{dist:+.2f}:{duty}')
                    after=measure(world,inst,roles,scene);worst,reasons=verdict(rows,roles,actor,formation=True)
                    tests.append({'leg':[kind,dist,duty],'plan':plan_m,'realized':realized(before,after),
                                  'cumulative_after':delta(after,base0,roles),'worst':worst,'fail':reasons,
                                  'force_slip_series':[{'t':r['t'],**{rid:{'finger_n':r[rid]['finger_n'],'slip_axis_mm':r['delta'][rid]['slip_axis_mm'],
                                      'slip_perp_mm':r['delta'][rid]['slip_perp_mm']} for rid in roles},**({'band_px':r['band_px']} if 'band_px' in r else {})} for r in rows]})
                    space_rows+=rows;frame(f'carry_{kind}_{"p" if dist>0 else "m"}{int(duty*100):03d}')
                    if any('grip_force' in r or r=='beam_touches_floor' for r in reasons):break
                    base=measure(world,inst,roles,scene)
            else:
                for sign in (1.,-1.):
                    plan_m=rotation_plan(mode,actor,partner,sign=sign,odometry=pair_odometry)
                    for inc in range(int(round(ROTATE_TOTAL_DEG/ROTATE_STEP_DEG))):
                        before=measure(world,inst,roles,scene)
                        rows=drive(plan_m,f'{mode}:{sign:+.0f}:{inc}')
                        after=measure(world,inst,roles,scene);worst,reasons=verdict(rows,roles,actor,formation=True)
                        tests.append({'direction':sign,'increment':inc,'plan':plan_m,'realized':realized(before,after),
                                      'cumulative_after':delta(after,base0,roles),'worst':worst,'fail':reasons})
                        space_rows+=rows
                        if any('grip_force' in r or r=='beam_touches_floor' for r in reasons):stop=True;break
                        base=measure(world,inst,roles,scene)
                    frame(f'{mode}_{"ccw" if sign>0 else "cw"}')
                    if stop:break
            report['space']=swept_space([{'bases':[r[rid]['base_xy'] for rid in roles],'ends':r['beam_ends_xy']} for r in space_rows],c0)
            report['band_px_samples']=n_px
        elif mode=='setdown_look':
            report['setdown']=setdown_look(world,inst,roles,scene,plan,ports,qw,band,points,base0,window,measure,frame,pwm_origin,ev)
            tests.append({'fail':report['setdown']['fail']})
        elif mode=='yaw':
            for duration in YAW_DURATIONS:
                rows=[];yaw0=world.robot(actor).base_rpy()[2];vis_d={}
                for k,sign in enumerate((1,-1)):
                    t0=float(world.data.time)
                    while float(world.data.time)<t0+duration-1e-8:
                        ports[actor].apply({'kind':'mecanum','forward':0.,'left':0.,'turn':sign*YAW_EFFORT,'duration_s':.15},float(world.data.time))
                        step=min(.1,t0+duration-float(world.data.time))
                        rows+=window(step,f'yaw{duration}:{k}:on')
                    ports[actor].stop();rows+=window(1.5,f'yaw{duration}:{k}:hold')
                    if k==0:
                        turned=math.degrees(((world.robot(actor).base_rpy()[2]-yaw0)+math.pi)%(2*math.pi)-math.pi)
                        vis_d['turned']=look_vis(actor);frame(f'yaw{int(duration*1000):04d}')
                worst,reasons=verdict(rows,roles,actor)
                tests.append({'cumulative_after':delta(measure(world,inst,roles,scene),base0,roles),'pulse_s':duration,'native_wheel_level':[round(x,3) for x in (.35,YAW_EFFORT+1/12)],
                              'turned_deg':turned,'rate_deg_s':turned/duration,'worst':worst,'fail':reasons,'visibility':vis_d})
                failures+=bool(reasons)
                if any('grip_force' in r or r=='beam_touches_floor' for r in reasons) or failures>=2:break
                base=measure(world,inst,roles,scene)
        frame('end')
        safe=[t for t in tests if not t['fail']]
        report.update(status='complete',probe='done',tests=tests,visibility_p0=vis,
            safe_max=None if mode in FORMATION_MODES+('setdown_look',) else ((max(t['pan_pwm'] for t in safe) if mode!='yaw' else max(t['pulse_s'] for t in safe)) if safe else None),
            pass_n=len(safe),test_N=len(tests),
            first_fail=next(({'step':t.get('pan_pwm',t.get('pulse_s',t.get('leg',t.get('increment')))),'reasons':t['fail']} for t in tests if t['fail']),None))
        return report
    except BaseException as error:
        report.update(status='HOST_ERROR' if not isinstance(error,KeyboardInterrupt) else 'interrupted',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        report['wall_s']=time.monotonic()-start;report['sim_s']=None if world is None else float(world.data.time)
        report['loadavg_at_end']=os.getloadavg();write(out/'result.json',report)
        for s in streams:s.close()
        if world is not None:world.close()
        compress_logs(out)


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--episode',type=int,default=0)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--mode',choices=('pan','pan_repeat','yaw','setdown_look')+FORMATION_MODES,required=True)
    p.add_argument('--actor',choices=('r1','r2'),default='r1');p.add_argument('--grasp-cap-s',type=float,default=45.)
    p.add_argument('--teacher-profile',choices=('legacy','pi_geometry_v1','observable_v2'),default='observable_v2')
    p.add_argument('--pair-odometry',choices=('off','gcp_probe_v1'),default='off',help='gcp_probe_v1: pair-carry rates measured on gcp1 (sim/visible_belief.py)');a=p.parse_args()
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan,a.out,mode=a.mode,actor=a.actor,grasp_cap_s=a.grasp_cap_s,teacher_profile=a.teacher_profile,pair_odometry=a.pair_odometry),ensure_ascii=False))
if __name__=='__main__':main()
