"""Evaluation-only fixed cameras; no renderer or extra state when disabled."""
import os
import shutil
import subprocess


def enabled():
    value = os.environ.get('UGRP_S3_OVERVIEW', 'off')
    if value not in ('off', 'on_v1'):
        raise ValueError('UGRP_S3_OVERVIEW must be off or on_v1')
    return value == 'on_v1'


class Overview:
    def __init__(self, host):
        import mujoco
        self.mj = mujoco
        # Separate rendering model/data: even visual settings never touch physics.
        self.model = mujoco.MjModel.from_xml_path(str(host.out/'scene.xml'))
        self.model.vis.global_.offwidth = max(640, self.model.vis.global_.offwidth)
        self.model.vis.global_.offheight = max(480, self.model.vis.global_.offheight)
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=480, width=640)
        lookat = (1.35, .15, .10) if host.bundle['case'] == 'pair' else (-.2, -2.05, .10)
        self.cameras = []
        for azimuth, elevation in ((135., -55.), (90., -12.)):
            camera = mujoco.MjvCamera()
            camera.type = mujoco.mjtCamera.mjCAMERA_FREE
            camera.lookat[:] = lookat
            camera.distance, camera.azimuth, camera.elevation = 2.8, azimuth, elevation
            self.cameras.append(camera)
        self.next_time = host.now
        self.frames = 0
        self.process = subprocess.Popen([shutil.which('ffmpeg'), '-nostdin', '-n', '-v', 'error',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1280x480', '-r', '20', '-i', '-',
            '-an', '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(host.out.parent/'overview.mp4')],
            stdin=subprocess.PIPE)

    def frame(self, host):
        import numpy as np
        if host.now + 1e-8 < self.next_time:
            return
        # Copy state into the observer; never forward/step the live world.
        self.mj.mj_copyData(self.data, host.world.model, host.world.data)
        frames = []
        for camera in self.cameras:
            self.renderer.update_scene(self.data, camera=camera)
            frames.append(self.renderer.render().copy())
        self.process.stdin.write(np.concatenate(frames, axis=1).tobytes())
        self.frames += 1
        self.next_time += .2  # 5 SIM frames/s played at 20 fps = fourfold speed.

    def close(self):
        try:
            self.process.stdin.close()
            if self.process.wait(timeout=30) or not self.frames:
                raise RuntimeError('overview encoder failed or recorded no frames')
        finally:
            self.renderer.close()


def recording_backend(base):
    class Recorded(base):
        overview = None

        def eval_sample(self):
            if self.overview is None:
                self.overview = Overview(self)
            self.overview.frame(self)
            return super().eval_sample()

        def close(self):
            try:
                if self.overview is not None:
                    self.overview.close()
                    self.overview = None
            finally:
                super().close()
    return Recorded
