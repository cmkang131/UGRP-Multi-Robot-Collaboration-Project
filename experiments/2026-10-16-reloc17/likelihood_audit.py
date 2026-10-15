"""Saved-RGB observation audit on GCP2. Truth is residual-scoring only."""
import hashlib,json,math,os,platform
from pathlib import Path
import cv2,numpy as np
from scripts.analyze_reloc11_selfmap import rows
from harness.selfmap4_geometry import static_input,observe
from harness.e2e_static_rgb_localizer import create
from harness.self_map_landmark_sensor import Sensor
from harness.self_map_csm import sample_segments
from harness.natural_floor_slam import transform,wrap
from harness.own_map_amcl_vendor import field

def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    root=Path('/home/ugrp/ugrp-sim/runs');out=root/'reloc17-investigation';records=[]
    cal=Path(__file__).resolve().parents[2]/'experiments/2026-10-16-reloc16/colour-calibration.json'
    os.environ.update(UGRP_SCENE_COLOUR_BOUNDARY='scene_colour_transition_v2',UGRP_SCENE_RENDER_PROFILE='walls_floor_contrast_v5_indigo110_s80',UGRP_SCENE_COLOUR_CALIBRATION=str(cal),UGRP_SCENE_COLOUR_CALIBRATION_SHA256=hashlib.sha256(cal.read_bytes()).hexdigest(),UGRP_RELOC16_FLOOR_LANDMARK_MASK='scene_floor_landmark_mask_v1')
    static,_=static_input();pf=create(static,option='static_landmarks_v1',seed=5064);sensor=Sensor(pf.landmark_map.hues)
    for seed in (93584,93583):
        raw=root/f'reloc16-r3-selfmap-{seed}-v5-df8115a5/raw';trace=rows(raw/'trace.jsonl');frames=rows(raw/'robots/r3/frames.jsonl');truth={round(r['t'],6):r for r in rows(raw/'eval_only/trajectory.jsonl')}
        candidates=[(r,f) for r,f in zip(trace,frames) if r.get('static_registration',{}).get('updated')]
        # Deterministic coverage over the full saved trajectory, no outcome selection.
        for idx in np.unique(np.linspace(0,len(candidates)-1,12,dtype=int)):
            r,f=candidates[idx];p=raw/f['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
            image=cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB);servo={int(k):v for k,v in f['commanded_servo'].items()}
            obs=observe(image,servo,sensor);points=sample_segments(obs['segments'])
            gt=truth[round(r['t'],6)];actual=np.array([*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']]);d=pf.field.distances(transform(points,actual))
            # Evaluator diagnostic curve: actual xy fixed, yaw offsets in existing
            # 5-degree task units. These poses are NEVER sent into a live PF.
            offsets=np.deg2rad(np.arange(-6,7)*5);poses=np.tile(actual,(len(offsets),1));poses[:,2]+=offsets
            c,s=np.cos(poses[:,2,None]),np.sin(poses[:,2,None])
            xy=np.stack((poses[:,0,None]+c*points[None,:,0]-s*points[None,:,1],poses[:,1,None]+s*points[None,:,0]+c*points[None,:,1]),axis=-1)
            distance=pf.field.distances(xy)
            pz=field.PARAMS['z_hit']*np.exp(-distance**2/(2*field.PARAMS['sigma_hit_m']**2))+field.PARAMS['z_rand']/field.PARAMS['range_max_m']
            cubic=np.log(1+(pz**3).sum(1));logproduct=np.log(pz).sum(1)
            records.append(dict(seed=seed,t=r['t'],image=str(p),sha256=f['sha256'],wall_points=len(points),distance_at_truth_m=d.tolist(),
                yaw_offset_deg=np.rad2deg(offsets).tolist(),cubic_loglikelihood=cubic.tolist(),prob_loglikelihood=logproduct.tolist(),
                cubic_best_yaw_offset_deg=float(np.rad2deg(offsets[np.argmax(cubic)])),prob_best_yaw_offset_deg=float(np.rad2deg(offsets[np.argmax(logproduct)]))))
    def dist(v):return {k:float(x) for k,x in zip(('p0','p50','p95','max'),np.percentile(v,[0,50,95,100]))} if v else {}
    summary=[]
    for seed in (93584,93583):
        rs=[r for r in records if r['seed']==seed];ds=[d for r in rs for d in r['distance_at_truth_m']]
        summary.append(dict(seed=seed,N=len(rs),wall_endpoint_residual_m=dist(ds),wall_point_count=dist([r['wall_points'] for r in rs]),
            cubic_best_yaw_offsets_deg=[r['cubic_best_yaw_offset_deg'] for r in rs],prob_best_yaw_offsets_deg=[r['prob_best_yaw_offset_deg'] for r in rs],
            cubic_curve_log_range=dist([max(r['cubic_loglikelihood'])-min(r['cubic_loglikelihood']) for r in rs]),prob_curve_log_range=dist([max(r['prob_loglikelihood'])-min(r['prob_loglikelihood']) for r in rs])))
    data=dict(analysis_host='gcp2',scope='evaluation-only same saved RGB, known-map endpoint residual and yaw likelihood curve; not a PF replay or closed-loop result',parameters=field.PARAMS,summary=summary,frames=records)
    (out/'likelihood-audit.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(summary))

if __name__=='__main__':main()
