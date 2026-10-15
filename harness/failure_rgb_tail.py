"""Recording-only own-camera SIM-time ring; never supplies controller input."""
from collections import deque
import hashlib

from harness.grasp_act_data import write_json


class FailureRGBTail:
    # User 2026-10-15: preceding 10 SIM seconds, 10 Hz; inclusive endpoints.
    def __init__(self):
        self.frames = deque()
        self.total_frames = 0
        self.peak_bytes = 0

    def capture(self, world, roles, now):
        pictures = {rid: bytes(world.render_jpeg(robot_id=rid, camera='robot_cam')) for rid in roles}
        self.frames.append((now, pictures))
        self.total_frames += len(pictures)
        while self.frames and self.frames[0][0] < now-10.-1e-8:
            self.frames.popleft()
        self.peak_bytes = max(self.peak_bytes, sum(len(b) for _,fs in self.frames for b in fs.values()))

    def finish(self, out, *, failed):
        out.mkdir(parents=True, exist_ok=True)
        manifest = []
        if failed:
            for i, (now, fs) in enumerate(self.frames):
                for rid, data in fs.items():
                    p = out/rid/f'{i:04d}.jpg'
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
                    manifest.append(dict(t=now, robot=rid, path=str(p.relative_to(out)),
                        bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        write_json(out/'manifest.json', dict(recording_only=True, controller_input=False,
            hz=10, window_sim_s=10, failed_or_interrupted=failed,
            total_captured_frames=self.total_frames, peak_buffer_bytes=self.peak_bytes,
            stored_bytes=sum(x['bytes'] for x in manifest), frames=manifest))
