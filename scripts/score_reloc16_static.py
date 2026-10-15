"""gcp2-only saved 88-pose boundary comparison; no physics, no GT control."""
import argparse,json,platform,collections
from pathlib import Path
import cv2,numpy as np
from scripts.summarize_scene_tex3 import read,write,sha
from scripts.score_scene_tex5 import signal,compare,semantic
from scripts.probe_scene_tex3 import jpeg
from scripts.probe_scene_tex2 import pose_pwm_mode
from scripts.zone_teacher import FOLDED
from harness.zone_pair_highpose import HIGH
from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
from harness.reloc16_wall_tracking import track

def main(out):
    if not platform.node().startswith('ugrp-sim-gcp2'):raise RuntimeError('gcp2 only')
    cv2.setNumThreads(1);out.mkdir(parents=True,exist_ok=False)
    root=Path('/home/ugrp/ugrp-sim/runs');raws=[root/'scenetex5-r1-v1-native',root/'scenetex5-r3-indigo110_s80']
    cal=read(Path('experiments/2026-10-16-reloc16/colour-calibration.json'))
    results={};sources=[]
    for raw in raws:
        rows=[read(raw/i['record']) for i in read(raw/'index.json')]
        rows_out=[];sources.append(dict(raw=str(raw),index_sha256=sha(raw/'index.json')))
        for r in rows:
            stem=r['case']+'--'+r['material']+'--'+r['quality']
            masks={s:cv2.imread(str(raw/(stem+'--mask-'+s+'.png')),0)>0 for s in ('floor','wall')}
            nxt=cv2.imread(str(raw/(stem+'--next.png')))
            pwm=FOLDED if pose_pwm_mode(r['pose'])=='FOLDED' else {**HIGH,1:1500}
            rr=dict(case=r['case'],signals={},semantics={},files={})
            for e in ('png','jpeg90','pil82'):
                path=raw/r['encodings'][e]['file'];assert sha(path)==r['encodings'][e]['sha256'] if 'sha256' in r['encodings'][e] else path.is_file()
                before=cv2.imread(str(path));after=nxt if e=='png' else jpeg(nxt,90 if e=='jpeg90' else 82,pil=e=='pil82')[0]
                state=ColourBoundaryState(r['material'],cal,option=RELOC16_OPTION) if raw==raws[1] else None
                rr['signals'][e]=signal(before,after,pwm,masks,state)
                rr['semantics'][e]=semantic(r,e);rr['files'][e]=dict(path=str(path),sha256=sha(path))
                if state is not None:
                    rr['signals'][e]['wall_LK']=track(before[...,::-1].copy(),after[...,::-1].copy(),cal)
                    rr['signals'][e]['wall_LK'].pop('before_uv',None);rr['signals'][e]['wall_LK'].pop('after_uv',None)
                    from harness.reloc16_compass import contacts,certify_points
                    from harness.reloc15_heading import commanded_rotation
                    from harness.active_wall_vision import modules
                    mp,hfw,_=modules()
                    uv=contacts(mp.undistort(before),cal,mp.column_positions(96,2),hfw.PARAMS)
                    rr['signals'][e]['compass']=certify_points(uv,np.linalg.inv(mp.K_INV),commanded_rotation(pwm),residual_px=cal['line_residual_px_p95'],min_columns=hfw.PARAMS['min_run_columns'])
            rows_out.append(rr)
            print('scored',raw.name,r['case'],flush=True)
        results[raw.name]=rows_out
    base={r['case']:r for r in results[raws[0].name]};candidate=results[raws[1].name];report={}
    for e in ('png','jpeg90','pil82'):
        pairs=[(r['signals'][e],base[r['case']]['signals'][e]) for r in candidate if r['signals'][e]['qualified']]
        cols=compare([a['columns'] for a,b in pairs],[b['columns'] for a,b in pairs])
        errors=compare([x for a,b in pairs for x in a['residuals_px']],[x for a,b in pairs for x in b['residuals_px']],qs=(50,95),greater=False)
        equal=sum(r['semantics'][e]==base[r['case']]['semantics'][e] for r in candidate)
        reasons=collections.Counter()
        for a,b in pairs:reasons.update(a['reasons'])
        report[e]=dict(columns=cols,error_px=errors,existing_detector_equal=equal,N=88,qualified_N=len(pairs),
            false_columns=sum(a['false_columns'] for a,b in pairs),baseline_false_columns=sum(b['false_columns'] for a,b in pairs),reasons=dict(reasons),
            wall_tracks=compare([a['wall_LK']['wall_tracks'] for a,b in pairs],[b['LK_tracks'] for a,b in pairs]),
            floor_channel_unchanged=True,compass_status=dict(collections.Counter(r['signals'][e]['compass']['status'] for r in candidate)))
    write(out/'cases.json',results);write(out/'summary.json',dict(report=report,sources=sources,calibration_sha256=sha(Path('experiments/2026-10-16-reloc16/colour-calibration.json')),
        ready=all(r['columns']['pass'] and r['error_px']['pass'] and r['existing_detector_equal']==88 for r in report.values()),
        scope='88 same static poses; wall tracks distinct from floor metric VO; no motion/localization success'))
    write(out/'rejection-table.json',dict(raw_sources=sources,reproduction=['python','-m','scripts.score_reloc16_static','--output',str(out)],
        stages=[dict(encoding=e,candidates=88,qualified=r['qualified_N'],colour_columns=sum(r['reasons'].values()),accepted=r['reasons'].get('COLOUR_TRANSITION',0),reasons=r['reasons']) for e,r in report.items()]))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.output)
