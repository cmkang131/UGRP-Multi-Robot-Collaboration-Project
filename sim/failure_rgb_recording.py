"""Recording only: bounded 10 SIM-second own-RGB buffer, no control output."""
from collections import deque
import hashlib
import json

MODE='own_rgb_last10_10hz_v1'


class FailureRGB:
    def __init__(self,mode=MODE):
        if mode!=MODE:raise ValueError('unknown failure RGB recording option')
        self.rows=deque();self.mode=mode;self.captured=0

    def capture(self,t,cameras):
        row={rid:capture() for rid,capture in cameras.items()}
        self.rows.append((t,row));self.captured+=len(row)
        # User 2026-10-15: last 10 SIM seconds, 10Hz. The runner's existing
        # 0.1 SIM-second loop defines the sampling clock; no wall deadline.
        while self.rows and self.rows[0][0]<t-10-1e-8:self.rows.popleft()

    def finish(self,out,*,failed):
        files=[]
        if failed:
            for t,row in self.rows:
                for rid,jpg in row.items():
                    p=out/'failure-rgb'/rid/f'{t:.6f}.jpg';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(jpg)
                    files.append(dict(t=t,path=str(p.relative_to(out)),bytes=len(jpg),sha256=hashlib.sha256(jpg).hexdigest()))
        record=dict(mode=self.mode,control_input=False,training_rgb=False,captured=self.captured,
            retained_frames=len(files),bytes=sum(f['bytes'] for f in files),
            retained_range_sim_s=[self.rows[0][0],self.rows[-1][0]] if files else None,files=files)
        (out/'failure-rgb-recording.json').write_text(json.dumps(record,indent=2)+'\n')
        return {k:v for k,v in record.items() if k!='files'}
