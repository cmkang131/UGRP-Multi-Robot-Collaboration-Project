"""gcp2-only saved-image calibration and distribution audit; no rendering."""
from __future__ import annotations
import argparse,json,platform,sys
from collections import defaultdict,Counter
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
from scripts.summarize_scene_tex3 import read,write,sha
from scripts.score_scene_tex4 import distribution,selfmap_metrics
from scripts.probe_scene_tex2 import pose_pwm_mode,mask_score
from scripts.probe_scene_tex3 import jpeg
from harness.scene_colour_boundary import ColourBoundaryState,surface_masks
from sim.scene_contrast_v5 import profile_record
ENC=('png','jpeg90','pil82');BASE=('floor_light_textured_v1','native')

def quantile(values,weights,q):
    ix=np.argsort(values);values=values[ix];cum=np.cumsum(weights[ix])
    return float(values[min(len(values)-1,np.searchsorted(cum,q/100*(cum[-1]-1)+1))])

def calibrate(rows,profile):
    from harness.active_wall_vision import modules
    mp,_,_=modules();mp.undistort(np.zeros((480,640,3),np.uint8))
    hist={s:np.zeros((3,256),np.int64) for s in ('floor','wall')}
    ab={s:np.zeros(65536,np.int64) for s in hist};sources=[]
    for r in rows:
        root=Path(r['raw_root']);stem=r['case']+'--'+r['material']+'--'+r['quality']
        masks={s:cv2.imread(str(root/(stem+'--mask-'+s+'.png')),0) for s in hist}
        masks={s:cv2.erode(cv2.remap(m,mp._UNDISTORT[0],mp._UNDISTORT[1],cv2.INTER_NEAREST),np.ones((5,5),np.uint8))>0 for s,m in masks.items()}
        for e in ENC:
            lab=cv2.cvtColor(mp.undistort(cv2.imread(str(root/r['encodings'][e]['file']))),cv2.COLOR_BGR2LAB)
            for s,m in masks.items():
                pix=lab[m]
                for c in range(3):hist[s][c]+=np.bincount(pix[:,c],minlength=256)
                ab[s]+=np.bincount(pix[:,1].astype(int)*256+pix[:,2],minlength=65536)
            sources.append({'case':r['case'],'encoding':e,'sha256':r['encodings'][e]['sha256']})
    labs={s:{'p'+str(q).zfill(2):[quantile(np.arange(256),hist[s][c],q) for c in range(3)] for q in (0,1,50,99,100)} for s in hist}
    axis=np.array(labs['wall']['p50'][1:])-np.array(labs['floor']['p50'][1:]);axis/=np.linalg.norm(axis)
    values=(np.arange(65536)//256)*axis[0]+(np.arange(65536)%256)*axis[1]
    tails={'floor_p99':quantile(values,ab['floor'],99),'wall_p01':quantile(values,ab['wall'],1)}
    if tails['floor_p99']>=tails['wall_p01']:raise ValueError('CHROMA_DISTRIBUTIONS_NOT_SEPARATED')
    return {'schema':'ugrp.scene_colour_calibration.v1','scene_profile':profile,'scene_sha256':profile_record(profile)['sha256'],
        'lab':labs,'axis_ab':axis.tolist(),'split':sum(tails.values())/2,'split_basis':tails,
        'basis':'midpoint of original floor p99 and wall p01 chroma; class envelopes p00/p100; no boundary-error tuning',
        'interior_kernel_px':5,'interior_kernel_basis':'existing strip_half_px=2 -> 5-pixel support',
        'source_scope':'same88 poses x3 encodings exploratory, not holdout','sources':sources}

def signal(before,after,pwm,masks,state=None,return_scan=False):
    if state is None and not return_scan:return selfmap_metrics(before,after,pwm,masks)
    from harness.active_wall_vision import modules
    from harness.active_camera import transform
    from harness.wall_contact_detector import detect
    from harness.e2e_rgb_vo import ground_pair
    mp,hfw,_=modules()
    try:origin,rotation=transform(pwm)
    except ValueError as exc:return {'qualified':False,'status':str(exc),'columns':None,'residuals_px':[],'false_columns':None,'LK_tracks':None,'LK_inliers':None}
    cm=mp.ColumnModel(tuple(sorted(pwm.items())),0.,mp.column_positions(96,2),camera_transform=(origin,rotation))
    params=dict(floor_patch_max_m=.81,run_step_window=3,top_edge_px=4);und=mp.undistort(before)
    scan=detect(hfw,und,cm,params=params,loaded=False,wall_detector='scene_colour_transition_v1' if state else 'off',contact_state=state)
    truth={k:cv2.remap(v.astype(np.uint8),mp._UNDISTORT[0],mp._UNDISTORT[1],cv2.INTER_NEAREST)>0 for k,v in masks.items()}
    if return_scan:return und,scan,cm,truth
    residuals=[];false=visible=0
    for j,u in enumerate(cm.columns):
        edges=np.flatnonzero(truth['wall'][:-1,u]&truth['floor'][1:,u])+.5;visible+=bool(len(edges));v=scan['vb'][j,0]
        if np.isfinite(v):
            if len(edges):residuals.append(float(np.min(abs(v-edges))))
            else:false+=1
    cv2.setRNGSeed(0)
    flow=ground_pair(cv2.cvtColor(before,cv2.COLOR_BGR2RGB),cv2.cvtColor(after,cv2.COLOR_BGR2RGB),pwm,vo_floor_mask='homography_v1')
    return {'qualified':True,'status':flow['status'],'columns':int(np.isfinite(scan['vb'][:,0]).sum()),'residuals_px':residuals,'false_columns':false,'visible_boundary_columns':visible,
        'LK_tracks':int(flow.get('tracks',0)),'LK_inliers':int(flow.get('inliers',0)),'segments':len(hfw.link_segments(scan,params)),
        'reasons':dict(Counter(state.last_result['column_reasons']))}

def compare(a,b,qs=(10,50),greater=True):
    ad,bd=distribution(a),distribution(b)
    get=lambda d,q:d['median'] if q==50 else d['p'+str(q)]
    ok=all(get(ad,q) is not None and get(bd,q) is not None and (get(ad,q)>=get(bd,q) if greater else get(ad,q)<=get(bd,q)) for q in qs)
    return {'pass':bool(ok),'candidate':ad,'v1':bd,'quantiles':list(qs),'direction':'>=' if greater else '<='}

def semantic(r,e):
    v=r['encodings'][e]['semantic'];boxes=v['detectors']['boxes_own_zone_v2'];beam=v['detectors']['beam_legacy_dark_band_v2']
    return {'boxes':v['box_counts'],'clipped':sorted(boxes.get('clipped_kinds',[])),
        **{'beam_'+f:beam.get(f) for f in ('visible','end_visible','reason','grip_source')}}

def main(inputs,out):
    from harness.zone_pair_highpose import HIGH
    from scripts.zone_teacher import FOLDED
    cv2.setNumThreads(1);out.mkdir(exist_ok=False,parents=True)
    rows=[];sources=[];models=[]
    for root in inputs:
        meta=read(root/'summary.json');assert meta['status']=='MEASURED',root
        hashes=read(root/'SHA256SUMS.json')
        assert all((root/f).is_file() and sha(root/f)==h for f,h in hashes.items()),root
        sources.append({'path':str(root),'source_sha':meta['source_sha'],'verified_files':len(hashes),'summary_sha256':sha(root/'summary.json')})
        models.extend(read(root/'models.json'))
        for idx in read(root/'index.json'):
            r=read(root/idx['record']);r['raw_root']=str(root);rows.append(r)
    groups=defaultdict(list)
    for r in rows:groups[(r['material'],r['quality'])].append(r)
    baseline={r['case']:r for r in groups[BASE]};assert len(baseline)==88
    modelref={m['map']:m for m in models if (m['material'],m['quality'])==BASE};cals={}
    for key,rr in groups.items():
        assert len(rr)==88 and set(r['case'] for r in rr)==set(baseline)
        if key[0].startswith('walls_floor_contrast_v5_'):
            cals[key[0]]=calibrate(rr,key[0]);write(out/(key[0]+'-calibration.json'),cals[key[0]])
    for r in rows:
        root=Path(r['raw_root']);stem=r['case']+'--'+r['material']+'--'+r['quality']
        masks={s:cv2.imread(str(root/(stem+'--mask-'+s+'.png')),0)>0 for s in ('floor','wall')}
        after=cv2.imread(str(root/(stem+'--next.png')));pwm=FOLDED if pose_pwm_mode(r['pose'])=='FOLDED' else {**HIGH,1:1500}
        state=ColourBoundaryState(r['material'],cals[r['material']]) if r['material'] in cals else None
        r['signal']={};r['colour_iou']={};r['colour_separation']={}
        for e in ENC:
            before=cv2.imread(str(root/r['encodings'][e]['file']));nxt=after if e=='png' else jpeg(after,90 if e=='jpeg90' else 82,pil=e=='pil82')[0]
            r['signal'][e]=signal(before,nxt,pwm,masks,state)
            if state:
                pred,_=surface_masks(before,state.calibration);r['colour_iou'][e]={s:mask_score(pred[s],masks[s]) for s in masks}
            lab=cv2.cvtColor(before,cv2.COLOR_BGR2LAB).astype(float)
            if all(m.any() for m in masks.values()):
                centres=[np.median(lab[masks[s]],axis=0) for s in ('wall','floor')]
                r['colour_separation'][e]={'delta_L':float(abs(centres[0][0]-centres[1][0])),'delta_E76_opencv8':float(np.linalg.norm(centres[0]-centres[1]))}
        print('scored',r['case'],r['material'],flush=True)
    reports=[];funnel=[]
    for key,rr in groups.items():
        name='--'.join(key);report={'material':key[0],'quality':key[1],'frames':len(rr),'encodings':{}};bb=[baseline[r['case']] for r in rr]
        mm=[m for m in models if (m['material'],m['quality'])==key]
        parity=bool(mm) and all((m['physics_sha256'],m['camera_sha256'])==(modelref[m['map']]['physics_sha256'],modelref[m['map']]['camera_sha256']) for m in mm)
        assert all(a['qpos_sha256']==b['qpos_sha256'] for a,b in zip(rr,bb))
        detector_ok=boundary_ok=features_ok=lk_ok=True
        for e in ENC:
            equal=[semantic(a,e)==semantic(b,e) for a,b in zip(rr,bb)];detector_ok &= all(equal)
            qualified=[r for r in rr if r['signal'][e]['qualified']];ref=[baseline[r['case']] for r in qualified]
            cols=compare([r['signal'][e]['columns'] for r in qualified],[r['signal'][e]['columns'] for r in ref])
            errors=compare([v for r in qualified for v in r['signal'][e]['residuals_px']],[v for r in ref for v in r['signal'][e]['residuals_px']],qs=(50,95),greater=False)
            boundary_ok &= cols['pass'] and errors['pass']
            feats={f:compare([r['encodings'][e]['surfaces']['floor'][f] for r in rr],[r['encodings'][e]['surfaces']['floor'][f] for r in bb]) for f in ('orb20','orb7','interior20','interior7')}
            matches={f:compare([r['matches'][e][f]['mutual_ratio_matches'] for r in rr],[r['matches'][e][f]['mutual_ratio_matches'] for r in bb]) for f in ('floor20','floor7')}
            lk={f:compare([r['signal'][e][f] for r in qualified],[r['signal'][e][f] for r in ref]) for f in ('LK_tracks','LK_inliers')}
            features_ok &= all(x['pass'] for x in [*feats.values(),*matches.values()]);lk_ok &= all(x['pass'] for x in lk.values())
            wall_intrusions=Counter()
            for a,b in zip(rr,bb):
                for label,surfaces in a['encodings'][e]['intrusions'].items():
                    if surfaces.get('wall',0)>b['encodings'][e]['intrusions'].get(label,{}).get('wall',0):wall_intrusions[label]+=1
            report['encodings'][e]={'detector_equal':sum(equal),'semantic_changes':[{'case':a['case'],'candidate':semantic(a,e),'v1':semantic(b,e)} for a,b,same in zip(rr,bb,equal) if not same],
                'boundary_columns':cols,'boundary_error_px':errors,'qualified_n':len(qualified),
                'false_columns':sum(r['signal'][e]['false_columns'] for r in qualified),'v1_false_columns':sum(r['signal'][e]['false_columns'] for r in ref),
                'floor_features':feats,'floor_matches':matches,'LK':lk,'wall_range_new_intrusion_poses':dict(wall_intrusions),
                'iou':{s:distribution(r['colour_iou'][e][s]['iou'] for r in rr) for s in ('floor','wall')} if key[0] in cals else None,
                'colour_separation':{f:distribution(r['colour_separation'][e][f] for r in rr if e in r['colour_separation']) for f in ('delta_L','delta_E76_opencv8')},
                'drive_floor_orb20':distribution(r['encodings'][e]['surfaces']['floor']['orb20'] for r in rr if r['pose']=='drive'),
                'paired_floor_feature_regressions_record_only':{f:sum(a['encodings'][e]['surfaces']['floor'][f]<b['encodings'][e]['surfaces']['floor'][f] for a,b in zip(rr,bb)) for f in feats}}
        gates=[('same88_pose_physics_camera',parity),('existing_detectors_all_encodings',detector_ok),('boundary_distribution_all_encodings',boundary_ok),('floor_feature_matching_distribution_all_encodings',features_ok),('LK_distribution_all_encodings',lk_ok)]
        alive=88;stages=[]
        for stage,ok in gates:
            before=alive;alive=alive if ok else 0
            stages.append({'stage':stage,'input_n':before,'cumulative_pass_n':alive,'rejected_n':before-alive,
                'rejection':None if ok else {'category':stage.upper(),'blocking_object':'wall/floor visual appearance or RGB occlusion','minimum_gap_m':None,'minimum_gap_reason':'static RGB distribution gate, not collision clearance','reason':'requested comparison failed; see report fields'}})
        report.update(ready=all(bool(v) for _,v in gates),physics_camera_parity=parity,gates=dict(gates),
            wall_occluded_scene_limit={'frames':sum(r['pose']=='high_beam_peer_occluded' for r in rr),'wall_visible':sum(r['pose']=='high_beam_peer_occluded' and r['encodings']['png']['surfaces']['wall']['pixels']>0 for r in rr)})
        write(out/(name+'.json'),report)
        write(out/(name+'-cases.json'),[{'case':r['case'],'raw_root':r['raw_root'],'signal':r['signal'],'iou':r['colour_iou']} for r in rr])
        reports.append(report);funnel.append({'material':key[0],'quality':key[1],'stages':stages})
    write(out/'rejection-table.json',{'arms':funnel,'sources':sources,'reproduction_command':[sys.executable,'-m','scripts.score_scene_tex5',*sys.argv[1:]],'basis':'2026-10-16 user distribution gates; no added slack','raw_inputs':list(map(str,inputs))})
    write(out/'summary.json',{'schema':'ugrp.scenetex5.static.v1','status':'MEASURED','sources':sources,'reports':reports,'decision':'READY' if any(r['ready'] for r in reports if r['material'] in cals) else 'NOT_READY','analysis_sha256':sha(Path(__file__)),'physics_steps':0,'model_calls':0,'scope':'same88-pose exploratory SIM0 RGB audit; not motion, localization or physical task success'})
    select=[r for r in groups[BASE] if r['robot']=='r1' and r['view']==0 and r['pose'] in ('drive','box_palette','high_beam_peer_occluded')][:6];keys=list(groups)
    sheet=Image.new('RGB',(320*len(keys),264*len(select)),'white');draw=ImageDraw.Draw(sheet)
    for y,base in enumerate(select):
        for x,key in enumerate(keys):
            r=next(r for r in groups[key] if r['case']==base['case'])
            im=Image.open(Path(r['raw_root'])/r['encodings']['png']['file']).convert('RGB');im.thumbnail((320,240));sheet.paste(im,(x*320,y*264+24))
            draw.text((x*320+2,y*264+1),key[0].replace('walls_floor_contrast_v5_','')+'/'+key[1],fill='black')
            draw.text((x*320+2,y*264+12),r['map'].split('_final')[0]+'/'+r['pose'],fill='black')
    sheet.save(out/'comparison.jpg',quality=85)
    (out/'analysis-source.py').write_bytes(Path(__file__).read_bytes())
    write(out/'SHA256SUMS.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):p.error('gcp2 analysis only')
    main(a.inputs,a.output)
