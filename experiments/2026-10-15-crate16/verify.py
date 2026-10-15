"""Reproduce crate16 offline claims on five saved runs. No physics/remote.

New actions are never used to invent subsequent observations. The opt-in
replay is teacher-forced on ORIGINAL issued commands, not a physical rollout.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent/'2026-10-15-crate15'))
from replay import RAW, js, replay, read   # installs the physics/render prohibitions
from sim.crate_motion_v16 import Navigation, MODE, rectangle_gap
from sim.crate_navigation_v12 import FOOTPRINT
from sim.cargo_teacher_profile import CRATE
from sim.grasp_act_goal_set import geometry
from harness.static_keepouts import polygon_at, rect_corners
from sim.crate_grasp_teacher import CrateGraspTeacher

ANALYSIS = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate15-8007db00')
RUNS = ('crate-reproduction-77990-8007db00','crate-reproduction-79314-8007db00',
        'crate-reproduction-79317-8007db00','crate-diag-79450-8007db00','crate-diag-79451-8007db00')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values):
    v = sorted(values)
    return {'n':len(v),'min':v[0] if v else None,'p50':v[len(v)//2] if v else None,
            'p95':v[min(len(v)-1,int(len(v)*.95))] if v else None,'max':v[-1] if v else None,
            'sum':sum(v)}


def polygon_distance(a,b):
    """Independent vertex/edge distance; zero for overlap, as Sonnet review."""
    def cross(p,q,r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def inside(p,poly):
        v=[cross(poly[i],poly[(i+1)%4],p) for i in range(4)]
        return all(x>=0 for x in v) or all(x<=0 for x in v)
    if any(inside(p,b) for p in a) or any(inside(p,a) for p in b): return 0.
    for i in range(4):
        for j in range(4):
            p,q,r,s=a[i],a[(i+1)%4],b[j],b[(j+1)%4]
            if cross(p,q,r)*cross(p,q,s)<0 and cross(r,s,p)*cross(r,s,q)<0: return 0.
    def distance(p,q,r):
        dx,dy=r[0]-q[0],r[1]-q[1]
        u=max(0.,min(1.,((p[0]-q[0])*dx+(p[1]-q[1])*dy)/(dx*dx+dy*dy)))
        return math.hypot(p[0]-q[0]-u*dx,p[1]-q[1]-u*dy)
    return min([distance(p,b[i],b[(i+1)%4]) for p in a for i in range(4)]+
               [distance(p,a[i],a[(i+1)%4]) for p in b for i in range(4)])


def route_minimum(nav, route, heading):
    worst=math.inf
    yaws=[nav.pose[2]]+[nav.heading_at(p,heading) for p in route[1:-1]]+[heading]
    obstacles=[(r,rect_corners(r)) for _,r in nav.rectangles]
    for (a,b),(ya,yb) in zip(zip(route,route[1:]),zip(yaws,yaws[1:])):
        da=math.atan2(math.sin(yb-ya),math.cos(yb-ya))
        n=max(1,math.ceil(math.dist(a,b)/.002),math.ceil(abs(da)/math.radians(.5)))
        for i in range(n+1):
            p=(a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n,ya+da*i/n)
            own=None
            for rect,poly in obstacles:
                if rectangle_gap(p,rect,0.)>=worst: continue
                if own is None: own=polygon_at(p,FOOTPRINT)
                worst=min(worst,polygon_distance(own,poly))
    return worst*1000


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    source_hashes={}; baseline=[]; timings=[]; tick_rows=[]; routes=[]
    for name in RUNS:
        raw=RAW/name/'raw'
        for filename in ('result.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl'):
            path=raw/filename
            if not path.exists(): path=Path(str(path)+'.zst')
            source_hashes[str(path)]=sha(path)
        r=replay(name);r.pop('teachers');baseline.append(r)
        assert r['matched']==r['total'],r
        starts={}; times={}; prepare_times={}; first_t=None
        original_prepare=CrateGraspTeacher.prepare_signal
        def timed_prepare(self,world,now):
            at=time.perf_counter()
            value=original_prepare(self,world,now)
            prepare_times[(self.rid,now)]=time.perf_counter()-at
            return value
        def hook(stage,i,now,rid,t,w,plain,ev,*rest):
            nonlocal first_t
            if first_t is None: first_t=now
            if stage=='pre': starts[(rid,i)]=time.perf_counter()
            else:
                elapsed=time.perf_counter()-starts[(rid,i)]
                prepare_s=prepare_times[(rid,now)]
                times[(rid,i)]=elapsed+prepare_s
                tick_rows.append({'run':name,'tick':i,'robot':rid,'t':now,'sim_elapsed_s':now-first_t,
                    'teacher_compute_s':elapsed+prepare_s,'teacher_step_s':elapsed,'teacher_prepare_s':prepare_s,
                    'first30':now-first_t<=30.,
                    'navigation':[n.stats for n in t.navigation_cache.values()]})
        CrateGraspTeacher.prepare_signal=timed_prepare
        try: r=replay(name,hook=hook,options={'crate_motion':MODE})
        finally: CrateGraspTeacher.prepare_signal=original_prepare
        outcomes={rid:{'phase':t.phase,'outcome':t.outcome} for rid,t in r.pop('teachers').items()}
        row={'run':name,'teacher_compute_s':distribution(list(times.values())),
            'first30_teacher_compute_s':distribution([v['teacher_compute_s'] for v in tick_rows if v['run']==name and v['first30']]),
            'teacher_forced_outcomes':outcomes,
            'changed_command_ticks':r['total']-r['matched'],'total_ticks':r['total'],'audit':r['audit']}
        timings.append(row);print(json.dumps(row),flush=True)
        wp=ANALYSIS/(name+'-worlds.json');source_hashes[str(wp)]=sha(wp)
        worlds=json.loads(wp.read_text());res=js(raw/'result.json')
        for rid,diag in res['prefix']['teachers'].items():
            end=res['prefix']['assigned'][rid]
            for call in diag['goal_set_log']:
                world=min(worlds[rid],key=lambda w:abs(w['t']-call['t']))
                for candidate in call['candidates']:
                    if candidate['reason']!='no_path': continue
                    choice=(math.radians(candidate['offset_deg']),candidate['distance_m'])
                    _,_,heading,goal=geometry(world,rid,end,choice)
                    nav=Navigation(world,rid,True,CRATE,(-20,20,-20,20),end=end)
                    at=time.perf_counter();path=nav.path(nav.pose[:2],goal,heading);duration=time.perf_counter()-at
                    routes.append({'run':name,'robot':rid,'t':call['t'],'choice':choice,'path_found':bool(path),
                        'path_s':duration,'pad_m':nav.stats['path_pads_m'][-1] if path else None,
                        'minimum_physical_rectangle_gap_mm':route_minimum(nav,path,heading) if path else None,
                        'expansions':nav.stats['expansions']})
    baseline_n=sum(v['total'] for v in baseline);assert baseline_n==1424
    # The review's empty, unreachable goal used to search 4000 heap entries.
    w={'t':1.,'robots':{'r1':{'pose':[0.,0.,0.]}},'objects':{},'walls':[(1.5,0.,.02,10.,0.)],
       'beam':None,'visibility':{'r1':{'visible_probes':0,'objects':[],'peers':[]}}}
    nav=Navigation(w,'r1',True,CRATE,(-20,20,-20,20));at=time.perf_counter()
    path=nav.path((0.,0.),(2.4,0.),0.);unreachable_s=time.perf_counter()-at
    assert path is None
    ticks=a.output/'ticks.jsonl';ticks.write_text(''.join(json.dumps(v)+'\n' for v in tick_rows))
    detail=a.output/'route-retests.json';detail.write_text(json.dumps(routes,indent=2)+'\n')
    summary={'scope':'offline saved inputs only; opt-in timings use teacher-forced ORIGINAL issued history; no rollout/success claim',
        'baseline':baseline,'baseline_matched':sum(v['matched'] for v in baseline),'baseline_total':baseline_n,
        'timings':timings,'all_teacher_compute_s':distribution([v['teacher_compute_s'] for v in tick_rows]),
        'route_retests':len(routes),'routes_found':sum(v['path_found'] for v in routes),
        'route_minimum_gap_mm':distribution([v['minimum_physical_rectangle_gap_mm'] for v in routes if v['path_found']]),
        'preferred_pad_counts':dict(Counter(str(v['pad_m']) for v in routes if v['path_found'])),
        'unreachable_goal':{'path_found':False,'path_s':unreachable_s,'stats':nav.stats},
        'source_sha256':source_hashes,'detail_sha256':{str(ticks):sha(ticks),str(detail):sha(detail)},
        'ci_baseline_d3571214':'CI 미실행','physical_runs':0,'render_calls':0,'remote_connections':0,'model_calls':0}
    (a.output/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('baseline','timings','source_sha256')},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
