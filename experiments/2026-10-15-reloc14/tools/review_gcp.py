from pathlib import Path
import json,hashlib,shutil,cv2,numpy as np
from scripts.analyze_reloc11_selfmap import rows
R=Path('/home/ugrp/ugrp-sim');O=R/'ops-reviews/reloc14';O.mkdir(parents=True,exist_ok=True)
for p in sorted(R.glob('runs/reloc14-*')):
 if not (p/'EXIT').exists():continue
 carry='carry' in p.name;raw=p/'raw'
 files=sorted(raw.glob('review-own/*.jpg') if carry else raw.glob('robots/r3/rgb/*.jpg'))
 if not files:continue
 trace=rows(raw/('teacher-commands.jsonl' if carry else 'trace.jsonl'))
 ids=set(np.linspace(0,len(files)-1,6,dtype=int).tolist())
 selected=sorted(ids);images=[];receipts=[];target=O/p.name;target.mkdir(exist_ok=True)
 for i in selected:
  f=files[i];im=cv2.imread(str(f));im=cv2.resize(im,(426,320))
  j=min(len(trace)-1,int(f.stem) if carry else i);r=trace[j]
  label=f"t={r['t']:.1f} {r.get('phase',r.get('stage',''))}"
  cv2.putText(im,label,(5,22),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
  images.append(im);receipts.append(dict(source=str(f),local_name=f.name,t=r['t'],sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
  shutil.copy2(f,target/f.name)
 while len(images)<6:images.append(images[-1])
 montage=np.concatenate([np.concatenate(images[:3],axis=1),np.concatenate(images[3:6],axis=1)],axis=0)
 output=O/(p.name+'.jpg');cv2.imwrite(str(output),montage)
 (O/(p.name+'.json')).write_text(json.dumps(dict(run=p.name,frames=receipts,montage_sha256=hashlib.sha256(output.read_bytes()).hexdigest()),indent=2)+'\n')
 print(json.dumps(dict(run=p.name,N=len(receipts),montage=str(output))))
