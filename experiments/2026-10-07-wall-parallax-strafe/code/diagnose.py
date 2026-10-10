"""Post-seal evaluation only: actual travel, texture, and immutable raw receipts."""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import cv2
import replay_strafe as adapter
c=adapter.c
EXP=adapter.EXP
RAW=c.OUT.parent

def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def st(x):return dict(median=float(np.median(x)),p90=float(np.quantile(x,.9)),max=float(np.max(x)))

def main():
    adapter.verify()
    assert all((c.OUT/'parallax_v1'/case/'receipt.json').is_file() for case in c.EPISODES)
    output={}
    traces={}
    for case,ep in c.EPISODES.items():
        prediction=rows(c.OUT/'parallax_v1'/case/'predictions.jsonl')
        receipt=c.read(c.OUT/'parallax_v1'/case/'receipt.json')
        assert c.sha(c.OUT/'parallax_v1'/case/'predictions.jsonl')==receipt['predictions_sha256']
        truth=rows(ep/'eval_only/trajectory.jsonl')
        cameras=rows(ep/'eval_only/camera.jsonl')
        xy=np.array([r['robot_xyz_m'][:2] for r in truth])
        yaw=np.array([r['robot_yaw_rad'] for r in truth])
        rot=np.array([[math.cos(yaw[0]),-math.sin(yaw[0])],[math.sin(yaw[0]),math.cos(yaw[0])]])
        local=(xy-xy[0])@rot
        times=np.array([r['t'] for r in truth])
        own=list(c.stream(case))
        dr=np.array([r[3] for r in own])
        ts=np.array([r[0]['sim_time'] for r in own])
        inds=[int(np.argmin(abs(times-t))) for t in ts]
        err=np.linalg.norm(dr[:,:2]-local[inds],axis=1)
        windows=[np.linalg.norm(dr[i,:2]-dr[max(0,i-9),:2]) for i in range(9,len(dr))]
        actual_windows=[np.linalg.norm(local[inds[i]]-local[inds[i-9]]) for i in range(9,len(dr))]
        x=ET.fromstring((ep/'scene.xml').read_text())
        walls=[dict(g.attrib) for g in x.iter('geom') if (g.get('name') or '').startswith('zone_wall')]
        asset=[dict(g.attrib) for g in x.iter() if g.tag in ('texture','material') and 'ground' in g.get('name','')]
        totals=receipt['counts']
        rejection_keys=['low_parallax','zero_baseline','reprojection','behind_camera','outside_wall_roi','lk_failure','insufficient_views','range']
        events={k:totals.get(k,0) for k in rejection_keys}
        # Complete event denominator includes accepted; exclude frame/seed/reset counters.
        unknown=set(totals)-set(rejection_keys)-{'accepted','unsettled','calibrated_unloaded','seeded','reset_tracks'}
        assert not unknown,unknown
        n_events=sum(events.values())+totals.get('accepted',0)
        camera_by_t={round(r['t'],6):r for r in cameras}
        pitch=[]
        for r in prediction:
            actual=camera_by_t[round(r['t'],6)]
            body=np.array(actual['body_rotation']).reshape(3,3)
            camera=np.array(actual['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
            optical=body.T@camera
            # Optical +z in chassis; negative up component means downward.
            actual_pitch=math.degrees(math.asin(np.clip(optical[2,2],-1,1)))
            nominal_pitch=math.degrees(math.asin(np.clip(r['rotation'][2][2],-1,1)))
            pitch.append(actual_pitch-nominal_pitch)
        candidates=[p for r in prediction for p in r['candidate']]
        output[case]=dict(eligible_frames=receipt['frames'],counts=totals,event_count=n_events,
            event_fractions={k:v/n_events for k,v in events.items()},
            actual_xy_extent_m=np.ptp(local,axis=0).tolist(),actual_path_m=float(np.linalg.norm(np.diff(xy,axis=0),axis=1).sum()),
            actual_yaw_span_deg=float(np.degrees(np.ptp(np.unwrap(yaw)))),
            dr_xy_extent_m=np.ptp(dr[:,:2],axis=0).tolist(),dr_end_error_m=float(err[-1]),dr_path_error_m=st(err),
            available_10view_dr_baseline_m=st(windows),available_10view_actual_baseline_m=st(actual_windows),
            pitch_actual_minus_table_deg=st(pitch),
            accepted_unique_tracks=len(set(p['track_id'] for p in candidates)),
            accepted_frame_ids=[r['frame_id'] for r in prediction if r['candidate']],
            accepted_parallax_deg=st([p['parallax_deg'] for p in candidates]) if candidates else None,
            confidence=st([p['confidence'] for p in candidates]) if candidates else None,
            texture=dict(walls=walls,ground_assets=asset,wall_materials_count=sum('material' in w for w in walls)),
            acquisition=c.read(ep/'result.json'),evaluation_sources={str(p):c.sha(p) for p in
                [ep/'eval_only/trajectory.jsonl',ep/'eval_only/camera.jsonl',ep/'scene.xml']})
        traces[case]=dict(t=times-times[0],local=local,ts=ts-times[0],dr=dr)
    real=Path('/Users/changmin/projects/ugrp/outputs/camera-review-20261006/search-v3/recovered/real_traces/20260902T145131Z-real-19bb30fd/skills/20260902T145421Z-pick-b5f9a960/frames/frame-000005.jpg')
    c.dump(EXP/'results/diagnosis.json',dict(cases=output,real_reference=dict(path=str(real),sha256=c.sha(real),
        comparability='Historical tabletop real RGB, not matched arena walls; no quantitative real-wall texture claim'),
        tuning=0,mapping_replays=0,decision='STOP_OWN_MAP_TRACK'))
    # Static scientific figures, not a rebuilt map or success visualization.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(2,2,figsize=(10,6),constrained_layout=True)
    for j,(case,tr) in enumerate(traces.items()):
        ax=axs[0,j]
        ax.plot(tr['t'],tr['local'][:,1],label='actual lateral (eval only)',color='black')
        ax.plot(tr['ts'],tr['dr'][:,1],label='frozen command DR',color='#bd5042')
        ax.set(title=case,xlabel='time after reset (s)',ylabel='lateral displacement (m)')
        ax.legend(fontsize=8)
        counts=output[case]['counts']
        keys=['seeded','accepted','low_parallax','zero_baseline','reprojection','outside_wall_roi','lk_failure']
        axs[1,j].barh(keys,[counts.get(k,0) for k in keys],color='#557b90')
        axs[1,j].set(xlabel='count (seeds / repeated events are distinct units)')
    figs=EXP/'figures'
    figs.mkdir(exist_ok=True)
    fig.savefig(figs/'acquisition-diagnosis.png',dpi=140)
    plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    paths=[RAW/'annotations/strafe-north-2.png',real]
    titles=['Unchanged simulated wall + checker floor','Historical real tabletop (not matched arena)']
    for ax,p,title in zip(axs,paths,titles):
        ax.imshow(cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB))
        ax.set_title(title,fontsize=10)
        ax.axis('off')
    fig.savefig(figs/'texture-evidence.png',dpi=120)
    plt.close(fig)
    c.dump(EXP/'results/raw-manifest.json',dict(root=str(RAW),files={str(p.relative_to(RAW)):
        dict(bytes=p.stat().st_size,sha256=c.sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()}))
    print(json.dumps({k:{a:b for a,b in v.items() if a not in ('texture','evaluation_sources','acquisition')} for k,v in output.items()},indent=2))

if __name__=='__main__':main()
