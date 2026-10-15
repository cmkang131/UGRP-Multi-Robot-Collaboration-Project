import importlib.util,json,time,cv2,numpy as np,platform
from pathlib import Path
from scripts.summarize_scene_tex3 import read,write
from scripts.score_scene_tex5 import signal
from scripts.probe_scene_tex2 import pose_pwm_mode
from scripts.zone_teacher import FOLDED
from harness.zone_pair_highpose import HIGH
from harness.active_wall_vision import modules
from harness import scene_colour_boundary as cb
from harness import reloc16_compass as compass
from harness.reloc15_heading import commanded_rotation
cv2.setNumThreads(1)
def load(name,file):
 s=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ref=Path('/home/ugrp/ugrp-sim/src/reloc16-93635d6e/harness')
old=load('ref_boundary',ref/'scene_colour_boundary.py');oldcompass=load('ref_compass',ref/'reloc16_compass.py')
mp,hfw,_=modules();cal=read(Path('experiments/2026-10-16-reloc16/colour-calibration.json'))
raw=Path('/home/ugrp/ugrp-sim/runs/scenetex5-r3-indigo110_s80');timings=[];same=[];comp=[]
for idx in read(raw/'index.json'):
 r=read(raw/idx['record']);pwm=FOLDED if pose_pwm_mode(r['pose'])=='FOLDED' else {**HIGH,1:1500}
 if pwm!=FOLDED:continue
 cm=mp.ColumnModel(tuple(sorted(pwm.items())),0.,mp.column_positions(96,2),camera_transform=__import__('harness.active_camera',fromlist=['transform']).transform(pwm))
 for e in ('png','jpeg90','pil82'):
  und=mp.undistort(cv2.imread(str(raw/r['encodings'][e]['file'])))
  args=dict(params=dict(floor_patch_max_m=.81,run_step_window=3,top_edge_px=4),loaded=False)
  os=old.ColourBoundaryState(r['material'],cal,option=old.RELOC16_OPTION);ns=cb.ColourBoundaryState(r['material'],cal,option=cb.RELOC16_OPTION)
  t=time.process_time();a=old.detect(hfw,und,cm,state=os,**args);ot=time.process_time()-t
  t=time.process_time();b=cb.detect(hfw,und,cm,state=ns,**args);nt=time.process_time()-t
  equal=all(np.array_equal(a[k],b[k],equal_nan=True) for k in a);same.append(equal)
  uv=compass.contacts(und,cal,mp.column_positions(96,2),hfw.PARAMS)
  kw=dict(residual_px=cal['line_residual_px_p95'],min_columns=hfw.PARAMS['min_run_columns'])
  t=time.process_time();c=oldcompass.certify_points(uv,np.linalg.inv(mp.K_INV),commanded_rotation(pwm),**kw);oc=time.process_time()-t
  t=time.process_time();d=compass.certify_points(uv,np.linalg.inv(mp.K_INV),commanded_rotation(pwm),**kw);nc=time.process_time()-t
  comp.append(c==d);timings.append(dict(case=r['case'],encoding=e,boundary_before=ot,boundary_after=nt,compass_before=oc,compass_after=nc))
  if not equal or c!=d:print('MISMATCH',r['case'],e,flush=True)
report=dict(N=len(same),boundary_exact_N=sum(same),compass_exact_N=sum(comp),timings=timings,
 timing_cpu_median={k:float(np.median([r[k] for r in timings])) for k in ('boundary_before','boundary_after','compass_before','compass_after')},
 scope='same saved encoded RGB; process CPU only, not closed-loop speed; all outputs including hypothesis counts exact',reference_sha='93635d6ecd47226138c433603a15dd362ff10f11')
write(Path('/home/ugrp/ugrp-sim/runs/reloc16-perf.json'),report);print(json.dumps({k:v for k,v in report.items() if k!='timings'}))
