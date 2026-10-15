"""Recording-only 2Hz overview and own-camera review; never control input."""
import json
from pathlib import Path


class PlaybackRecorder:
    def __init__(self,out,world,*,top_camera='cctv_top'):
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.world,self.top=world,top_camera;self.rows=[];self.last_slot=None

    def observe(self,now):
        # Called on existing native .1s clock. User requests whole-run2Hz.
        slot=round(now*2)
        if abs(now*2-slot)>1e-6 or slot==self.last_slot:return
        self.last_slot=slot;files={}
        for camera in ('overview','r1','r2','r3'):
            jpeg=(self.world.render_team_jpeg(camera=self.top) if camera=='overview' else
                  self.world.render_jpeg(robot_id=camera,camera='robot_cam'))
            p=self.out/f'{len(self.rows):05d}-{camera}.jpg';p.write_bytes(jpeg)
            files[camera]=p.name
        self.rows.append(dict(t=now,files=files))
        self.flush()

    def flush(self):
        (self.out/'manifest.json').write_text(json.dumps(dict(hz=2,recording_only=True,controller_reads=0,frames=self.rows),indent=2)+'\n')
