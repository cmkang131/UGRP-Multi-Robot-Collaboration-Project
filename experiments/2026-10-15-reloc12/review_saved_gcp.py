import pathlib,json,sys,subprocess,hashlib,math
import cv2,numpy as np
root=pathlib.Path('/home/ugrp/ugrp-sim');out=root/'ops-reviews/reloc12';out.mkdir(parents=True,exist_ok=True)
for name in sys.argv[1:]:
 folder=root/'runs'/name;raw=folder/'raw';ledger=raw/'robots/r3/frames.jsonl'
 def read(p):
  if p.exists():return p.read_bytes()
  return subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
 rows=[json.loads(l) for l in read(ledger).splitlines()]
 ids=np.linspace(0,len(rows)-1,6,dtype=int);images=[];receipt=[]
 for i in ids:
  r=rows[int(i)];p=raw/'robots/r3/rgb'/f'{int(i):05d}.jpg'
  im=cv2.imread(str(p));im=cv2.resize(im,(426,320))
  cv2.putText(im,f"{name} t={r['sim_time']:.1f}",(5,20),cv2.FONT_HERSHEY_SIMPLEX,.35,(255,255,255),1)
  images.append(im);receipt.append(dict(path=str(p),t=r['sim_time'],sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 montage=np.concatenate([np.concatenate(images[:3],axis=1),np.concatenate(images[3:],axis=1)],axis=0)
 p=out/(name+'.jpg');cv2.imwrite(str(p),montage)
 (out/(name+'.json')).write_text(json.dumps(dict(run=name,frames=receipt,montage_sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2)+'\n')
 print(json.dumps(dict(run=name,montage=str(p),selected_N=6)))
