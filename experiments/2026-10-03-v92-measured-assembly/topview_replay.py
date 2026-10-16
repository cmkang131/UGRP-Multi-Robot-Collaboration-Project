"""Top-view REPLAY of recorded eval-only qpos (visualisation only; not a physics rerun, not robot input).

Adapted from outputs/v91-heldout-videos-20261003/topview_replay.py. Robot base free-joint
qpos addresses are read from the recorded scene by joint name instead of hard-coded offsets.
Left: whole-pair overview centred on the r1/r2 extent. Right: close view following r1.
Every 4th 20 Hz trajectory row (5 Hz) is written at 20 fps -> 4x SIM speed.
"""
import json, sys, os, subprocess, numpy as np, mujoco

run, out = sys.argv[1], os.path.abspath(sys.argv[2])
os.chdir(run)
m = mujoco.MjModel.from_xml_path('scene.xml'); d = mujoco.MjData(m)
a1 = int(m.joint('r1__base_free').qposadr[0]); a2 = int(m.joint('r2__base_free').qposadr[0])
rows = [json.loads(l) for l in open('eval_only/trajectory.jsonl')]
assert len(rows[0]['qpos']) == m.nq, (len(rows[0]['qpos']), m.nq)
rows = rows[::4]
q = np.array([r['qpos'] for r in rows])
r1 = q[:, a1:a1 + 2]; r2 = q[:, a2:a2 + 2]
allxy = np.vstack([r1, r2]); c = (allxy.min(0) + allxy.max(0)) / 2
span = max(np.ptp(allxy[:, 0]), np.ptp(allxy[:, 1])) + 1.2
W, H = 640, 480
ren = mujoco.Renderer(m, H, W)


def cam(look, dist):
    cm = mujoco.MjvCamera(); cm.type = mujoco.mjtCamera.mjCAMERA_FREE
    cm.lookat[:] = [look[0], look[1], 0.0]; cm.distance = dist; cm.elevation = -90; cm.azimuth = 90
    return cm


ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{2*W}x{H}',
    '-r', '20', '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '23', out], stdin=subprocess.PIPE)
for i, r in enumerate(rows):
    d.qpos[:] = r['qpos']; mujoco.mj_forward(m, d)
    ren.update_scene(d, camera=cam(c, span * 1.15)); a = ren.render()
    ren.update_scene(d, camera=cam(r1[i], 1.2)); b = ren.render()
    ff.stdin.write(np.hstack([a, b]).tobytes())
ff.stdin.close(); rc = ff.wait()
print(json.dumps({'output': out, 'frames': len(rows), 'qposadr': {'r1': a1, 'r2': a2},
                  'center': c.tolist(), 'span_m': float(span), 'ffmpeg_rc': rc,
                  'label': 'REPLAY of recorded eval_only qpos; not a physics rerun'}))
