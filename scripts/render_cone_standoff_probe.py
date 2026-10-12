"""Render-only project-check of planned cone stand-off poses (sim VM, one process). Poses come from a JSON list
[[x, y, yaw], ...] (planner output, map frame). Writes frames + the placements; detection/evaluation are offline."""
import json, math, sys
from pathlib import Path
sys.path.insert(0, '.')
poses = json.loads(Path(sys.argv[1]).read_text()); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
from harness.active_camera import SEARCH
from scripts._calib_world import build_world
static = json.loads(Path('maps/zones_e2e/zone_wide_door_e2e_b80_cones_v1.json').read_text())
world, definition = build_world(static_map=static)
import mujoco
for rid in list(world.controllers):
    if rid != 'r1': world.robot(rid).set_base_pose_for_test((4.9, -3.0 if rid == 'r2' else 1.2, .0323), 0.)
placements = []
for i, (x, y, yaw) in enumerate(poses):
    world.robot('r1').set_base_pose_for_test((x, y, .032355118817659255), yaw)
    mujoco.mj_forward(world.model, world.data)
    world._team_joint_move_servos({'r1': dict(SEARCH)}, 1.5, settle_s=2.0)
    world.robot('r1')._sync_real_camera_mount(); mujoco.mj_forward(world.model, world.data)
    (OUT/f'f{i:03d}.jpg').write_bytes(world.render_jpeg(robot_id='r1', camera='robot_cam', quality=95))
    placements.append(dict(frame=i, robot=[x, y, yaw]))
json.dump(dict(placements=placements), open(OUT/'evaluation_ground_truth.json', 'w'), indent=1)
print('frames', len(poses)); world.close()
