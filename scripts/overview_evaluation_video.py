"""Independent observer compositor; overlays never touch the physics owner."""
from pathlib import Path
import bisect
import hashlib
import itertools
import json
import shutil
import subprocess


def data(path):
    p=Path(path)
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])


def read(path):return json.loads(data(path))
def rows(path):return [json.loads(line) for line in data(path).splitlines()]
def sha(path):return hashlib.sha256(data(path)).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


class Timeline:
    def __init__(self,records):
        self.records=records;self.times=[r['t'] for r in records]
    def at(self,t):
        i=bisect.bisect_right(self.times,t+1e-8)-1
        return self.records[i] if i>=0 else None


class Video:
    def __init__(self,host,title,robots,*,own_trace=None,origin=None,return_valid=None):
        import mujoco
        import numpy as np
        from PIL import ImageFont
        self.mj,self.np=mujoco,np;self.title,self.robots=title,robots
        self.model=mujoco.MjModel.from_xml_path(str(host.out/'scene.xml'))
        self.model.vis.global_.offwidth=max(960,self.model.vis.global_.offwidth)
        self.model.vis.global_.offheight=max(420,self.model.vis.global_.offheight)
        self.model.vis.global_.fovy=32
        self.data=mujoco.MjData(self.model)
        self.renderer=mujoco.Renderer(self.model,height=420,width=960)
        self.camera=mujoco.MjvCamera();self.camera.type=mujoco.mjtCamera.mjCAMERA_FREE
        static=read(host.out/'inputs/static_map.json');bounds=static['bounds_m']
        self.camera.lookat[:]=((bounds[0]+bounds[1])/2,(bounds[2]+bounds[3])/2,.12)
        self.camera.distance=8.6;self.camera.azimuth=90.;self.camera.elevation=-65.
        self.B=static['regions']['zone_B'];self.trace=own_trace;self.origin=origin
        self.return_valid=return_valid;self.actual_path=[];self.estimated_path=[]
        self.font=ImageFont.truetype('/home/ubuntu/ugrp-sim/s3view3-font.ttf',19)
        self.small=ImageFont.truetype('/home/ubuntu/ugrp-sim/s3view3-font.ttf',17)
        self.frames=0;self.next_t=host.now;self.output=host.out.parent/'overview.mp4'
        self.last=None
        self.process=subprocess.Popen([shutil.which('ffmpeg'),'-nostdin','-n','-v','error',
            '-f','rawvideo','-pix_fmt','rgb24','-s','1280x480','-r','40','-i','-',
            '-an','-c:v','libx264','-threads','1','-preset','veryfast','-crf','20',
            '-pix_fmt','yuv420p','-movflags','+faststart',str(self.output)],stdin=subprocess.PIPE)

    def project(self,points):
        np=self.np;cams=self.renderer.scene.camera
        eye=np.mean([c.pos for c in cams],axis=0)
        forward=np.mean([c.forward for c in cams],axis=0);forward/=np.linalg.norm(forward)
        up=np.mean([c.up for c in cams],axis=0);up/=np.linalg.norm(up)
        right=np.cross(forward,up);v=np.asarray(points)-eye;depth=v@forward
        h=np.tan(np.radians(16));w=h*960/420
        return np.column_stack((480+(v@right)/(depth*w)*480,60+210-(v@up)/(depth*h)*210))

    def frame(self,host,own):
        from PIL import Image,ImageDraw
        import math
        if host.now+1e-8<self.next_t:return
        self.mj.mj_copyData(self.data,host.world.model,host.world.data)
        self.renderer.update_scene(self.data,camera=self.camera)
        canvas=Image.new('RGB',(1280,480),'#101820');canvas.paste(Image.fromarray(self.renderer.render()),(0,60))
        draw=ImageDraw.Draw(canvas)
        draw.text((8,5),self.title+' · 8x',font=self.font,fill='white')
        draw.text((985,5),f'SIM {host.now:.2f}s',font=self.font,fill='white')
        x,y=self.B['center_m'];hx,hy=self.B['half_extents_m']
        poly=self.project([[x-hx,y-hy,.003],[x+hx,y-hy,.003],[x+hx,y+hy,.003],[x-hx,y+hy,.003]])
        draw.line([tuple(p) for p in poly]+[tuple(poly[0])],fill='#ffe462',width=3)
        draw.text(tuple(poly[0]+[4,-23]),'B',font=self.small,fill='#ffe462')
        if self.trace is None:
            label='평가 표시: 노랑 B 경계 · 빨강 실제 빔 외곽'
            beam=next(v['body_name'] for v in host.objects.values() if v['kind']=='long_beam')
            ids=[g for g in range(self.model.ngeom) if self.model.geom_bodyid[g]==self.model.body(beam).id]
            points=self.np.concatenate([self.np.array(list(itertools.product(*zip(-self.model.geom_size[g],self.model.geom_size[g]))))@self.data.geom_xmat[g].reshape(3,3).T+self.data.geom_xpos[g] for g in ids])
            lo,hi=points.min(axis=0),points.max(axis=0)
            box=self.project([[lo[0],lo[1],.004],[hi[0],lo[1],.004],[hi[0],hi[1],.004],[lo[0],hi[1],.004]])
            draw.line([tuple(p) for p in box]+[tuple(box[0])],fill='#ff6459',width=3)
        else:
            label='평가 전용 오버레이: 주황 추정 위치 · 청록 실제 위치 (제어 입력 아님)'
            row=self.trace.at(host.now)
            actual=self.data.body('r3__robot').xpos.copy();self.actual_path.append(actual[:2].tolist())
            if row:
                u,v=row['local_pose'][:2];ox,oy,yaw=self.origin
                est=[ox+math.cos(yaw)*u-math.sin(yaw)*v,oy+math.sin(yaw)*u+math.cos(yaw)*v,.04]
                self.estimated_path.append(est[:2])
                for trail,color in [(self.actual_path,'#40e0cf'),(self.estimated_path,'#ff9d3c')]:
                    pix=self.project([[*p,.04] for p in trail])
                    if len(pix)>1:draw.line([tuple(p) for p in pix],fill=color,width=2)
                    a,b=pix[-1];draw.ellipse((a-5,b-5,a+5,b+5),fill=color)
                dist=math.dist(actual[:2],self.origin[:2]);pred=math.dist(est[:2],self.origin[:2])
                draw.text((970,352),f'실제 시작점 거리 {dist:.3f}m',font=self.small,fill='#40e0cf')
                draw.text((970,378),f'추정 시작점 거리 {pred:.3f}m',font=self.small,fill='#ff9d3c')
                if row.get('declared_return'):
                    draw.text((970,412),'참 귀환' if self.return_valid else '거짓 귀환',font=self.font,fill='#40e0cf' if self.return_valid else '#ff6459')
                a,b=self.project([[*self.origin[:2],.04]])[0]
                draw.ellipse((a-9,b-9,a+9,b+9),outline='white',width=2)
        draw.text((8,32),label,font=self.small,fill='#ffe462')
        area=420//len(self.robots)
        for i,rid in enumerate(self.robots):
            y=60+i*area;draw.text((970,y+2),rid+' own RGB',font=self.small,fill='white')
            im=Image.fromarray(own[rid][1]);im.thumbnail((320,min(area-22,240)),Image.Resampling.LANCZOS)
            canvas.paste(im,(960+(320-im.width)//2,y+22))
        self.last=self.np.asarray(canvas).tobytes();self.process.stdin.write(self.last)
        self.frames+=1;self.next_t+=.2

    def close(self):
        try:
            # Explicit 1.5s terminal still makes B placement / return error visible.
            if self.last:
                for _ in range(60):self.process.stdin.write(self.last)
            self.process.stdin.close()
            if self.process.wait(timeout=30) or not self.frames:raise RuntimeError('video encoding failed')
        finally:
            if self.process.poll() is None:self.process.kill();self.process.wait()
            self.renderer.close()
