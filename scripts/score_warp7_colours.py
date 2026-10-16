"""Score saved MJWarp own RGB against evaluator-only visible geometry labels.

No CPU agreement gate. No simulator state or label is passed to a detector.
Pixel precision/recall are reported without a fitted acceptance cutoff.
Components are assigned to their largest visible label (ties are errors),
and absence means zero labelled pixels. Minimum observable area reuses each
production detector's own minimum area, never a new relaxed colour gate.
"""
import argparse, hashlib, json, platform
from collections import Counter
from pathlib import Path
import cv2
import numpy as np


def write(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def score(root,out):
    from harness.floor_goal import detect_floor,FloorGoalOptions
    from harness.zone_color_boxes import detect_own,OWN_PROFILE_ZONE,OWN_MIN_AREA_PX
    from scripts.probe_scene_tex2 import mask_score
    from harness.warp5_perception import install
    install();cv2.setNumThreads(1)
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((root/'SHA256SUMS.json').read_text())
    mismatches=[n for n,h in manifest.items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
    if mismatches:raise ValueError('source manifest mismatch: '+repr(mismatches))
    rows=[];events=[]
    for case in json.loads((root/'index.json').read_text()):
        record=json.loads((root/(case+'.json')).read_text())
        bgr=cv2.imread(str(root/(case+'--mjwarp.jpg')))
        masks={p.stem.split('--mask-')[-1]:cv2.imread(str(p),0)>0
               for p in root.glob(case+'--mjwarp--mask-*.png')}
        if not any(k.startswith('paint_') for k in masks):raise ValueError('semantic evaluation masks required')
        def assign(pred):
            overlaps={k:int((pred & m).sum()) for k,m in masks.items()}
            best=max(overlaps.values(),default=0)
            winners=[k for k,v in overlaps.items() if v==best and best>0]
            return winners[0] if len(winners)==1 else 'unknown_or_tie',overlaps
        boxes=detect_own(bgr,record['pwm'],profile=OWN_PROFILE_ZONE)['detections']
        for d in boxes:
            x,y,w,h=d['pixel_bbox'];pred=np.zeros(bgr.shape[:2],bool);pred[y:y+h,x:x+w]=True
            # Reconstruct the actual silhouette, rather than scoring floor
            # inside the bounding rectangle as a box detector prediction.
            from harness.zone_color_boxes import _colour_components
            comps,_=_colour_components(bgr,d['kind'],OWN_PROFILE_ZONE)
            comp=next(c for c in comps if list(c['bbox'])==d['pixel_bbox'])
            pred[:]=False
            canvas=np.zeros(pred.shape,np.uint8);cv2.drawContours(canvas,[comp['contour']],-1,1,-1);pred=canvas>0
            label,overlaps=assign(pred);target='box_'+d['kind']
            events.append(dict(case=case,detector='box',target=target,label=label,
                correct=label==target,overlaps=overlaps,pixels=int(pred.sum()),bbox=d['pixel_bbox']))
        patches,accepted,diagnostics=detect_floor(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),servo=record['pwm'],profile='camera_v3')
        for p in patches:
            pred=accepted==p['component'];label,overlaps=assign(pred)
            events.append(dict(case=case,detector='floor_B',target='paint_zone_B',label=label,
                correct=label=='paint_zone_B',overlaps=overlaps,pixels=int(pred.sum())))
        # Positive visibility and recall use the unchanged detector area floor.
        # This includes full-visibility fixtures and labels unexpectedly seen
        # in other poses. Partial silhouettes remain separately measurable.
        targets={**{k:OWN_MIN_AREA_PX for k in masks if k.startswith('box_')},
                 'paint_zone_B':FloorGoalOptions().min_pixels}
        observations=[]
        for target,minimum in targets.items():
            truth=masks[target];visible=int(truth.sum());eligible=visible>=minimum
            found=any(e['case']==case and e['target']==target and e['correct'] for e in events)
            observations.append(dict(target=target,visible_pixels=visible,area_floor=minimum,
                eligible=eligible,detected=found,miss=eligible and not found))
        rows.append(dict(case=case,pose=record['pose'],robot=record['robot'],visibility=observations,
            floor_B_pixel_score=mask_score(accepted>0,masks['paint_zone_B']),floor_diagnostics=diagnostics))
    totals={}
    for detector in ('box','floor_B'):
        ee=[e for e in events if e['detector']==detector]
        vv=[v for r in rows for v in r['visibility'] if (v['target'].startswith('box_'))==(detector=='box')]
        positive=[v for v in vv if v['eligible']]
        totals[detector]=dict(accepted=len(ee),correct=sum(e['correct'] for e in ee),
            false_positive=sum(not e['correct'] for e in ee),visible=len(positive),
            detected=sum(v['detected'] for v in positive),missed=sum(v['miss'] for v in positive),
            precision=sum(e['correct'] for e in ee)/len(ee) if ee else None,
            recall=sum(v['detected'] for v in positive)/len(positive) if positive else None)
    reasons=Counter((e['detector']+'_false_'+e['label']) for e in events if not e['correct'])
    reasons.update(v['target']+'_miss' for r in rows for v in r['visibility'] if v['miss'])
    # Static DEV admission is exact identification of eligible visible labels
    # and zero false accepted components. No CPU count/equality condition.
    # A failed component remains failed; a measured table permits motion DEV
    # diagnosis only, and never asserts localization or mission qualification.
    checks=dict(semantic_labels_present=len(rows)==88,hashes_match=not mismatches,
        no_false_components=all(t['false_positive']==0 for t in totals.values()),
        all_eligible_visible_detected=all(t['missed']==0 for t in totals.values()))
    write(out/'cases.json',rows);write(out/'events.json',events)
    funnel=dict(unit='frame',stages=[dict(stage='rendered_labelled',cumulative_pass_n=len(rows),rejected_n=0),
        dict(stage='no_false_components',cumulative_pass_n=sum(not any(e['case']==r['case'] and not e['correct'] for e in events) for r in rows),
            rejected_n=sum(any(e['case']==r['case'] and not e['correct'] for e in events) for r in rows))],
        rejection_distribution=[dict(category=k,N=n,blocked_object=k,minimum_gap_m=None,gap_status='image_classification_not_physical_gap') for k,n in reasons.most_common()],
        raw=str(root),reproduction=['python','-m','scripts.score_warp7_colours','--input',str(root),'--output',str(out)])
    write(out/'rejection-table.json',funnel)
    summary=dict(admitted=all(checks.values()),checks=checks,N=len(rows),totals=totals,
        scope='MJWarp static own-RGB DEV only; geometry labels evaluator-only; no CPU equivalence',
        raw=str(root),verified_files=len(manifest),hash_mismatches=mismatches,
        rejection_table=str((out/'rejection-table.json').resolve()))
    write(out/'summary.json',summary)
    write(out/'SHA256SUMS.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith(('ugrp-sim-gcp2','ugrp-act-l4-gcp2')):p.error('gcp2 saved-image analysis only')
    score(a.input.resolve(),a.output.resolve())
