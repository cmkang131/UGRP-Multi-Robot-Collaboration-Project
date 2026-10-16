"""Explain the frozen camera/load rejections; no relaxed acceptance decision."""
import collections
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np

from diagnose import RAW, ROOT, native, intervals


def main(dest):
    assert not dest.exists()
    folder=RAW['loaded']/'zone_wide_two_doors_final_v3'
    trace=[json.loads(l) for l in (folder/'eval_only/trajectory.jsonl').read_text().splitlines()]
    contacts=[json.loads(l) for l in (folder/'eval_only/contacts.jsonl').read_text().splitlines()]
    geom=ET.parse(folder/'scene.xml').getroot().find('.//geom[@name="cargo_beam__bar"]')
    size=np.fromstring(geom.get('size'),sep=' ');pos=np.fromstring(geom.get('pos'),sep=' ')
    t=np.array([r['t']-trace[0]['t'] for r in trace])
    bottom=[];bilateral=[];reasons=[]
    for tr,cr in zip(trace,contacts):
        R=np.array(tr['beam_rotation']).reshape(3,3)
        b=tr['beam_xyz_m'][2]+(R@pos)[2]-np.abs(R[2])@size
        touched=set();supported=False
        for c in cr['contacts']:
            if 'cargo_beam__bar' not in (c['geom1'],c['geom2']) or c['dist_m']>0:continue
            other=c['geom2'] if c['geom1']=='cargo_beam__bar' else c['geom1']
            if other in {rid+'__'+side+'_finger' for rid in ('r1','r2') for side in ('left','right')}:touched.add(other)
            else:supported=True
        held=len(touched)==4
        bottom.append(b);bilateral.append(held)
        reasons.append('not_lifted' if b<.01 else 'external_support' if supported else 'missing_bilateral_grip' if not held else 'lifted')
    bottom=np.array(bottom);bilateral=np.array(bilateral);reasons=np.array(reasons)
    result={'reason_counts':dict(collections.Counter(reasons.tolist())),
            'reason_intervals_relative_s':{key:intervals(reasons==key,t) for key in sorted(set(reasons))},
            'periods':[]}
    for name,lo,hi in [('grasp_pose',.2,4.),('hover_initial',4.2,12.),('motion',12.,330.),
        ('pan_center',334.,337.),('pan_1230',337.,340.),('pan_970',340.,343.),('pan_700',343.,346.),
        ('pan_1770',346.,349.),('pan_2030',349.,352.),('pan_2300',352.,355.),('center_return',355.,362.)]:
        sel=(t>=lo-1e-7)&(t<hi-1e-7)
        result['periods'].append({'name':name,'start_s':lo,'end_exclusive_s':hi,'samples':int(sel.sum()),
            'bottom_min_max_m':[float(bottom[sel].min()),float(bottom[sel].max())],
            'bilateral_samples':int(bilateral[sel].sum()),'reasons':dict(collections.Counter(reasons[sel].tolist()))})
    report=json.loads((folder.parents[2]/'final-pair-v88-measured-dryrun-20261003-035426/fit_report.json').read_text())
    reference=report['camera']['loaded']['807,1897,2187,1500']['optical']
    records=json.loads((dest.parent/'camera.json').read_text())
    residual=[]
    for rid in ('r1','r2'):
        ids=set(next(r['selected_frame_ids'] for r in records if r['profile']=='loaded' and r['robot']==rid and r['pose']=='807,1897,2187,1500'))
        labels=[json.loads(l) for l in (folder/f'eval_only/{rid}/camera_labels.jsonl').read_text().splitlines()]
        for row in labels:
            if row['frame_id'] not in ids:continue
            angle=np.degrees(np.arccos(np.clip((np.trace(np.array(row['rotation'])@np.array(reference['rotation']).T)-1)/2,-1,1)))
            residual.append({'robot':rid,'relative_s':row['t']-labels[0]['t'],'frame_id':row['frame_id'],
                'origin_residual_mm':np.linalg.norm(np.array(row['origin_m'])-reference['origin_m'])*1000,
                'rotation_residual_deg':angle})
    result['hover_residuals_to_unchanged_full_sample_median']=residual
    result['qualification']='Diagnostic times only; no subset promoted and frozen 1s settlement unchanged.'
    dest.write_text(json.dumps(result,indent=2,default=native)+'\n')


if __name__=='__main__':
    main(Path(sys.argv[1]))
