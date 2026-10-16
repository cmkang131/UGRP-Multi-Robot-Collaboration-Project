"""Bounded pair yaw correction from own RGB headings and issued grip geometry.

No measured beam pose. Each robot builds only its own plan; code shares a
scalar angle after checking agreement. Translation and rotation must pass the
regrasp barrier before execution. Refusal is explicit, never a request for
more landmark frames. A new physical yaw controller is NOT validated offline.
"""
import math
import numpy as np

MAX_YAW_RAD = math.radians(5)
AGREEMENT_RAD = math.radians(8)


def correction_angle(choice):
    values = choice['axis_errors_rad']
    if len(values)!=2 or any(v is None or not math.isfinite(v) for v in values):
        raise ValueError('axis_correction_pose_unobserved')
    # Axis errors wrap at +/-90 degrees, but those attitudes are outside
    # this small-correction controller's domain anyway.
    if max(values)-min(values)>AGREEMENT_RAD:
        raise ValueError('axis_correction_heading_disagreement')
    angle=-sum(values)/len(values)
    if not math.radians(1)<=abs(angle)<=math.radians(30):
        raise ValueError('axis_correction_outside_bounded_domain')
    return max(-MAX_YAW_RAD,min(MAX_YAW_RAD,angle))


def plans(localizers, teachers, angle, now):
    """Arc about the nominal beam midpoint, constant body twist per robot.

    A rigid held beam midpoint stays at the same body coordinate throughout
    this twist. Each wheel's integrated duty is preserved over shared 100 ms
    periods. Short duty is distributed across fewer periods, never rounded up.
    """
    from sim.visible_belief import rates
    from sim.grasp_act_release_teacher import check_wheels
    if not math.isfinite(angle) or not 0<abs(angle)<=MAX_YAW_RAD+1e-9:
        raise ValueError('axis_correction_angle_limit')
    required={}
    for rid,t in teachers.items():
        loc=localizers[rid]
        if not t.holding or not (loc.decision or {}).get('accepted'):
            raise ValueError('axis_correction_unconfirmed_input')
        (ex,ey),(ox,oy),_=t.end_and_outward(now)
        center=np.array([ex-.30*ox,ey-.30*oy])
        pose=np.asarray(loc.own.x,float)
        points=[]
        for theta in np.linspace(0,angle,11):
            rot=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
            delta=center-rot@center
            c,s=math.cos(pose[2]),math.sin(pose[2])
            points.append([pose[0]+c*delta[0]-s*delta[1],pose[1]+s*delta[0]+c*delta[1],pose[2]+theta])
        if not loc.global_matcher.free(np.asarray(points),extra_clearance=.15).all():
            raise ValueError('axis_correction_motion_clearance')
        ax,lat,yaw=rates(t.odometry_profile)
        f,l,a=center[1]*angle/ax,-center[0]*angle/lat,angle/yaw
        required[rid]=[f-l-a,f+l+a,f+l-a,f-l+a]
    periods=math.ceil(max(abs(v) for row in required.values() for v in row)/.1)
    out={}
    for rid,row in required.items():
        levels=[math.copysign(.35,v) if abs(v)>1e-12 else 0. for v in row]
        counts=[math.ceil(abs(v)/.1) if level else 0 for v,level in zip(row,levels)]
        durations=[abs(v)/n if n else 0. for v,n in zip(row,counts)]
        if any(0<d<.04 for d in durations):
            raise ValueError('axis_correction_pulse_window')
        out[rid]=[]
        for i in range(periods):
            active=[(i+1)*n//periods>i*n//periods for n in counts]
            w=[v if yes else 0. for v,yes in zip(levels,active)]
            d=[v if yes else 0. for v,yes in zip(durations,active)]
            check_wheels(w,d);out[rid].append((w,d))
        # Check the actual duty schedule too, including within-period arcs.
        from sim.visible_belief import odometry
        q=np.asarray(localizers[rid].own.x,float).copy();samples=[q.copy()]
        for w,d in out[rid]:
            elapsed=0.
            for stop in sorted(set([*d,.1])):
                active=[v if elapsed<limit-1e-9 else 0. for v,limit in zip(w,d)]
                dx,dy,da=odometry(active,stop-elapsed,teachers[rid].odometry_profile)
                c,s=math.cos(q[2]+da/2),math.sin(q[2]+da/2)
                q += [c*dx-s*dy,s*dx+c*dy,da]
                samples.append(q.copy());elapsed=stop
        if not localizers[rid].global_matcher.free(np.asarray(samples),extra_clearance=.15).all():
            raise ValueError('axis_correction_motion_clearance')
    return out
