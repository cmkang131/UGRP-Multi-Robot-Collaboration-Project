"""s2v39 same fixed command/RGB replay; GT loaded only by score()."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np

from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_best_cluster import runtime_class as best_runtime, OPTION as BEST
from harness.zone_solo_cyan_amcl_sensor import runtime_class as sensor_runtime, OPTION as SENSOR, likelihood
from harness.zone_solo_cyan_landmarks import runtime_class as landmark_runtime, OPTION, MapFeatures, landmark_likelihood
from harness.zone_solo_cyan_likelihood_field import Field
from harness import zone_solo_cyan_contract_v106 as contract

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('saved_sensor_replay',HERE/'replay_amcl_sensor.py')
saved=importlib.util.module_from_spec(spec);spec.loader.exec_module(saved)
old=saved.old;read,rows,sha=old.read,old.rows,old.sha
CRITERIA=HERE/'landmarks-criteria.json'


def replay(which,option,out,criteria):
    instances=[]
    def factory(base):
        Runtime=landmark_runtime(sensor_runtime(best_runtime(base)))
        def create(*args,pose_estimate,**kwargs):
            r=Runtime(*args,pose_estimate=BEST,sensor_model=SENSOR,
                sensor_landmarks=OPTION if option=='on' else 'off',**kwargs)
            instances.append(r);return r
        return create
    bind(old.replay,runtime_class=factory,CRITERIA=CRITERIA)(which,option,out,criteria)
    audit=dict(option=OPTION if option=='on' else 'off',gt_inputs=False,
        landmarks=copy.deepcopy(getattr(instances[0],'landmark_audit',None)))
    (out/f'{which}-{option}-landmarks.json').write_text(json.dumps(audit)+'\n')


def score(out,criteria):
    # Reuse scalar-only scorer AFTER all four prediction files close. Its wall
    # probe is retained separately; the new paired landmark probe is below.
    bind(saved.score,CRITERIA=CRITERIA)(out,criteria)
    result=read(out/'result.json');result['schema']='ugrp.s2.landmarks.result.v1'
    static=contract.hp.resolve(contract.MAP_ID)[0];mapped=MapFeatures(static);field=Field(static)
    probe=read(Path(criteria['likelihood_probe']['source']))
    particles=np.array([probe['views'][0]['truth'],criteria['likelihood_probe']['fixed_false_pose']])
    observations=read(out/'start1052-on-landmarks.json')['landmarks']['rows'];details=[]
    for view in probe['views']:
        observed=min(observations,key=lambda r:abs(r['t']-view['t']))
        assert abs(observed['t']-view['t'])<1e-6
        wall=likelihood(field,particles,view['points'])
        feature=landmark_likelihood(mapped,particles,observed['features'])
        details.append(dict(t=view['t'],features=observed['features'],wall_GT_over_false=float(wall[0]/wall[1]),
            feature_GT_over_false=float(feature[0]/feature[1]),joint_GT_over_false=float(wall[0]*feature[0]/(wall[1]*feature[1]))))
    result['landmark_probe']=dict(views=details,product_joint_ratio=float(np.prod([x['joint_GT_over_false'] for x in details])))
    for case in criteria['recordings']:
        audit=read(out/f'{case}-on-landmarks.json')['landmarks']
        result['recordings'][case]['landmark_counts']=dict(attempts=len(audit['rows']),updates=len(audit['measured']),
            floor_lines=sum(sum(f['kind']=='floor_line' for f in r['features']) for r in audit['rows']),
            doors=sum(sum(f['kind']=='door' for f in r['features']) for r in audit['rows']),
            feature_updates=sum(r['features']>0 for r in audit['measured']))
    result['hashes']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='result.json'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(gates=result['gates'],landmark_probe=result['landmark_probe'],metrics=result['recordings'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--score',action='store_true');p.add_argument('--recording',choices=('start1052','carry1051'))
    a=p.parse_args();criteria=read(CRITERIA);a.output.mkdir(parents=True,exist_ok=True)
    if a.score:
        assert not (a.output/'result.json').exists();score(a.output,criteria)
    else:
        for case in ([a.recording] if a.recording else criteria['recordings']):
            for opt in ('off','on'):
                assert not (a.output/f'{case}-{opt}.json').exists()
                replay(case,opt,a.output,criteria)
