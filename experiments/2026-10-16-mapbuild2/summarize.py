"""GCP2-only finite evidence reduction; no actor, model API, or simulator step."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith('ugrp-act-l4-gcp2'):raise ValueError('GCP2_L4_ONLY')
    root=Path('/home/ugrp/ugrp-sim/runs/mapbuild2');out=root/'delivery-v1';out.mkdir(exist_ok=False)
    sys.path.insert(0,'/home/ugrp/ugrp-sim/src/mapbuild2-ef0dd1d7')
    from harness.e2e_rgb_vo import between,PARAMS
    from harness.natural_floor_slam import Options
    captured=read(root/'capture-r4/summary.json');analysis=read(root/'analysis-r1/summary.json')
    corrected=read(root/'projection-eval-r1/scores.json');labels=read(root/'projection-eval-r1/labels.json')
    trajectories={name:read(root/'analysis-r1'/file) for name,file in {
        'legacy':'legacy-trajectory.json','orange-columns-fast7':'orange-columns-fast7-trajectory.json','command':'command-trajectory.json'}.items()}
    maps={p.name.removesuffix('-predicted-score.json'):read(p) for p in (root/'map-r3').glob('*-score.json')}
    camera=read(root/'camera-eval-r2.json')['summary'];truth={(r['sequence'],r['frame_id']):r['pose'] for r in labels['frames']}
    phases=[]
    for name in dict.fromkeys(r['sequence'] for r in labels['frames']):
        for start,end,axis in ((10,20,'forward'),(20,30,'left'),(30,40,'turn')):
            true=between(truth[name,start],truth[name,end]);methods={}
            for method,rows in trajectories.items():
                poses={r['frame_id']:r['lk_pose'] for r in rows if r['sequence']==name}
                delta=between(poses[start],poses[end]);denom=true[2] if axis=='turn' else np.linalg.norm(true[:2])
                numerator=delta[2] if axis=='turn' else np.linalg.norm(delta[:2])
                methods[method]=dict(delta=delta.tolist(),scale_ratio=float(numerator/denom) if denom!=0 else None,
                    scale_basis='signed yaw' if axis=='turn' else 'translation norm')
            phases.append(dict(sequence=name,axis=axis,sim_range=[start/10,end/10],truth_delta=true.tolist(),methods=methods))
    orb=[dict(sequence=r['sequence'],config=r['config'],pairs=r['pairs'],features_p50=r['feature_a']['p50'],
        ratio_p50=r['ratio']['p50'],mutual_p50=r['mutual']['p50'],ransac_p50=r['ransac']['p50'],
        stages=r['stages'],reasons=r['reasons']) for r in analysis['orb']]
    funnels=[]
    for candidate,rows in list(trajectories.items())[:2]:
        pairs=[r for r in rows if r['frame_id']!=0];qualified=[r for r in pairs if not r['lk']['status'].startswith('unknown_camera')]
        for method in ('lk','slam'):
            support=[r for r in qualified if (r['lk'].get('tracks',0)>=PARAMS['min_tracks'] if method=='lk' else r['slam']['features']>=Options().min_matches)]
            passed=[r for r in support if (r['lk']['status']=='measured' if method=='lk' else r['slam']['status'] in ('visual_update','visual_relocalized'))]
            values=[('pairs',len(pairs)),('qualified_camera',len(qualified)),('feature_support',len(support)),('geometric_tracking',len(passed))]
            previous=len(pairs);stages=[]
            for stage,n in values:stages.append(dict(stage=stage,cumulative_pass_n=n,rejected_n=previous-n));previous=n
            reasons=Counter(r['lk']['status'] if method=='lk' else r['slam']['reason'] for r in pairs if r not in passed)
            funnels.append(dict(candidate=candidate,method=method,unit='pair',stages=stages,reasons=dict(reasons)))
    cell_funnels=[]
    for name,result in maps.items():
        pred=read(root/'map-r3'/(name+'-predicted.json'));correct=result['observed_truth_cells']-result['wrong_free_cells']-result['occupied_fp']
        cell_funnels.append(dict(sequence=name,unit='predicted_grid_cell',stages=[
            dict(stage='predicted',cumulative_pass_n=len(pred['cells']),rejected_n=0),
            dict(stage='inside_truth_domain',cumulative_pass_n=result['observed_truth_cells'],rejected_n=result['out_of_truth_cells']),
            dict(stage='correct_occupancy_label',cumulative_pass_n=correct,rejected_n=result['wrong_free_cells']+result['occupied_fp'])]))
    full_funnel=dict(raw=str(root),reproduction=dict(capture=read(root/'capture-r4-exit.json')['command'],
        replay=read(root/'analysis-r1-queue.json'),mapping=read(root/'map-r3-queue.json')),
        tracking=funnels,map_frames=read(root/'map-r3/rejection-table.json'),map_cells=cell_funnels,
        rejection_fields='raw trajectories/events retain category/reason/blocked_object/minimum_gap_m/gap_status')
    dump(out/'all-gates-funnel.json',full_funnel)
    dump(out/'tracking-scores.json',corrected);dump(out/'command-phase-scale.json',phases)
    dump(out/'orb-table.json',orb);dump(out/'camera-summary.json',camera);dump(out/'map-scores.json',maps)
    raw_manifest=root/'capture-r4/SHA256SUMS.json';entries=read(raw_manifest);mismatches=[]
    for relative,expected in entries.items():
        path=root/'capture-r4'/relative
        if not path.is_file() or digest(path)!=expected:mismatches.append(relative)
    if mismatches:raise ValueError('RAW_HASH_MISMATCH:'+repr(mismatches))
    dump(out/'artifact-receipts.json',dict(raw_manifest=str(raw_manifest),raw_manifest_sha256=digest(raw_manifest),
        original_files_verified=len(entries),mismatches=mismatches,
        raw_bytes=sum((root/'capture-r4'/k).stat().st_size for k in entries)))
    original=read(root/'capture-r4/own.json');pairs={name:[] for name in ('drive','high')}
    for posture in pairs:
        for row in original['frames']:
            if row['sequence']==posture+'-off':
                other=truth[posture+'-on_v1',row['frame_id']];this=truth[row['sequence'],row['frame_id']]
                pairs[posture].append(float(np.linalg.norm(np.asarray(this[:2])-other[:2])))
    dump(out/'sensor-comparison.json',dict(readings=analysis['ranges'],fusion=False,
        paired_physics_xy_max_m={k:max(v) for k,v in pairs.items()},scope='paired issued tapes, separate worlds; not sensor-fused control efficacy'))
    reasons=[('capture-r1','HOST_ERROR','EGL import failed before physics'),
        ('capture-r2','HOST_ERROR','supervisor stopped for known invalid-range finalization defect; partial images, no complete labels'),
        ('capture-r3','HOST_ERROR','submission rejected: mistyped previous funnel path'),('capture-r4','cap_end','4/4 worlds and164/164 own frames'),
        ('analysis-r1','COMPLETE','causal tracking + standard ORB matrix'),('map-r1','HOST_ERROR','unused legacy motion calibration absent'),
        ('map-r2','HOST_ERROR','NumPy integer grid key serialization'),('map-r3','COMPLETE_NOT_READY','map emitted and scored; wrong-free cells and omissions'),
        ('playback-r2','ERROR','ffprobe43 frames vs41; duplicate terminal padding'),('playback-r3','ERROR','ffmpeg -r with non-CFR fps_mode rejected'),
        ('playback-r4','COMPLETE','3 videos all41 frames/1.366667s; full2Hz/10Hz strips'),
        ('projection-eval-r1','COMPLETE','exact normalized-quaternion heading; original labels retained'),
        ('camera-eval-r1','COMPLETE','body-relative comparison only'),('camera-eval-r2','COMPLETE','adds chassis tilt/floor-relative camera geometry')]
    dump(out/'attempts.json',[dict(attempt=n,status=s,category='run_attempt',reason=r,blocked_object='not_applicable' if 'COMPLETE' in s or s=='cap_end' else n,
        minimum_gap_m=None,gap_status='not_measured',raw=str(root/n)) for n,s,r in reasons])
    dump(out/'reset-render-comparison.json',read(root/'reset-render-comparison.json'))
    dump(out/'source-receipt.json',read(a.sources))
    dump(out/'playback-receipts.json',read(root/'playback-r4/receipts.json'))
    dump(out/'summary.json',dict(schema='ugrp.mapbuild2.summary.v1',status='NOT_READY',host=platform.node(),project='ugrp-sim-b-1014',
        shared=True,speed_admission=False,capture={k:captured[k] for k in ('status','frames','worlds','physics_steps','wall_s','scene','scene_xml_sha256','input_audit')},
        tracking=[dict(candidate=c,**row) for c,rows in corrected['metrics'].items() for row in rows if row['method']=='lk'],
        sparse_slam_tracked_pairs={k:sum(r['tracked_n'] for r in v if r['method']=='slam') for k,v in corrected['metrics'].items()},
        heading_label_correction_max_deg=corrected['heading_correction_abs_max_deg'],
        map_coverage={k:v['coverage'] for k,v in maps.items()},map_wrong_free={k:v['wrong_free_cells'] for k,v in maps.items()},
        remaining=['HIGH/actual held-load camera qualification absent','sparse map anchor correspondence80/80 insufficient for FOLDED',
            'partial map wrong-free7 and false semantics; obstacle class has no static targets','full frontier exploration and warp10 same-seed comparison not performed',
            'real camera original paths unavailable','existing shared-host8h configuration requires natural stop to clear'],
        scope='one map/start/seed; short fixed issued-command acquisition, no holdout or delivered mission success'))
    dump(out/'next-queue.json',dict(status='WITHHELD',rejection_table=str(out/'all-gates-funnel.json'),
        reason='camera qualification/sparse map/occupancy remain NOT_READY; comparison4 waits for warp10; no new batch approved'))
    dump(root/'RUN_META.json',dict(**{'class':'dev'},pr=556,branch='codex/mapbuild1',sha=captured['source_sha'],batch='mapbuild2',
        reconstructed=True,evidence='capture-r4 queue/source summary; no source or outcome relabeling'))
    dump(out/'SHA256SUMS.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(delivery=str(out),verified=len(entries),files=len(list(out.iterdir())))))


if __name__=='__main__':main()
