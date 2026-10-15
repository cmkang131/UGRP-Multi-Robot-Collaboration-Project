"""Format already verified remote records; no simulation or outcome inference."""
import argparse,json,hashlib,datetime
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();s=json.loads(a.input.read_text())
for r in s['runs']:
 r.pop('worlds',None)
 for w in r.get('world_results',[]):
  teacher=w.get('teacher',{})
  w['teacher']={k:teacher[k] for k in ('command_result','phase','ik_rejections','ik_rejection_reasons','events') if k in teacher}
  if r.get('cap_s',90)<=4:w.pop('lookaround',None)
 r['raw_full_record']=str(a.input)
s['source_record_sha256']=hashlib.sha256(a.input.read_bytes()).hexdigest()
s['formatter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
s['formatted_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
a.out.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
