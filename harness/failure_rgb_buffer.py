"""Recording-only last ten SIM seconds, independent of training cameras."""
from collections import deque
import hashlib
import json
from pathlib import Path


class FailureRGBBuffer:
    def __init__(self,out):
        self.out=Path(out);self.frames=deque()

    def add(self,t,jpeg,*,camera):
        # 10 SIM seconds / 10Hz are the user's explicit recording contract.
        self.frames.append((float(t),bytes(jpeg),camera))
        while self.frames and self.frames[0][0]<t-10.-1e-8:self.frames.popleft()

    def flush(self,reason):
        self.out.mkdir(parents=True,exist_ok=True);records=[]
        for i,(t,jpeg,camera) in enumerate(self.frames):
            p=self.out/f'{i:04d}.jpg';p.write_bytes(jpeg)
            records.append(dict(t=t,camera=camera,path=p.name,bytes=len(jpeg),sha256=hashlib.sha256(jpeg).hexdigest()))
        value=dict(reason=reason,recording_only=True,training_rgb=False,hz=10,span_sim_s=10,
            frame_N=len(records),bytes=sum(r['bytes'] for r in records),frames=records)
        (self.out/'manifest.json').write_text(json.dumps(value,indent=2)+'\n')
        return value


def record_backend_frame(buffer,backend,robot):
    """Render a recorder-owned frame, leaving the control port ID untouched."""
    jpeg=backend.world.render_jpeg(robot_id=robot,camera='robot_cam')
    buffer.add(backend.now,jpeg,camera=robot+'/robot_cam')
