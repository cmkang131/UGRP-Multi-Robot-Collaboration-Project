import json,inspect,collections,subprocess
from pathlib import Path
import cv2,numpy as np
from scripts.score_scene_tex5 import signal,ColourBoundaryState
from scripts.summarize_scene_tex3 import read
from harness import scene_colour_boundary as cb
from scripts.probe_scene_tex2 import pose_pwm_mode
from scripts.zone_teacher import FOLDED
from harness.zone_pair_highpose import HIGH
cv2.setNumThreads(1)
root=Path('/home/ugrp/ugrp-sim/runs/scenetex5-r3-indigo110_s80')
cal=read(Path('/home/ugrp/ugrp-sim/runs/scenetex5-r3-analysis/walls_floor_contrast_v5_indigo110_s80-calibration.json'))
source=inspect.getsource(cb.detect)
source=source.replace('reasons = []','reasons = []; diagnostics=[]')
source=source.replace('found = False','found = False;why="NO_CHROMA_CROSSING"')
source=source.replace("if above < 0 or below >= len(s) or not np.median(w[max(0,v-int(p['band_px'])):above+1]) or not f[below]: continue",'''if above < 0 or below >= len(s):why="SUPPORT_OUTSIDE_IMAGE";continue
            if not np.median(w[max(0,v-int(p['band_px'])):above+1]):why="WALL_BAND_CLASS_SUPPORT";continue
            if not f[below]:why="FLOOR_SINGLE_ROW_CLASS_SUPPORT";continue''')
source=source.replace("if row >= top[j]-p['self_margin_px']-1: continue", "if row >= top[j]-p['self_margin_px']-1: why='OWN_TOP';continue")
source=source.replace("if not np.isfinite(t): continue", "if not np.isfinite(t): why='CAMERA_RAY';continue")
source=source.replace("if not p['min_range_m'] <= r <= p['max_range_m']: continue", "if not p['min_range_m'] <= r <= p['max_range_m']: why='RANGE';continue")
source=source.replace("found = True; break", "found = True;why='PRIMARY';break")
source=source.replace("reasons.append('COLOUR_TRANSITION'", "diagnostics.append(why);reasons.append('COLOUR_TRANSITION'")
source=source.replace("'column_reasons':reasons,", "'column_reasons':reasons,'diagnostics':diagnostics,")
exec(compile(source,'audit-instrumentation','exec'),cb.__dict__)
rows=[]
for idx in read(root/'index.json'):
 r=read(root/idx['record']);pwm=FOLDED if pose_pwm_mode(r['pose'])=='FOLDED' else {**HIGH,1:1500}
 stem=r['case']+'--'+r['material']+'--'+r['quality']
 masks={s:cv2.imread(str(root/(stem+'--mask-'+s+'.png')),0)>0 for s in ('floor','wall')}
 nxt=cv2.imread(str(root/(stem+'--next.png')))
 for e in ('png','jpeg90','pil82'):
  state=ColourBoundaryState(r['material'],cal)
  # signal imported detect at runtime from wall_contact_detector, dispatches cb.detect.
  result=signal(cv2.imread(str(root/r['encodings'][e]['file'])),nxt,pwm,masks,state)
  if state.last_result:
   rows.append(dict(case=r['case'],encoding=e,signal=result,rejection_detail=dict(collections.Counter(state.last_result['diagnostics']))))
out=Path('/home/ugrp/ugrp-sim/runs/reloc16-before-audit');out.mkdir(exist_ok=False)
(out/'audit.json').write_text(json.dumps(rows,indent=2))
summary={e:dict(total=collections.Counter(),detail=collections.Counter()) for e in ('png','jpeg90','pil82')}
for r in rows:
 summary[r['encoding']]['total'].update(r['signal']['reasons']);summary[r['encoding']]['detail'].update(r['rejection_detail'])
(out/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
