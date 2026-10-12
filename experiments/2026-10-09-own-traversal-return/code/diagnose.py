"""Post-seal GT diagnosis only; never imported by graph/controller."""
from offline import BASE,RAW,EXP,load,rows,dump,compose,wrap
import math
from collections import Counter
import numpy as np


def main():
    out=[]
    for seed in range(49001,49007):
        p=load(RAW/str(seed)/'prediction.json');r=load(EXP/'results'/f'{seed}.json');g=p['graph'];ep=BASE/f'seed{seed}'
        truth=rows(ep/'eval_only/trajectory.jsonl');gt=np.array([[*v['robot_xyz_m'][:2],v['robot_yaw_rad']] for v in truth]);times=np.array([v['t'] for v in truth]);origin=gt[0]
        counts={label:{k:sum(e[label][k] for e in r['edges_audit']) for k in ('center_crossing_segments','center_segments','footprint_overlap_samples','footprint_samples')} for label in ('estimated','actual')}
        badtimes=[]
        if g['goal_node'] is not None:
            target=g['nodes'][g['goal_node']];badtimes=[b for b in g['breaks'] if b['t']>target['t']]
        groups=[]
        for b in badtimes:
            if groups and b['t']-groups[-1]['end']<=.201:groups[-1]['end']=b['t'];groups[-1]['frames']+=1
            else:groups.append(dict(start=b['t'],end=b['t'],frames=1,reason=b['reason']))
        last_t=max(n['t'] for n in g['nodes']);passages=load(ep/'inputs/static_map.json')['passages'];cross=[]
        for i,(a,b) in enumerate(zip(gt,gt[1:])):
            if times[i+1]>last_t:break
            for d in passages:
                ax=0 if d['axis']=='x' else 1;c=np.array(d['center_m'])
                if (a[ax]-c[ax])*(b[ax]-c[ax])<0:
                    u=(c[ax]-a[ax])/(b[ax]-a[ax]);hit=a[:2]+u*(b[:2]-a[:2])
                    if abs(hit[1-ax]-c[1-ax])<d['width_m']/2:cross.append(dict(id=d['id'],t=float(times[i]+u*(times[i+1]-times[i])),point=hit.tolist()))
        match_error=None
        if p['match'] and p['match']['status']=='accepted':
            pred=compose(origin,p['match']['pose']);idx=np.argmin(abs(times-p['query']['t']));match_error=dict(xy_m=float(np.linalg.norm(pred[:2]-gt[idx,:2])),yaw_deg=abs(float(wrap(pred[2]-gt[idx,2])))*180/math.pi)
        first_translation=None
        if groups:
            a,b=[np.argmin(abs(times-t)) for t in (groups[0]['start']-.2,groups[0]['start']+.4)]
            first_translation=float(np.linalg.norm(gt[a,:2]-gt[b,:2]))
        v=dict(seed=seed,frames=r['frames'],nodes=r['nodes'],edges=r['edges'],components=r['components'],breaks=r['breaks'],break_reasons=r['break_reasons'],B_node=r['B_node'],B_component_size=r['B_component_size'],last_component_size=r['last_component_size'],route=r['route_exists'],match=None if p['match'] is None else p['match']['reason'],match_eval=match_error,all_edges_audit=counts,first_B_following_break=groups[0] if groups else None,break_intervals_after_B=groups,first_break_translation_06s_m=first_translation,actual_door_crossings=cross)
        out.append(v)
    dump(EXP/'results/diagnosis.json',out)
    return out

if __name__=='__main__':main()
