"""gcp1-only evaluator analysis of saved simalt2 engine outputs; no stepping."""
import argparse
import json
import math
from pathlib import Path
import socket
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('fixture','reference','candidate','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if socket.gethostname().split('.')[0]!='ugrp-sim-gcp1':p.error('gcp1 analysis only')
    import mujoco
    import numpy as np
    m=mujoco.MjModel.from_xml_path(str(a.fixture/'scene.xml'))
    meta=json.loads((a.fixture/'fixture.json').read_text())
    rr=json.loads((a.reference/'result.json').read_text());cc=json.loads((a.candidate/'result.json').read_text())
    r=np.load(a.reference/'states.npz');c=np.load(a.candidate/'states.npz')
    def addr(body):return int(m.jnt_qposadr[int(m.body_jntadr[m.body(body).id])])
    base=addr('r1__robot');box=addr('cargo_cyan_2')
    def angle(q1,q2):
        q1=q1/np.linalg.norm(q1,axis=-1,keepdims=True);q2=q2/np.linalg.norm(q2,axis=-1,keepdims=True)
        return np.degrees(2*np.arccos(np.clip(np.abs(np.sum(q1*q2,axis=-1)),0,1)))
    result={'reference':str(a.reference),'candidate':str(a.candidate),'cases':[],
            'threshold_basis':'unchanged exploratory simalt1 proposal: 5mm/2deg endpoint and 2mm extra 3s slip; not a research success gate',
            'candidate_complete':cc['status']=='complete','physics_hashes_equal':rr['physics_hashes']==cc['physics_hashes'],
            'reproduce':sys.argv,'accepted_for_expansion':False}
    for case in meta['cases']:
        name=case['name']
        if name not in c or len(c[name])==0:
            result['cases'].append({'name':name,'status':'not_measured'});continue
        n=min(len(r[name]),len(c[name]));rv=r[name][:n];cv=c[name][:n]
        row={'name':name,'sample_count':n,'complete':n==len(case['phases']),
             'base_endpoint_translation_m':float(np.linalg.norm(rv[-1,base:base+3]-cv[-1,base:base+3])),
             'base_endpoint_rotation_deg':float(angle(rv[-1,base+3:base+7],cv[-1,base+3:base+7])),
             'box_endpoint_translation_m':float(np.linalg.norm(rv[-1,box:box+3]-cv[-1,box:box+3])),
             'box_endpoint_rotation_deg':float(angle(rv[-1,box+3:box+7],cv[-1,box+3:box+7])),
             'base_max_translation_m':float(np.max(np.linalg.norm(rv[:,base:base+3]-cv[:,base:base+3],axis=1))),
             'box_max_translation_m':float(np.max(np.linalg.norm(rv[:,box:box+3]-cv[:,box:box+3],axis=1)))}
        row['exploratory_endpoint_pass']=(row['complete'] and row['base_endpoint_translation_m']<=.005
            and row['base_endpoint_rotation_deg']<=2 and row['box_endpoint_translation_m']<=.005
            and row['box_endpoint_rotation_deg']<=2)
        hold=[i for i,phase in enumerate(case['phases']) if phase=='hold' and i<n]
        if hold:
            row['hold_recorded_sim_s']=len(hold)*.1
            for label,values in [('reference',rv),('candidate',cv)]:
                row[label+'_box_hold_displacement_m']=float(np.linalg.norm(values[hold[-1],box:box+3]-values[max(0,hold[0]-1),box:box+3]))
            row['hold_extra_slip_m']=row['candidate_box_hold_displacement_m']-row['reference_box_hold_displacement_m']
            row['exploratory_hold_pass']=len(hold)==30 and row['hold_extra_slip_m']<=.002
        rp=a.reference/(name+'-contacts.json');cp=a.candidate/(name+'-contacts.json')
        if rp.is_file() and cp.is_file():
            rc=json.loads(rp.read_text());ct=json.loads(cp.read_text());pairs=min(len(rc),len(ct))
            row['contact_pair_samples_equal']=sum(rc[i]['pairs']==ct[i]['pairs'] for i in range(pairs))
            row['contact_pair_samples_compared']=pairs
            row['reference_minimum_contact_distance_m']=min(x['minimum_dist_m'] for x in rc if x['minimum_dist_m'] is not None)
            row['candidate_minimum_contact_distance_m']=min(x['minimum_dist_m'] for x in ct if x['minimum_dist_m'] is not None)
        result['cases'].append(row)
    result['accepted_for_expansion']=(cc['status']=='complete' and len(result['cases'])==4
        and all(x.get('exploratory_endpoint_pass',False) and x.get('exploratory_hold_pass',True) for x in result['cases'])
        and result['physics_hashes_equal'])
    a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
