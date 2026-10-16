"""Evaluator-only certified stance census; original authored plans unchanged."""
import sys,json,math
from pathlib import Path
from analyze_before import ROOT,OPS,read,data,write
sys.path.insert(0,str(ROOT/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'))
from sim.grasp_act_search24 import reachability_map
from sim.grasp_act_search18 import body_clearance
from sim.grasp_act_search21 import FRESH_MARGIN_M
from sim.zone_arena import BOX_HALF
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects

if __name__=='__main__':
    rows=[]
    summary=read(ROOT/'ops-reviews/beampair8/cohort-analysis-v2/summary.json')
    static,_,_=resolve('zone_wide_two_doors_final_v3'); walls=keepout_rects(static,perimeter=True)
    for entry in summary['runs']:
        raw=Path(entry['raw']);p=read(raw/'plan.json')
        first=json.loads(data(raw/'eval-only.jsonl').splitlines()[0]); x,y,a=first['beam']['pose']
        # Rectangles use known cargo dimensions; observed-sphere comparison uses
        # the measurement's actual 3D rbound and pinned 5mm cargo padding.
        objects={k:v for k,v in first['objects'].items() if k!='beam_1'}
        out={}
        for end in ('teal','blue'):
            g=first['beam']['ends'][end]; gs=[]
            for offset,d,_,_ in reachability_map(g[2]):
                yaw=a+(math.pi if end=='blue' else 0.)+offset
                pose=(g[0]-d*math.cos(yaw),g[1]-d*math.sin(yaw),yaw)
                gaps={k:body_clearance(pose,[],[(*o['xy'],*BOX_HALF[:2],0.)]) for k,o in objects.items()}
                gaps['static_walls']=body_clearance(pose,[],walls,bounds=static['bounds_m'])
                name,gap=min(gaps.items(),key=lambda v:v[1]);gs.append(dict(pose=pose,blocked_object=name,min_gap_m=gap))
            best=max(gs,key=lambda v:v['min_gap_m'])
            out[end]=dict(N=len(gs),free_N=sum(v['min_gap_m']>=FRESH_MARGIN_M for v in gs),best=best)
        rows.append(dict(seed=p['seed'],original_success=entry['strict_success'],raw=str(raw),ends=out,
            both_have_static_stance=all(v['free_N'] for v in out.values())))
    report=dict(scope='evaluator-only exact known cube rectangles + full static walls at original first saved state; finite certified family, not proof of all possible manipulation infeasibility',
        N=len(rows),both_have_static_stance_N=sum(r['both_have_static_stance'] for r in rows),
        zero_static_stance=[r for r in rows if not r['both_have_static_stance']],rows=rows,
        original_plans_unchanged=True,margin_m=FRESH_MARGIN_M,margin_basis='unchanged search21 geometric envelope',cube_half_extents_m=list(BOX_HALF))
    write(OPS/'static-census.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
