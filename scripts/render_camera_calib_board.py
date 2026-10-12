"""Lab-style extrinsic calibration capture (render only; run on a sim VM, one process, no controller).

A flat checkerboard (8 x 5 squares of 0.10 m, white margin of one square, top face z=0.0045 m) lies on the floor at a
fixed, tape-measured place. The robot is put at marked floor positions (lab fixture: x, y, yaw of the chassis) and
renders its own RGB with a fixed arm posture. Only the frames + the marked placements are written; fitting is offline
(`scripts/fit_camera_calib.py`). The simulator camera pose is never read.
"""
import json, math, sys
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0, '.')
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
POSTURE = sys.argv[2] if len(sys.argv) > 2 else 'SEARCH,LOOK_AHEAD'
from harness import active_camera as AC

BOARD = dict(center_m=[1.5, -0.9], square_m=0.10, squares=[8, 5], margin_squares=1, top_z_m=0.0045, plate_z_m=0.004,
             inner_corners=[7, 4])


def add_board(xml):
    root = ET.fromstring(xml); world = root.find('worldbody')
    s, (nx, ny), m = BOARD['square_m'], BOARD['squares'], BOARD['margin_squares']
    cx, cy = BOARD['center_m']; z0 = BOARD['plate_z_m']; z1 = BOARD['top_z_m']
    ET.SubElement(world, 'geom', name='calib_plate', type='box', pos=f'{cx} {cy} {z0/2}',
                  size=f'{(nx+2*m)*s/2} {(ny+2*m)*s/2} {z0/2}', rgba='.95 .95 .95 1', contype='0', conaffinity='0', group='0')
    for i in range(nx):
        for j in range(ny):
            if (i+j) % 2 == 0:
                x = cx+(i+.5-nx/2)*s; y = cy+(j+.5-ny/2)*s
                ET.SubElement(world, 'geom', name=f'calib_sq_{i}_{j}', type='box', pos=f'{x} {y} {(z0+z1)/2}',
                              size=f'{s/2} {s/2} {(z1-z0)/2}', rgba='.02 .02 .02 1', contype='0', conaffinity='0', group='0')
    return ET.tostring(root, encoding='unicode')


from scripts._calib_world import build_world
world, definition = build_world(xml_extra=add_board)
import mujoco
for rid in list(world.controllers):
    if rid != 'r1':  # park the other robots out of the view (lab: nobody else on the board)
        world.robot(rid).set_base_pose_for_test((4.9 if rid == 'r2' else 4.9, -3.0 if rid == 'r2' else 1.2, .0323), 0.)
placements = []
for name in POSTURE.split(','):
    base_name, _, override = name.partition('@')   # e.g. SEARCH@6=1300 (pan validation posture)
    servo = dict(getattr(AC, base_name))
    if override:
        servo.update({int(k): int(v) for k, v in (o.split('=') for o in override.split(';'))})
    from harness.active_camera import transform as _fk  # arrangement only: aim the nominal optical axis at the board
    _f = _fk(servo)[1][:, 2]; aim = math.atan2(_f[1], _f[0])
    n = 0
    for d in (1.0, 1.15, 1.3, 1.45):
        for k, bearing in enumerate((-25., -12., 0., 12., 25.)):
            for off in (-8., 8.):
                b = math.radians(bearing); yaw = b+math.radians(off)-aim
                x = BOARD['center_m'][0]-d*math.cos(b); y = BOARD['center_m'][1]-d*math.sin(b)
                world.robot('r1').set_base_pose_for_test((x, y, .0323), yaw)
                mujoco.mj_forward(world.model, world.data)
                world._team_joint_move_servos({'r1': servo}, 1.5, settle_s=2.0)
                world.robot('r1')._sync_real_camera_mount(); mujoco.mj_forward(world.model, world.data)
                fn = f'{name}_{n:02d}.jpg'
                (OUT/fn).write_bytes(world.render_jpeg(robot_id='r1', camera='robot_cam', quality=95))
                placements.append(dict(file=fn, posture=name, servo=servo, base_xy_yaw=[round(x, 4), round(y, 4), round(yaw, 5)]))
                n += 1
json.dump(dict(board=BOARD, placements=placements), open(OUT/'placements.json', 'w'), indent=1)
print('frames', len(placements)); world.close()
