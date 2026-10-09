"""Post-outcome, evaluation-only explanation of the sealed selected mode.

Compare component scores at the latest nonempty own sensor packet preceding
the first confidence declaration. No particles, optimization or replay here.
This is a local score comparison, not a causal ablation or proposed tuning.
"""
import sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from harness.ownmap_s2 import GridField, mapped_landmarks, bounded_landmark_likelihood
from harness.zone_solo_cyan_likelihood_field import Field
from harness.zone_solo_cyan_landmarks import MapFeatures, landmark_likelihood
from harness.zone_solo_cyan_amcl_sensor import likelihood
from scripts.evaluate_ownmap_s2 import to_world,to_own,TreeField,truth_arrays,interpolate
from scripts.replay_ownmap_s2 import PLAN,read,rows,write


def evaluate(raw,evaluation):
    result=read(evaluation/'result.json');plan=read(PLAN);out=[]
    for p,r in zip(plan['pairs'],result['pairs']):
        assert p['id']==r['pair_id']
        path=raw/p['id']/'own_grid_v1';first=r['own_grid_v1']['first_convergence']
        if first is None:
            out.append(dict(pair_id=p['id'],available=False));continue
        packets=read(path/'measurements.json')['rows']
        packet=next(q for q in reversed(packets) if q['t']<=first['t']+1e-8 and (q['wall_count'] or q['features']))
        pose=next(q for q in rows(path/'poses.jsonl') if abs(q['t']-packet['t'])<1e-8)
        own=read(path/'own-map.json');field=GridField(own);mapped=mapped_landmarks(own)
        truth=truth_arrays(rows(Path(p['raw'])/'eval_only/trajectory.jsonl'))
        assert truth[0][0]<=packet['t']<=truth[0][-1]
        actual=interpolate(truth,[packet['t']])[0]
        a=rows(Path(p['map_raw'])/'eval_only/trajectory.jsonl')[0]
        anchor=np.r_[a['robot_xyz_m'][:2],a['robot_yaw_rad']]
        local=np.r_[to_own(actual[:2],anchor),actual[2]-anchor[2]]
        selected=np.array([pose['x'],pose['y'],pose['yaw']])
        world=np.r_[to_world(selected[:2],anchor),selected[2]+anchor[2]]
        static=read(Path(p['raw'])/'inputs/static_map.json');gt=Field(static)
        yy,xx=np.nonzero(gt.dist==0);points=gt.origin+np.c_[xx,yy]*gt.res
        grid=np.asarray(own['occupancy_grid']['cells']);res=own['occupancy_grid']['resolution_m']
        occupied=to_world((grid[grid[:,2]>0,:2]+.5)*res,anchor)
        support=TreeField(points[cKDTree(occupied).query(points)[0]<=.4])
        class Mixed:
            def distances(self,ps):
                return np.minimum(field.distances(to_own(ps,anchor)),support.distances(ps))
        local_pair=np.array([selected,local]);world_pair=np.array([world,actual])
        walls=np.asarray(packet['wall_points']).reshape(-1,2);features=packet['features']
        components={
            'own_wall':likelihood(field,local_pair,walls),
            'own_landmarks':bounded_landmark_likelihood(mapped,local_pair,features),
            'own_plus_supported_gt_wall':likelihood(Mixed(),world_pair,walls),
            'full_gt_wall':likelihood(gt,world_pair,walls),
            'full_gt_landmarks':landmark_likelihood(MapFeatures(static),world_pair,features)}
        contrasts={k:float(np.log(max(v[0],1e-300))-np.log(max(v[1],1e-300))) for k,v in components.items()}
        assert all(np.isfinite(list(contrasts.values())))
        out.append(dict(pair_id=p['id'],available=True,wrong_mode=r['own_grid_v1']['wrong_mode'],
            declaration_t=first['t'],packet_t=packet['t'],wall_points=len(walls),
            floor_features=sum(f['kind']=='floor_line' for f in features),
            selected_over_true_log_score=contrasts,
            positive_means='this packet favors the sealed selected pose over GT pose; not posterior evidence',
            scope='POST_OUTCOME_EVALUATION_ONLY; same saved packet, no PF, no parameter selection'))
    write(evaluation/'mode-score-diagnostic.json',dict(scope=__doc__,pairs=out))
    return out


if __name__=='__main__':
    import json
    print(json.dumps(evaluate(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
