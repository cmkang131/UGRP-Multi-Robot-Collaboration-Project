"""Selected text evidence + six own-RGB times/robot, never top/whole raw."""
import hashlib,io,json,subprocess,sys
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));from scripts import remote_run
remote_run.PRIMARY=ROOT
folder=Path(sys.argv[1]);rows=json.loads((folder/'plan.json').read_text());verification=[]
for row in rows:
 name=row['name'];path=f'/home/ugrp/ugrp-sim/runs/{name}'
 cmd=f'cd {path} && test -s EXIT && test -s SHA256SUMS && sha256sum -c --quiet SHA256SUMS && sha256sum SHA256SUMS'
 p=subprocess.run(['ssh','-o','BatchMode=yes','gcp1',cmd],text=True,capture_output=True)
 if p.returncode:print('pending',name,p.stderr.strip());continue
 target=Path(remote_run.fetch('gcp1',name));manifest={}
 for line in (target/'SHA256SUMS').read_text().splitlines():
  sha,file=line.split(maxsplit=1);manifest[file.strip().lstrip('*')]=sha
 verified=[]
 for f in target.rglob('*'):
  if not f.is_file() or f.name=='SHA256SUMS':continue
  key=path+'/'+str(f.relative_to(target));expect=manifest.get(key) or manifest.get(str(f.relative_to(target)))
  if expect is None:continue
  digest=hashlib.sha256(f.read_bytes()).hexdigest();assert digest==expect,(f,expect,digest);verified.append(str(f.relative_to(target)))
 # Remote file names/mtimes are review evidence; select six distinct times over the run.
 code="import pathlib,json; p=pathlib.Path("+repr(path+"/raw/eval-own/r1")+");print(json.dumps([dict(name=f.name,mtime=f.stat().st_mtime) for f in sorted(p.glob('*-grasp.jpg'))]))"
 remote=json.loads(subprocess.check_output(['ssh','-o','BatchMode=yes','gcp1','python3 -c '+__import__('shlex').quote(code)],text=True))
 if len(remote)<6:chosen=remote
 else:chosen=[remote[round((len(remote)-1)*i/5)] for i in range(6)]
 sheet=Image.new('RGB',(640,264*len(chosen)), 'white');draw=ImageDraw.Draw(sheet);frames=[]
 selected=[f"raw/eval-own/{rid}/{f['name']}" for f in chosen for rid in ['r1','r2']]
 framebase=ROOT/'outputs/crate18/frames'/name;framebase.mkdir(parents=True,exist_ok=True)
 filelist=framebase/'selected-files.txt';filelist.write_text('\n'.join(selected)+'\n')
 subprocess.run(['rsync','-a','--files-from',str(filelist),f'gcp1:{path}/',str(framebase)+'/'],check=True,capture_output=True)
 for i,f in enumerate(chosen):
  for j,rid in enumerate(['r1','r2']):
   rel=f"raw/eval-own/{rid}/{f['name']}";dst=framebase/rel
   digest=hashlib.sha256(dst.read_bytes()).hexdigest();expect=manifest.get(path+'/'+rel) or manifest.get(rel);assert digest==expect
   im=Image.open(dst);im.load();sheet.paste(im.resize((320,240)),(j*320,i*264+24));draw.text((j*320+4,i*264+4),rid+' '+f['name'],fill='black')
   frames.append(dict(path=str(dst),remote=path+'/'+rel,sha256=digest,mtime=f['mtime']))
 sheetpath=ROOT/'outputs/crate18/frames'/(name+'-review.jpg');sheet.save(sheetpath,quality=92)
 decoded=[]
 for filename,meta in json.loads((target/'raw/manifest.json').read_text()).items():
  if 'decoded_sha256' not in meta:continue
  f=target/'raw'/filename
  if not f.exists():continue
  b=subprocess.check_output(['zstd','-dc',str(f)]);assert hashlib.sha256(b).hexdigest()==meta['decoded_sha256'];decoded.append(filename)
 assert not any('eval-overview/' in name for name in manifest), 'top capture prohibited'
 verification.append(dict(all_grasp_frames_mtime=remote,decoded_hashes_verified=decoded,run=name,remote_manifest_verified=True,manifest_sha256=p.stdout.split()[0],local_files_verified=len(verified),
   frame_count=len(frames),frames=frames,sheet=str(sheetpath),directly_viewed=False,review_scope='own r1/r2 only; no top'))
 print(name,len(verified),'text hashes;',len(frames),'own frames',flush=True)
(folder/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
