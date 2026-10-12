"""Compare heading decisions on fixed recorded poses/paths; no simulation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from harness.own_map_heading import command as baseline
from harness.e2e_rpp_path import command as candidate
from harness.self_pulse_rotation import selected_model


def replay(path):
    data=json.loads(path.read_text())
    records={x['heading']['t']:x['heading'] for x in data['records'] if x.get('heading')}
    profiles=selected_model('s2_pulse_v122_rotL_v1')['profiles'];out={}
    for mode in ('off','rpp_v1'):
        actions=[];distances=[];matches=[]
        for row in records.values():
            plan=dict(coordinate_frame='r2/own_odom',status='frontier',path_m=row['path'],heading_rad=row['pose'][2])
            if mode=='off':a=baseline(plan,row['pose'],profiles,robot_id='r2')
            else:
                a,info=candidate(plan,row['pose'],profiles,robot_id='r2')
                distances.append(info['carrot_distance_m'])
            actions.append(a);matches.append(a==row['action'])
        signs=[math.copysign(1,a['turn']) for a in actions if a.get('turn')]
        out[mode]=dict(frames=len(actions),turns=sum(bool(a.get('turn')) for a in actions),
            forward=sum(a.get('forward',0)>0 for a in actions),holds=sum(a['kind']=='hold' for a in actions),
            turn_sign_flips=sum(a!=b for a,b in zip(signs,signs[1:])),matches_actual=sum(matches),
            carrot_range_m=[min(distances),max(distances)] if distances else None)
    assert out['off']['matches_actual']==out['off']['frames']==56
    return dict(source_run='e2e9-a-s61003',robot='r2',source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        scope='fixed saved inputs; proposed commands not executed; no closed-loop success evidence',results=out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
    print(json.dumps(replay(a.source),indent=2))
