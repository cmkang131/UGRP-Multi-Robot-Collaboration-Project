"""GCP2 terminal-run place gate reconstruction from native saved own RGB."""
import collections,hashlib,json,platform,subprocess,math
from pathlib import Path
import cv2,numpy as np
from harness.visual_arm_v3 import forward_grip
from harness.zone_own_perception import PAINT_HUE
from sim.grasp_act_solo_lookback import regions
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def text(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def obj(p):return json.loads(text(p))
def rows(p):return [json.loads(x) for x in text(p).splitlines()]
def main(n=3):
    assert platform.node().startswith('ugrp-sim-gcp2')
    q=obj(RUNS/f'reloc18-round{n}/queue.json');out=[]
    for task in q['runs']:
        raw=Path(task['raw']);folder=raw.parent
        if task['kind']!='carry' or not (folder/'EXIT').exists():continue
        d=obj(raw/'result.json');c=rows(raw/'teacher-commands.jsonl');view=[x for x in c if x['phase']=='zone_place_view']
        if not view:out.append(dict(run=task['name'],place_phase_frames=0,reason='place_not_reached'));continue
        lowrow=next(x for x in reversed(c) if x['t']<=view[0]['t'] and x['phase']=='close')
        low={int(k):v for k,v in lowrow['command']['pwm'].items()};gp={**low,1:1500};gx,gy,_=forward_grip(gp)
        fm=obj(raw/'failure-rgb/manifest.json');frames={round(x['t'],5):x for x in fm['frames']};records=[]
        ev={round(x['t'],5):x for x in rows(raw/'eval-only.jsonl') if 'base_xyz' in x}
        region=obj(raw/'carry-static-map.json')['regions']['zone_'+d['destination_zone']]
        for x in view:
            f=frames.get(round(x['t'],5))
            if f is None:continue
            p=raw/'failure-rgb'/f['path'];b=p.read_bytes();assert hashlib.sha256(b).hexdigest()==f['sha256']
            bgr=cv2.imdecode(np.frombuffer(b,np.uint8),cv2.IMREAD_COLOR);pwm={int(k):v for k,v in x['command']['pwm'].items()}
            roi,ring,g=regions(d['object_kind'],gp,pwm,(640,480),site=(gx+.15,gy,0.))
            hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)[roi];lo,hi=PAINT_HUE[d['destination_zone']]
            paint=(hsv[:,0]>=lo-5)&(hsv[:,0]<=hi+5)&(hsv[:,1]>=30)&(hsv[:,2]>=30)
            fraction=float(paint.mean()) if len(paint) else None
            reasons=[]
            if g['surface_in_frame_n']<g['surface_N']:reasons.append('footprint_out_of_frame')
            if g['site_pixels']<600:reasons.append('site_pixels_under600')
            if g['ring_pixels']<300:reasons.append('lookback_reference_ring_under300')
            if g['held_occlusion_pixels']>0:reasons.append('held_cargo_occludes_floor')
            if fraction is None or fraction<.6:reasons.append('paint_fraction_under0.6')
            evaluator=ev.get(round(x['t'],5));evaluation=None
            if evaluator:
                xx,yy=evaluator['base_xyz'][:2];a=evaluator['base_yaw_rad'];sx=xx+math.cos(a)*(gx+.15)-math.sin(a)*gy;sy=yy+math.sin(a)*(gx+.15)+math.cos(a)*gy
                cx,cy=region['center_m'];hx,hy=region['half_extents_m']
                evaluation=dict(actual_base=evaluator['base_xyz'],actual_yaw_rad=a,estimated_pose=x['map_pose']['pose_estimate'],
                    localization_error_xy_m=evaluator['map_pose_error_xy_m'],nominal_command_site_world=[sx,sy],
                    nominal_site_zone_margin_m=min(hx-abs(sx-cx),hy-abs(sy-cy)),scope='evaluation only; site uses nominal issued FK, sag unverified')
            recorded=x.get('destination_floor_visible')
            gate=bool(g['qualified'] and roi.sum()>=30 and fraction is not None and fraction>=.6)
            records.append(dict(t=x['t'],frame=str(p),sha256=f['sha256'],pwm=pwm,geometry=g,paint_fraction=fraction,evaluator=evaluation,
                recorded_gate=recorded,reconstruction_matches=gate==recorded,
                original_gate=gate,reasons=reasons))
        reasons=collections.Counter(k for x in records for k in x['reasons'])
        out.append(dict(run=task['name'],raw=str(raw),condition=task['condition'],place_phase_frames=len(view),native_scored_frames=len(records),
            native_missing_frames=len(view)-len(records),scope='native captured JPEG reconstructed with issued PWM; no evaluator input to gate',
            reconstructed_low_pwm=gp,reconstructed_grip_xy=[gx,gy],lookback_plan=d['teacher'].get('lookback_plan'),
            zone_region=region,paint_fraction_min=min((x['paint_fraction'] for x in records if x['paint_fraction'] is not None),default=None),
            paint_fraction_max=max((x['paint_fraction'] for x in records if x['paint_fraction'] is not None),default=None),
            reconstruction_mismatches=sum(not x['reconstruction_matches'] for x in records),first_evaluator=records[0]['evaluator'] if records else None,
            cumulative=dict(place_frames=len(view),native_available=len(records),geometry_qualified=sum(x['geometry']['qualified'] for x in records),
                roi_over30=sum(x['geometry']['qualified'] and x['geometry']['site_pixels']>=30 for x in records),
                painted_and_qualified=sum(x['original_gate'] for x in records)),rejection_reasons=dict(reasons),frames=records))
    p=RUNS/f'reloc18-round{n}/place-predicates.json';p.write_text(json.dumps(dict(runs=out,reproduce=f'PYTHONPATH=. python {__file__}'),indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k not in ('frames','lookback_plan')} for r in out],indent=2))
if __name__=='__main__':main()
