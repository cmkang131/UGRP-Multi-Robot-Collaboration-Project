import json,sys,hashlib
from collections import Counter
from pathlib import Path
from scripts.analyze_grasp_act_search24 import read
root=Path(sys.argv[1]);out=Path(sys.argv[2]);rows=[]
for raw in sorted(root.glob('diagnostic*/episode-*/raw')):
 data=read(raw/'result.json')
 if not data:continue
 res=json.loads(data);plan=json.loads(read(raw/'plan.json'));teachers={}
 for rid,t in res.get('teachers',{}).items():
  events=t.get('search20_log',[]);checks=[e for e in events if e.get('event')=='alignment_pulse_check'];reject=[e for e in events if e.get('event')=='final_command_reject'];obs=[e for e in t.get('search23_log',[]) if e.get('event')=='observed_band_priority']
  actual=[]
  for line in (read(raw/f'teacher-{rid}.jsonl') or b'').splitlines():
   d=json.loads(line)
   if d.get('teacher_phase')=='align' and any(d.get('applied_command',{}).get('wheels',[])):actual.append(d['applied_command']['t'])
  teachers[rid]={'outcome':t.get('outcome'),'pulse_checks':len(checks),'admitted_checks':sum(e['reason']=='admitted' for e in checks),'axis_check_reasons':dict(Counter(str(e['axis'])+':'+e['reason'] for e in checks)),'final_reject_reasons':dict(Counter(e['reason'] for e in reject)),'blocker_rows':dict(Counter(e['blocked_object'] for e in checks+reject if not e['blocked_object'].startswith('none:'))),'observed_priority_checks':len(obs),'actual_alignment_pulse_ticks':len(actual),'last_alignment_checks':checks[-6:],'events':t.get('events',[])[-5:]}
 rows.append({'episode':raw.parent.name,'seed':plan['seed'],'scene':plan.get('cargo_scene','off'),'status':res['status'],'success':res.get('physical_success'),'end_reason':res.get('end_reason'),'error_type':res.get('error_type'),'sim_s':res.get('sim_s'),'wall_s':res.get('wall_s'),'cap_end':res.get('cap_end'),'input_audit':res.get('input_audit'),'first30_speed':res.get('first30_speed'),'teachers':teachers})
report={'source_sha':(root/'SOURCE_SHA').read_text(),'raw_root':str(root),'scope':'GCP raw recount, not a new replay or physical trial','rows':rows}
out.write_text(json.dumps(report,indent=2)+'\n')
for r in rows:print(json.dumps({k:v for k,v in r.items() if k!='teachers'}));print({rid:{k:v for k,v in d.items() if k not in ('last_alignment_checks','events')} for rid,d in r['teachers'].items()})

from PIL import Image,ImageDraw
artifacts=[]
for raw in sorted(root.glob('diagnostic*/episode-*/raw')):
 res=json.loads(read(raw/'result.json'))
 if not res.get('physical_success'):continue
 frames=[]
 for rid in res.get('teachers',{}):
  files=sorted((raw/'eval-own'/rid).glob('*.jpg'))
  for i in sorted({round((len(files)-1)*u/5) for u in range(6)}) if files else []:frames.append((rid,files[i]))
 if not frames:continue
 canvas=Image.new('RGB',(640,270*((len(frames)+1)//2)),(20,20,20));draw=ImageDraw.Draw(canvas)
 for i,(rid,src) in enumerate(frames):
  x=(i%2)*320;y=(i//2)*270
  with Image.open(src) as im:canvas.paste(im.resize((320,240)),(x,y))
  draw.text((x+3,y+243),f'{raw.parent.name} {rid} {src.stem}',fill='white')
 dest=out.parent/(raw.parent.name+'-montage.jpg');canvas.save(dest,quality=92)
 artifacts.append({'path':dest.name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
report['success_montages']=artifacts
out.write_text(json.dumps(report,indent=2)+'\n')
