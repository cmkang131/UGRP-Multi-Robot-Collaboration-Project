import json,cv2,numpy as np
from pathlib import Path
from harness.e2e_rgb_gate import boundary
from scripts.replay_e2e_speed4 import read_rows
root=Path('outputs/e2e-speed4/b-samples');rows={Path(f['path']).name:f for f in read_rows(root/'robots/r1/frames.jsonl')}
res=[]
for factor in (.5,.75,.875,1.):
 for method in ('linear','nearest'):
  n=0;reason={}
  for p in sorted((root/'robots/r1/rgb').glob('*.jpg')):
   if int(p.stem)<264:continue
   im=cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB);small=cv2.resize(im,(int(640*factor),int(480*factor)),interpolation=cv2.INTER_AREA)
   low=cv2.resize(small,(640,480),interpolation=cv2.INTER_LINEAR if method=='linear' else cv2.INTER_NEAREST)
   servo={int(k):v for k,v in rows[p.name]['commanded_servo'].items()};d={}
   hit=boundary(low,servo,[0,0,0],marker_detect='contrast_v1',diagnostics=d)
   n+=hit is not None
   for r in d['contours']:
    if r['area_px2']>100:reason[r['reason']]=reason.get(r['reason'],0)+1
  res.append(dict(scale=factor,upsample=method,n=n,N=10,reasons=reason))
print(json.dumps(res));Path('outputs/e2e-speed4/scale-check.json').write_text(json.dumps(res,indent=2)+'\n')
