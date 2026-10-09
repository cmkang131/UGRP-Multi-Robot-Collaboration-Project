"""Offline evaluation-only pose-grid queries; no filter updates or simulator.
GT queries/counterfactuals never enter a controller, particle prior or calibration.
"""
import argparse,hashlib,json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace as NS
from collections import Counter
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze_visibility as geo
from harness import zone_solo_cyan_contract_v106 as c
from harness.s2_stiff_camera_calibration import runtime_class
from harness.zone_solo_cyan_augmented_start import Runtime
from harness.zone_solo_cyan_likelihood_field import Field,likelihood,PARAMS
from harness import vision_loc_protocol as vp
ROOT=Path(__file__).resolve().parents[2]
RAW=Path('/Users/changmin/projects/ugrp/outputs/s2-stiff-cal-20261007/start')
read=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(x) for x in p.read_text().splitlines()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def world(p,points):
    return points@geo.rz(p[2])[:2,:2].T+p[:2]


def score(field,px,views,key):
    total=np.zeros(len(px))
    for v in views:
        points=v[key]
        for i in range(0,len(px),4096):total[i:i+4096]+=np.log(likelihood(field,px[i:i+4096],points))
    return total


def main(out):
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    source=RAW.parent/'replay-start-on.json';saved=read(source);bundle=read(RAW/'setup_bundle.json')
    static=c.hp.resolve(c.MAP_ID)[0];field=Field(static);vl=vp.load_vis3()[0]
    omit=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    kw={k:v for k,v in bundle['options'].items() if k not in omit}
    kw.update(camera_pitch='stiff_target_v1',servo_stiffness='real_v1',
        stiff_camera_table=read(ROOT/'configs/calibration/s2_camera_stiff_target_v1.json'),
        **{k:bundle[k] for k in ('motion_model','pulse_calibration','extrinsic_calibration','floor_appearance')})
    rt=runtime_class(Runtime)(static,ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=1052,**kw)
    pf=rt.pose.provider.loc._pf
    gtrows=rows(RAW/'eval_only/trajectory.jsonl');cameras=rows(RAW/'eval_only/camera-pose.jsonl');frames=rows(RAW/'robots/r3/frames.jsonl')
    views=[];summary=[];sheets=[];segments=geo.wall_segments(static)
    try:
        for v in saved['views']:
            t=v['t'];g=min(gtrows,key=lambda q:abs(q['t']-t));ca=min(cameras,key=lambda q:abs(q['t']-t));f=min(frames,key=lambda q:abs(q['sim_time']-t))
            assert max(abs(q-t) for q in (g['t'],ca['t'],f['sim_time']))<1e-6
            truth=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']]
            pose={int(k):x for k,x in v['pose'].items()};cols=np.array(v['columns']);cm=pf.column_model_for(pose,columns=cols)
            pts=np.array(v['points']);opt=(np.c_[pts,np.zeros(len(pts))]-cm.origin)@cm._rot
            uv=opt@geo.K.T;uv=uv[:,:2]/uv[:,2,None]
            rz=geo.rz(truth[2]);base=np.r_[truth[:2],0.]
            actual=NS(origin=rz.T@(np.array(ca['camera_cached_xyz_m'])-base),_rot=rz.T@np.array(ca['camera_cached_optical_rotation']),columns=uv[:,0])
            bottom,_,_=geo.bottom_projection(actual,truth,segments)
            floors=[]
            for offset in (-4,4):
                rays=geo.pixel_rays(actual,uv[:,0],uv[:,1]+offset);depth=-actual.origin[2]/rays[:,2]
                wall=geo.wall_depths(actual,truth,rays,static)
                cargo=geo.box_depth(actual.origin,rays,rz.T@(np.array(g['cyan_xyz_m'])-base),rz.T@np.array(g['cyan_rotation']).reshape(3,3),np.array(g['box_half_m']))
                body=np.minimum.reduce(list(geo.shadow_depths(actual.origin,rays,geo.robot_boxes(pose,actual)).values()))
                floors.append((depth>0)&(wall>=depth-1e-6)&(cargo>=depth-1e-6)&(body>=depth-1e-6))
            floor=floors[0]&floors[1]&(abs(uv[:,1]-bottom)>10)
            wall=(abs(uv[:,1]-bottom)<=4)&~floor
            labels=np.where(wall,'true_wall_bottom',np.where(floor,'floor_candidate','unknown'))
            rays=geo.pixel_rays(actual,uv[:,0],uv[:,1]);d=-actual.origin[2]/rays[:,2]
            actual_points=(actual.origin+d[:,None]*rays)[:,:2]
            pr,_=vl.expected_rows(pf.geometry,truth[None,:],cm);visible=(pr[0]>=4)&(pr[0]<=470)
            ideal=cm.floor_point(cm.t_of_row(pr[0]))[visible]
            views.append(dict(t=t,raw=pts,actual_camera=actual_points,true_only=pts[wall],no_floor=pts[~floor],thin=pts[::8],ideal=ideal))
            err=field.distances(world(truth,pts));actualerr=field.distances(world(truth,actual_points))
            summary.append(dict(t=t,pose=pose,truth=truth.tolist(),counts=dict(Counter(labels)),
                columns=len(pts),image=f['path'],nominal_pitch_deg=float(np.degrees(np.arcsin(cm._rot[2,2]))),actual_pitch_deg=ca['cached_pitch_deg'],
                true_bottom_visible=int(((bottom>=4)&(bottom<=470)).sum()),
                median_endpoint_wall_error_m=float(np.median(err)),actual_camera_median_endpoint_wall_error_m=float(np.median(actualerr)),
                median_projection_delta_m=float(np.median(np.linalg.norm(actual_points-pts,axis=1))),
                class_endpoint_errors={label:dict(n=int((labels==label).sum()),median_m=float(np.median(err[labels==label]))) for label in set(labels)},
                points=pts.tolist(),uv=uv.tolist(),labels=labels.tolist(),true_bottom=bottom.tolist()))
            data=(RAW/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
            img=vl.mp.undistort(cv2.imdecode(np.frombuffer(data,np.uint8),1))
            for p,label in zip(uv,labels):cv2.circle(img,tuple(np.rint(p).astype(int)),3,{'true_wall_bottom':(0,255,0),'floor_candidate':(0,0,255),'unknown':(0,255,255)}[label],-1)
            cv2.putText(img,f"t={t}: wall {wall.sum()} floor? {floor.sum()} other {(~wall&~floor).sum()}",(8,30),0,.55,(255,255,255),2)
            sheets.append(img)
        truth=np.array(summary[0]['truth']);x0,x1,y0,y1=static['bounds_m']
        xs=np.arange(x0,x1+1e-9,.1);ys=np.arange(y0,y1+1e-9,.1);ya=np.deg2rad(np.arange(-180,180,5))
        xx,yy,aa=np.meshgrid(xs,ys,ya,indexing='ij');grid=np.c_[xx.ravel(),yy.ravel(),aa.ravel()]
        free=pf._map_logprior(grid)==0;px=grid[free]
        result=dict(schema='ugrp.s2.start_likelihood_grid.v1',physics_runs=0,filter_updates=0,model_calls=0,source_sha=__import__('subprocess').check_output(['git','rev-parse','HEAD'],text=True).strip(),gt_usage='evaluation-only grid scores/counterfactuals',
            grid=dict(xy_m=.1,yaw_deg=5,total=len(grid),free=len(px)),parameters=PARAMS,views=summary,variants={})
        archive=dict(poses=px);maps={};false=(np.linalg.norm(px[:,:2]-truth[:2],axis=1)>.25)|(abs(np.arctan2(np.sin(px[:,2]-truth[2]),np.cos(px[:,2]-truth[2])))>np.deg2rad(15))
        for key in ('raw','actual_camera','true_only','no_floor','thin','ideal'):
            log=score(field,px,views,key);exact=float(score(field,truth[None,:],views,key)[0]);archive[key]=log
            best=int(np.argmax(log));wrong=np.flatnonzero(false)[np.argmax(log[false])]
            allmap=np.full(len(grid),np.nan);allmap[free]=log-exact;maps[key]=allmap.reshape(xx.shape).max(2)
            result['variants'][key]=dict(exact_GT_log=exact,best_pose=px[best].tolist(),best_log=float(log[best]),best_over_GT=float(np.exp(log[best]-exact)),
                best_position_error_m=float(np.linalg.norm(px[best,:2]-truth[:2])),grid_points_above_GT=int((log>exact).sum()),
                false_best_pose=px[wrong].tolist(),false_best_over_GT=float(np.exp(log[wrong]-exact)),
                truth_evaluation_tolerance='25cm and15deg',point_count=sum(len(v[key]) for v in views))
            weights=np.exp(log-log.max());weights/=weights.sum();mean=weights@px[:,:2]
            result['variants'][key].update(grid_uniform_prior_near_GT_mass=float(weights[~false].sum()),grid_uniform_prior_mean_xy=mean.tolist(),grid_uniform_prior_mean_error_m=float(np.linalg.norm(mean-truth[:2])),grid_uniform_prior_sigma_xy_m=float(np.sqrt(weights@np.sum((px[:,:2]-mean)**2,axis=1))))
            print(key,result['variants'][key],flush=True)
        # Per-view attribution at the same aggregate raw false peak, not changing it for each ablation.
        wrong=np.array(result['variants']['raw']['false_best_pose'])
        for v,s in zip(views,summary):
            m=likelihood(field,np.vstack([truth,wrong]),v['raw']);s['GT_false_likelihood']=m.tolist()
            pose={int(k):x for k,x in s['pose'].items()};uv=np.array(s['uv'])
            cm=pf.column_model_for(pose,columns=uv[:,0]);rays=geo.pixel_rays(cm,uv[:,0],uv[:,1]);depth=-cm.origin[2]/rays[:,2]
            s['GT_false_geometry']=[]
            for hypothesis in (truth,wrong):
                first=geo.wall_depths(cm,hypothesis,rays,static)
                expected,_,_=geo.bottom_projection(cm,hypothesis,segments)
                s['GT_false_geometry'].append(dict(ray_intersects_wall_before_endpoint=int((first<depth-1e-6).sum()),
                    median_bottom_residual_px=float(np.median(abs(expected-uv[:,1]))),
                    detected_in_view=int(((expected>=4)&(expected<=470)).sum())))
            for label in s['class_endpoint_errors']:
                selected=np.array(s['labels'])==label;part=likelihood(field,np.vstack([truth,wrong]),v['raw'][selected])-1
                s['class_endpoint_errors'][label]['GT_false_additive_score']=part.tolist()
        # Exact GT yaw slice separates translational ambiguity from heading ambiguity.
        slice_px=np.c_[xx[:,:,0].ravel(),yy[:,:,0].ravel(),np.full(xx[:,:,0].size,truth[2])];valid=pf._map_logprior(slice_px)==0
        sl=np.full(len(slice_px),np.nan);sl[valid]=score(field,slice_px[valid],views,'raw')-result['variants']['raw']['exact_GT_log']
        maps['GT_yaw_slice']=sl.reshape(xx.shape[:2]);j=np.nanargmax(sl)
        result['GT_yaw_slice']=dict(best_pose=slice_px[j].tolist(),best_over_GT=float(np.exp(sl[j])))
        # Saved XML world geoms are fixed scene evidence, not a new simulation.
        xml=ET.parse(RAW/'scene.xml');walls=[]
        for o in static['obstacles']:
            if o['kind']!='wall':continue
            el=xml.find('.//geom[@name="zone_'+o['id']+'"]');assert el is not None
            pos=np.fromstring(el.get('pos'),sep=' ');size=np.fromstring(el.get('size'),sep=' ')
            error=max(np.max(abs(pos-np.r_[o['center_m'],o['height_m']/2])),np.max(abs(size-np.r_[o['half_extents_m'],o['height_m']/2])))
            walls.append(dict(id=o['id'],map_scene_max_abs_m=float(error),pos=pos.tolist(),size=size.tolist()))
        result['map_scene']=dict(walls=walls,door=static['passages'],scene_floor_visual_geoms=[e.attrib for e in xml.findall('.//worldbody/geom') if e.get('name','').startswith(('zone_','pickup_'))])
        np.savez_compressed(out/'grid.npz',**archive)
        cv2.imwrite(str(out/'observations.jpg'),np.vstack([np.hstack(sheets[i:i+2]) for i in (0,2,4)]))
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,4,figsize=(17,9),layout='constrained')
        for ax,(key,data) in zip(axes.flat,maps.items()):
            im=ax.imshow(data.T,origin='lower',extent=[xs[0],xs[-1],ys[0],ys[-1]],aspect='equal',cmap='coolwarm');ax.plot(*truth[:2],'g*',ms=14,label='exact GT (evaluation)');ax.plot(*wrong[:2],'kx',ms=9,label='raw false peak');ax.set_title(key+' : log score / GT');fig.colorbar(im,ax=ax,shrink=.65)
        axes.flat[-1].axis('off');axes.flat[0].legend(fontsize=7);fig.savefig(out/'likelihood-grid.png',dpi=150);plt.close(fig)
        result['evaluation_stationarity_max_m']=float(max(np.linalg.norm(np.array(g['robot_xyz_m'][:2])-truth[:2]) for g in gtrows))
        result['sources']={str(p):sha(p) for p in [source,RAW/'scene.xml',RAW/'eval_only/trajectory.jsonl',RAW/'eval_only/camera-pose.jsonl',RAW/'robots/r3/frames.jsonl',Path(__file__)]}
        result['artifacts']={str(p):sha(p) for p in out.iterdir() if p.is_file()}
        (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    finally:rt.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args().output)
