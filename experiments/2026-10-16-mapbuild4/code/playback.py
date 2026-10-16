import json,hashlib,subprocess,math
from pathlib import Path
base=Path('/home/ugrp/ugrp-sim/runs/mapbuild4');out=base/'playback-r1';out.mkdir(exist_ok=True);receipts=[]
for root in [base/'pulse-warp-r1']:
 for case in ['drive-left-+1-60','drive-left-+1-400','high-left-+1-60','drive-forward-+1-100']:
  source=root/case;n=21;folder=out/case;folder.mkdir(exist_ok=True)
  ins=[]
  for camera in ['overview','r1','r2']:ins+=['-framerate','30','-i',str(source/(camera+'-%04d.jpg'))]
  video=folder/'review-3x.mp4'
  subprocess.run(['ffmpeg','-y','-nostdin','-loglevel','error',*ins,'-filter_complex','[0:v][1:v][2:v]hstack=inputs=3[v]','-map','[v]','-frames:v',str(n),'-fps_mode','vfr','-an','-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-threads','1',str(video)],check=True)
  for camera in ['overview','r1','r2']:
   for hz,vf in [(2,r'select=not(mod(n\,5)),scale=320:240,tile=3x2'),(10,'scale=320:240,tile=7x3')]:
    subprocess.run(['ffmpeg','-y','-nostdin','-loglevel','error','-framerate','10','-i',str(source/(camera+'-%04d.jpg')),'-vf',vf,'-frames:v','1','-threads','1',str(folder/f'{camera}-{hz}hz.jpg')],check=True)
  probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
  assert int(probe['streams'][0]['nb_frames'])==n and video.stat().st_size<=8*1024**2
  receipts.append(dict(case=case,source=str(source),sim_range=[0,2],probe=probe,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.iterdir()}))
(out/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
print('complete',len(receipts))
