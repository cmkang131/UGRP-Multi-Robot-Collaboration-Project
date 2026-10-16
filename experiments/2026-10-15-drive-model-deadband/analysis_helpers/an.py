import sys,json,math,os,statistics as st
sys.dont_write_bytecode=True
from lib import *
K035=1/.35
def m2(wheels,dur,dt):
    w0,w1,w2,w3=wheels
    f,l,t=(w0+w1+w2+w3)/4,(-w0+w1+w2-w3)/4,(-w0+w1-w2+w3)/4
    sec=max([min(dt,.1,d) if w else 0. for w,d in zip(wheels,dur)] or [0.])
    return f*K035*.129*sec,l*K035*.08*sec,t*K035*.35*sec
def body_delta(a,b):
    # GT body-frame delta from pose a to b (x,y,yaw|None)
    dx,dy=b[0]-a[0],b[1]-a[1]
    if a[2] is None: return math.hypot(dx,dy),None,None
    dyaw=wrap(b[2]-a[2]);h=a[2]+dyaw/2
    return dx*math.cos(h)+dy*math.sin(h),-dx*math.sin(h)+dy*math.cos(h),dyaw
def steps(ev_t,gt,cmds):
    """ev_t list, gt list of (x,y,yaw|None); cmds dict round(t,3)->(wheels,dur,tag)"""
    out=[]
    for i in range(1,len(ev_t)):
        ta,tb=ev_t[i-1],ev_t[i]
        c=cmds.get(round(ta,3))
        if c is None: continue
        wheels,dur,tag=c;dt=tb-ta
        g=body_delta(gt[i-1],gt[i])
        out.append(dict(ta=ta,tb=tb,dt=dt,w=wheels,d=dur,tag=tag,g=g,m1=cdelta(wheels,dur,min(.15,dt)),m2=m2(wheels,dur,dt),i=i))
    return out
def summarize(S,gt,start_yaw=None,has_yaw=True,min_move=.5):
    """per-robot stats for the step list S (all steps)"""
    gL=sum(math.hypot(s['g'][0],s['g'][1]) if has_yaw else s['g'][0] for s in S)
    i1=sum(math.hypot(s['m1'][0],s['m1'][1]) for s in S)
    i2=sum(math.hypot(s['m2'][0],s['m2'][1]) for s in S)
    r={'gt_path_m':gL,'m1_path_m':i1,'m2_path_m':i2}
    if has_yaw:
        r['gt_yaw_abs']=sum(abs(s['g'][2]) for s in S);r['m1_yaw_abs']=sum(abs(s['m1'][2]) for s in S);r['m2_yaw_abs']=sum(abs(s['m2'][2]) for s in S)
        r['gt_yaw_net']=sum(s['g'][2] for s in S);r['m1_yaw_net']=sum(s['m1'][2] for s in S);r['m2_yaw_net']=sum(s['m2'][2] for s in S)
    return r
def drift(S,gt,model='m1',yaw0=None):
    """open-loop integrate model from GT start pose, return list of position diff (m) per step end"""
    g0=gt[S[0]['i']-1];x,y,a=g0[0],g0[1],(g0[2] if g0[2] is not None else yaw0)
    D=[]
    for s in S:
        dx,dy,da=s[model]
        x+=math.cos(a)*dx-math.sin(a)*dy;y+=math.sin(a)*dx+math.cos(a)*dy;a+=da
        g=gt[s['i']]
        D.append((math.hypot(x-g[0],y-g[1]),(wrap(a-g[2]) if g[2] is not None else None)))
    return D
