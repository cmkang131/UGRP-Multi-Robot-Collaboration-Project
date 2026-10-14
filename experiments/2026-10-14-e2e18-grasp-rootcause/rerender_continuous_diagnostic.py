from pathlib import Path
import hashlib,json,subprocess,io,tarfile,sys
import mujoco
from PIL import Image,ImageDraw
root=Path.home()/'ugrp-sim/runs/grasp-teacher-continuous-b0cc9d77/speed'
manifest=[]
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for case in sorted(root.glob('episode-*')):
  p=case/'raw';xml=(p/'scene.xml').read_bytes();f=p/'eval-only.jsonl.zst';raw=f.read_bytes();rows=[json.loads(x) for x in subprocess.check_output(['zstd','-qdc'],input=raw).splitlines()]
  m=mujoco.MjModel.from_xml_string(xml.decode());d=mujoco.MjData(m)
  with mujoco.Renderer(m,height=240,width=320) as renderer:
   for i in (0,60,120,180,240,290):
    row=rows[i];d.qpos[:]=row['joints'];d.time=row['t'];mujoco.mj_forward(m,d)
    canvas=Image.new('RGB',(640,500));draw=ImageDraw.Draw(canvas)
    for k,camera in enumerate(('cctv_top','cctv_top_east','cctv_top_north','cctv_top_north_east')):
     renderer.update_scene(d,camera=camera);frame=Image.fromarray(renderer.render());canvas.paste(frame,((k%2)*320,20+(k//2)*240))
    draw.text((5,3),f'SAVED QPOS / {case.name} / {i/10:g} SIM s',fill='white')
    buf=io.BytesIO();canvas.save(buf,format='JPEG',quality=86);b=buf.getvalue();name=f'{case.name}/saved-{i:06d}.jpg';info=tarfile.TarInfo(name);info.size=len(b);tar.addfile(info,io.BytesIO(b));manifest.append({'path':name,'sha256':hashlib.sha256(b).hexdigest(),'eval_path':str(f),'eval_sha256':hashlib.sha256(raw).hexdigest(),'scene_sha256':hashlib.sha256(xml).hexdigest(),'saved_t':row['t'],'physics_steps':0})
 b=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('saved-render-manifest.json');info.size=len(b);tar.addfile(info,io.BytesIO(b))
