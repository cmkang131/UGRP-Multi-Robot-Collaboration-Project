"""gcp2-only terminal audit, failure montage and finite playback construction."""
import argparse,hashlib,importlib.util,json,platform,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RUNS=Path('/home/ugrp/ugrp-sim/runs')
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def obj(p):return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst']))
def main(n,media=False):
 assert platform.node().startswith('ugrp-sim-gcp2');b=RUNS/f'reloc19-round{n}';assert (b/'DONE').exists()
 summary=mod('summary',ROOT/'experiments/2026-10-16-reloc19/summarize.py');summary.main(n)
 q=obj(b/'queue.json');verify=mod('verify',ROOT/'experiments/2026-10-16-reloc17/baseline_analyzer.py').verify
 review=mod('review',ROOT/'experiments/2026-10-16-reloc18/review.py');records=[]
 for t in q['runs']:
  raw=Path(t['raw']);d=obj(raw/'result.json');a=d.get('teacher',{}).get('carry',{}).get('destination_visual_acquire',{})
  r=dict(run=t['name'],raw=str(raw),source_sha=t['source_sha'],integrity=verify(raw),input_audit=d.get('input_audit'),destination=a)
  if (raw/'failure-rgb/manifest.json').exists() or (raw/'failure-rgb/manifest.json.zst').exists():
   frames=obj(raw/'failure-rgb/manifest.json')['frames'];out=b/'media'/t['name'];out.mkdir(parents=True,exist_ok=True)
   six=[]
   for i in range(6):
    f=frames[round(i*(len(frames)-1)/5)];p=raw/'failure-rgb'/f['path'];h=hashlib.sha256(p.read_bytes()).hexdigest();assert h==f['sha256']
    dest=out/f'failure-{i:02d}.jpg';shutil.copyfile(p,dest);six.append(dict(t=f['t'],raw=str(p),path=str(dest),sha256=h))
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1','-framerate','1','-i',str(out/'failure-%02d.jpg'),'-vf','scale=320:240,tile=3x2:nb_frames=6','-frames:v','1',str(out/'failure-six.jpg')],check=True)
   r['failure_six']=six
   if media and ((raw/'playback/manifest.json').exists() or (raw/'playback/manifest.json.zst').exists()) and not (out/'playback').exists():review.make(raw.parent,out/'playback')
  records.append(r)
 (b/'integrity.json').write_text(json.dumps(dict(runs=records,verified=all(x['integrity']['verified'] for x in records)),indent=2)+'\n')
 manifest={str(p.relative_to(b)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in b.rglob('*') if p.is_file()}
 (b/'retrieval-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(dict(round=n,verified=all(x['integrity']['verified'] for x in records),raw_files=sum(x['integrity']['files'] for x in records),runs=len(records))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--round',type=int,required=True);p.add_argument('--media',action='store_true');a=p.parse_args();main(a.round,a.media)
