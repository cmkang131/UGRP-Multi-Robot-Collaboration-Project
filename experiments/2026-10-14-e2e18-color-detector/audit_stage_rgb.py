"""Evaluation-only RGB audit, never imported into live control."""
from pathlib import Path
import subprocess,json,sys
sha=sys.argv[1];pattern=sys.argv[2]
code=r'''from pathlib import Path
import json,sys,subprocess,collections,math,hashlib
sys.path.insert(0,str(Path.home()/'ugrp-sim/src'/SHA))
import cv2
from harness.e2e_color_detection import detect
from harness.e2e_end_assignment import rgb_peer_regions

def read(p,lines=False):
 if not p.exists():p=Path(str(p)+'.zst')
 if not p.exists():return [] if lines else {}
 data=subprocess.check_output(['zstd','-qdc',str(p)]).decode() if p.suffix=='.zst' else p.read_text()
 return [json.loads(l) for l in data.splitlines() if l] if lines else json.loads(data)
rows=[]
for run in sorted((Path.home()/'ugrp-sim/runs').glob(PATTERN)):
 if not (run/'EXIT').exists():continue
 raw=run/'raw';trace=read(raw/'transport-trace.json');events=trace if isinstance(trace,list) else trace.get('events',[])
 out=dict(name=run.name,robots={},online_occupancy_events=[e for e in events if 'occupancy' in e.get('event','')])
 for rid,color in [('r1','teal'),('r2','blue')]:
  oo=read(raw/f'robots/{rid}/ownmap.jsonl',True);ff=read(raw/f'robots/{rid}/frames.jsonl',True);by={f['sha256']:f for f in ff};counts=collections.Counter();examples=[];seen=set();rgbcache={};ranges=[];last=None
  for o in oo:
   sha=o['sha256']
   counts['unique_rgb_frames']+=sha not in seen
   seen.add(sha);b=(o.get('own_beam_observation') or {}).get('result',{});counts['frames']+=1
   counts['body_visible']+=bool(b.get('visible'));counts['metric_grasp_admitted']+=bool(b.get('end_visible'))
   counts['online_band_presence']+=bool(b.get('band_visible'));counts['online_presence_field']+='band_visible' in b
   counts['reason:'+b.get('reason','none')]+=1
   f=by.get(sha)
   if f is None:counts['missing_frame_ledger']+=1;continue
   if sha not in rgbcache:
    data=(raw/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==sha
    image=cv2.imdecode(__import__('numpy').frombuffer(data,__import__('numpy').uint8),cv2.IMREAD_COLOR);_,visual=detect(image,color)
    rgbcache[sha]=(visual,rgb_peer_regions(data) if visual['band_visible'] else [])
   visual,regions=rgbcache[sha];counts['offline_common_band_presence']+=visual['band_visible']
   if not visual['band_visible']:last=None;continue
   matches=[]
   for band in visual['color_components']:
    a=band['bbox_xyxy'];margin=max(24,min(80,math.sqrt(band['pixels'])*.5))
    for peer in regions:
     p=peer['bbox_px'];dx=max(a[0]-p[2],p[0]-a[2],0);dy=max(a[1]-p[3],p[1]-a[3],0)
     if math.hypot(dx,dy)<=margin:matches.append(dict(band=band,peer=peer,gap_px=math.hypot(dx,dy),threshold_px=margin))
   hit=bool(matches);counts['peer_near_assigned_band_screen']+=hit
   if hit:
    if last is None or f['sim_time']-last>1.:counts['near_band_episodes']+=1
    last=f['sim_time']
    if len(examples)<6 and (not examples or f['sim_time']-examples[-1]['sim_time']>=2.):examples.append(dict(frame_id=f['frame_id'],sim_time=f['sim_time'],sha256=sha,path=f['path'],matches=matches,metric_grasp_admitted=bool(b.get('end_visible')),controller_status=(o.get('carrier_approach') or {}).get('status')))
   else:last=None
  out['robots'][rid]=dict(counts=dict(counts),examples=examples)
 rows.append(out)
print(json.dumps(dict(evaluation_only=True,screen_proximity_is_not_physical_occupancy=True,peer_identity='unknown visual robot proposal',criteria='assigned-color component and compound robot proposal boxes: gap <= clamp(sqrt(band area)/2,24,80) px; episodes gap >1s',runs=rows)))
'''.replace('SHA',repr(sha)).replace('PATTERN',repr(pattern))
r=subprocess.run(['ssh','-o','ConnectTimeout=10','azure3','timeout 120 /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python -'],input=code,text=True,capture_output=True,timeout=130);r.check_returncode();d=json.loads(r.stdout)
p=Path('experiments/2026-10-14-e2e18-color-detector/rgb-occupancy-audit.json');p.write_text(json.dumps(d,indent=2)+'\n')
for row in d['runs']:print(row['name'],{rid:r['counts'] for rid,r in row['robots'].items()},'occupancy_events',len(row['online_occupancy_events']))
