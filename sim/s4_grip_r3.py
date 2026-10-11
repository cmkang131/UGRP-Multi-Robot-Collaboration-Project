"""r3-only recording additions to the unchanged s4grip2 physical backend."""
import base64
from sim.s4_grip_dataset import PhysicsBackend as Previous


class PhysicsBackend(Previous):
    def capture_r3(self, relative_s, phase):
        obs=self.ports['r3'].capture()
        jpeg=base64.b64decode(obs['image'],validate=True)
        relative=f'robots/r3/rgb/{self.frame:05d}.jpg';path=self.out/relative
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(jpeg)
        self._append('robots/r3/frames.jsonl',dict(**{k:v for k,v in obs.items() if k!='image'},
            path=relative,relative_s=relative_s,phase=phase,commanded_servo=dict(self.commands['r3'])))
        self.frame+=1
        return obs['image']
