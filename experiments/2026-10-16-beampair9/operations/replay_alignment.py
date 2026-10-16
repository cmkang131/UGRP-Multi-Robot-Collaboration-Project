"""Own visible measurements/issued history only, GCP offline diagnostic.

Not a full teacher, FreeSpace/reobserver ghost, or physics replay. Test the
original minimum-width scalar axes against the native circle pulse predicate.
"""
import hashlib,json,math,sys,subprocess
from pathlib import Path
ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair9'
sys.path.insert(0,str(ROOT/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'))
def read_bytes(p):
    actual=p if p.exists() else Path(str(p)+'.zst')
    raw=actual.read_bytes()
    value=subprocess.check_output(['zstd','-qdc',str(actual)]) if actual.suffix=='.zst' else raw
    return value,actual,hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(read_bytes(p)[0])
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
from harness.grasp_act_visible_world import VisibleWorld,command_delta
from sim.grasp_act_visible_route import constraints
from sim.grasp_act_search17 import pulse_free
from sim.grasp_act_port import duty_wheels
from sim.grasp_act_teacher import local,wrap,STATION_M
from harness.static_keepouts import rect_distance

if __name__=='__main__':
    assert sys.platform=='linux'
    raw=ROOT/'runs/beampair8-record-8328015-72c0e83d/raw';t=read(raw/'result.json')['teachers']['r1']
    ev=[json.loads(x) for x in read_bytes(raw/'eval-only.jsonl')[0].splitlines()]
    commands=[json.loads(x)['applied_command'] for x in read_bytes(raw/'teacher-r1.jsonl')[0].splitlines()]
    model=VisibleWorld('r1','blue',odometry='search17_fixed_v1',search22='search22_v1',search23='search23_v1')
    for row,c in zip(ev,commands):world=model.observe(row['visible_measurements']['r1'],row['t']);model.issue(c)
    pose=world['robots']['r1']['pose'];g=world['beam']['ends']['blue'];x,y=local(pose,g)
    choice=t['goal_set_log'][-1]['selected']['choice'];heading=world['beam']['pose'][2]+math.pi+choice[0]
    errors=[x-t['staging_distance_m'],y,wrap(heading-pose[2])]
    radius,discs,rects=constraints(world,'r1',True)
    names=[r for r in world['robots'] if r!='r1']+[k for k in world['objects'] if k!='beam_1']+['beam_1']*5
    walls=[k for k,m in world['visibility']['r1']['observations'].items() if m['kind']=='wall']
    a=world['beam']['pose'][2];g0=world['beam']['ends']['teal']
    discs.append((g0[0]-STATION_M*math.cos(a),g0[1]-STATION_M*math.sin(a),.17+(.17-radius)))
    names+=['reserved:teal_stance'];axes=[]
    for axis,error in enumerate(errors):
        drive=[0.,0.,0.];drive[axis]=(.9,.9,.8)[axis]*error # unchanged native gains
        wheels,widths=duty_wheels([3*drive[0],3*drive[1],.65*drive[2]])
        value=dict(wheels=wheels,duration_s=[max(.04,d) if w else 0. for w,d in zip(wheels,widths)])
        checks=[]
        for mode in ('off','search17_fixed_v1'):
            dx,dy,_=command_delta(value,.1,mode=mode);c,s=math.cos(pose[2]),math.sin(pose[2])
            end=(pose[0]+c*dx-s*dy,pose[1]+s*dx+c*dy)
            blocked=[]
            for name,disc in zip(names,discs):
                if not pulse_free(pose,value,[disc],[],radius,mode=mode):
                    vx,vy=end[0]-pose[0],end[1]-pose[1];norm=vx*vx+vy*vy
                    u=max(0.,min(1.,((disc[0]-pose[0])*vx+(disc[1]-pose[1])*vy)/norm)) if norm else 0.
                    blocked.append(dict(blocked_object=name,min_gap_m=math.hypot(pose[0]+u*vx-disc[0],pose[1]+u*vy-disc[1])-disc[2]-radius,
                        start_gap_m=math.dist(pose[:2],disc[:2])-disc[2]-radius,reason_category='native_circle_pulse_rejection'))
            for name,rect in zip(walls,rects):
                if not pulse_free(pose,value,[],[rect],radius,mode=mode):
                    n=max(1,math.ceil(math.dist(pose[:2],end)/.001)) # native1mm sampling
                    gap=min(rect_distance((pose[0]+(end[0]-pose[0])*i/n,pose[1]+(end[1]-pose[1])*i/n),rect)-radius for i in range(n+1))
                    blocked.append(dict(blocked_object=name,min_gap_m=gap,reason_category='native_wall_pulse_rejection'))
            checks.append(dict(mode=mode,admitted=not blocked,blockers=blocked))
        axes.append(dict(axis=axis,error=error,pulse=value,checks=checks))
    result=dict(seed=8328015,raw=str(raw),pose=pose,local_assigned_end=[x,y,g[2]],errors=errors,axis_checks=axes,
        logged_alignment_axes_blocked_N=sum(e['event']=='alignment_axes_blocked' for e in t['search20_log']),
        scope=__doc__,source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reproduce=str(Path(__file__).resolve()))
    dump(OPS/'alignment15-visible-world-replay-v2.json',result)
    accepted=sum(c['admitted'] for axis in axes for c in axis['checks'])
    dump(OPS/'alignment15-diagnostic-funnel.json',dict(N=6,passed=accepted,rejected=6-accepted,
        population='three hypothetical scalar pulses x two original issued models; not actual issued actions',
        raw=str(raw),reproduce=result['reproduce'],source_script_sha256=result['source_script_sha256']))
    print(json.dumps(dict(N=6,admitted=accepted,rejected=6-accepted,blockers=[c['blockers'] for v in axes for c in v['checks'] if c['blockers']])))
