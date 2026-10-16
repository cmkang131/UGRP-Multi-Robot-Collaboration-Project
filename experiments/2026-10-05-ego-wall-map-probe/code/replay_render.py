"""Headless re-render of recorded robot-camera frames at a DIFFERENT wall height.

Refs #216. **Physical simulation runs: 0.** Loads the recorded ``scene.xml``, sets
the recorded ``qpos``/``qvel``, calls ``mj_forward`` and renders the wrist camera.
No ``mj_step`` anywhere (see WHY_NO_STEP below). The recorded episode directory is
opened read-only; nothing is written back into it.

Why this works at all
---------------------
The recorded frames are a deterministic function of ``(scene.xml, qpos)``: the
run that produced them rendered ``r1__robot_cam`` through
``mujoco.Renderer(640, 480)`` with ``MjvOption.geomgroup`` all-on except groups
4 and 5, then pushed the pinhole image through the OpenCV fisheye map
``raw_fisheye_remap(640, 480)`` and encoded it as JPEG quality 82.  Every one of
those inputs is recoverable from the episode, so re-running the same steps on the
same state reproduces the recorded JPEG **byte for byte** (sha256 in
``frames.jsonl``).  ``--verify-recorded`` re-checks exactly that.

The map JSON is deliberately NOT the lever.  ``apply_wall_profile``
(sim/zone_arena.py:214) only rewrites ``height_m`` in the map dictionary, which
never reaches the renderer: the pixels come from MuJoCo geom geometry baked into
``scene.xml``, and ``wall_probe.py:137`` reads the recorded JPEG.  So the height
is applied to the scene geometry itself, before the model is compiled.

Wall height mechanism
---------------------
A wall geom in the recorded scene is a ``<geom type="box" name="zone_<wall id>">``
whose ``pos`` z and ``size`` z are both ``height/2`` -- the same convention
``sim.zone_arena._geom`` writes.  Re-rendering at height H therefore means
rewriting those two attributes for every wall geom and re-compiling, so MuJoCo
recomputes its own derived model quantities (geom_rbound and friends) instead of
us leaving a stale model.  Only the six ``zone_wall_*`` geoms are touched; the
``zone_pickup`` / ``zone_zone_*`` / ``zone_slot_*`` floor-paint geoms sit at
z ~ 0.001 m and are excluded by name.  The wall set is cross-checked against
``inputs/static_map.json`` so "every wall, and only walls" is enforced, not
assumed.

WHY_NO_STEP
-----------
``mj_step`` integrates ``qvel`` and moves the state off the recorded trajectory,
so the render would no longer be *the* recorded pose.  Concretely, from a
recorded frame one ``mj_step`` already moved qpos by 2.1 mm and qvel by 8.5 m/s
(impulses from the recorded contacts); accumulated over a trajectory that is
metres of drift, and every frame would silently be a different pose than the one
the detector is being scored against.  ``mj_forward`` alone evaluates kinematics,
constraints and sensors at the recorded state and integrates nothing, so the
render is a pure function of that state.  Side effect: contacts are evaluated but
never resolved, and because the wall geoms are resized on a recompiled XML the
broadphase is consistent for the new size.  Contacts never enter the pixels
anyway -- rendering reads geometry only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import mujoco
import numpy as np
from PIL import Image

# Recorded episode directories live in the primary checkout's outputs/, never in
# this repository: a 640x480 JPEG is well over 1 MiB per frame and must not be
# committed under experiments/.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUTS_ROOT = Path('/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe')

sys.path.insert(0, str(REPO_ROOT))
from sim.masterpi_camera_profile import raw_fisheye_remap  # noqa: E402

# Matches sim/multi_masterpi_production.py:_render_rgb_direct -- groups 4 (floor
# overlays) and 5 (the camera's own housing and the held cargo) are excluded from
# the actor-visible pixels.
HIDDEN_GEOM_GROUPS = (4, 5)
WALL_GEOM_PREFIX = 'zone_wall_'


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_episode(ep_dir: Path, robot: str) -> tuple[list[dict], list[dict], Path, Path]:
    """Recorded trajectory, recorded frames, and the paths they came from.

    ``trajectory.jsonl`` and ``robots/<robot>/frames.jsonl`` are 1:1 and in the
    same sim-time order (checked here, not assumed): line i of each describes the
    same instant, so a trajectory line index is a valid frame index.  ``frame_id``
    in frames.jsonl is 1-based and ``path`` is the episode-relative JPEG.
    """
    traj = read_jsonl(ep_dir / 'eval_only' / 'trajectory.jsonl')
    frames_rel = None
    for rel in (Path('inputs') / 'frames.jsonl', Path('robots') / robot / 'frames.jsonl'):
        if (ep_dir / rel).exists():
            frames_rel = rel
            break
    if frames_rel is None:
        raise FileNotFoundError(f'no frames.jsonl for {robot} under {ep_dir}')
    frames = read_jsonl(ep_dir / frames_rel)
    if len(frames) != len(traj):
        raise ValueError(f'{len(frames)} frames vs {len(traj)} trajectory steps; not 1:1')
    for i, (f, s) in enumerate(zip(frames, traj)):
        if abs(float(f['sim_time']) - float(s['t'])) > 1e-9:
            raise ValueError(f'line {i}: frame sim_time {f["sim_time"]} != trajectory t {s["t"]}')
    return traj, frames, ep_dir / frames_rel, ep_dir


def scene_with_wall_height(scene_xml: Path, static_map_path: Path, height_m: float) -> str:
    """The recorded scene with every wall geom raised/lowered to ``height_m``.

    Returns XML text, not a compiled model, so the caller compiles the height it
    wants.  Raises if the wall set implied by the scene and by the static map
    disagree -- a silent partial resize would produce frames whose geometry does
    not match the ground truth the detector is scored against.
    """
    root = ET.fromstring(scene_xml.read_text())
    by_name = {g.get('name'): g for g in root.iter('geom')}
    scene_walls = {n for n in by_name if n and n.startswith(WALL_GEOM_PREFIX)}

    static = json.loads(static_map_path.read_text())
    map_walls = {'zone_' + o['id'] for o in static['obstacles'] if o.get('kind') == 'wall'}
    if scene_walls != map_walls:
        raise ValueError(
            'wall geom set disagrees with the static map; refusing to render a partial resize.\n'
            f'  scene only : {sorted(scene_walls - map_walls)}\n'
            f'  map only    : {sorted(map_walls - scene_walls)}')

    half = height_m / 2.0
    for name in sorted(scene_walls):
        geom = by_name[name]
        pos = [float(v) for v in geom.get('pos').split()]
        size = [float(v) for v in geom.get('size').split()]
        # Same convention as sim/zone_arena.py::_geom: the box is centred on
        # height/2, so its base stays on the floor at z=0 and its top is at height.
        pos[2] = half
        size[2] = half
        geom.set('pos', ' '.join(repr(float(v)) for v in pos))
        geom.set('size', ' '.join(repr(float(v)) for v in size))
    return ET.tostring(root, encoding='unicode')


def make_renderer(model: mujoco.MjModel, width: int, height: int):
    """One renderer + one MjvOption, created once and reused for every frame.

    Creating and tearing down a GL context per frame is fragile on macOS (a
    throwaway harness that re-created one renderer per frame produced spurious
    sha256 mismatches on r2 while a single reused renderer matched 186/186).
    """
    option = mujoco.MjvOption()
    option.geomgroup[:] = 1
    for group in HIDDEN_GEOM_GROUPS:
        option.geomgroup[group] = 0
    return mujoco.Renderer(model, height=height, width=width), option


def render_robot_cam(renderer, option, model, data, camera: str, fisheye_map) -> np.ndarray:
    """RGB uint8 exactly as the recorder produced it: pinhole render, then fisheye remap.

    Matches sim/multi_masterpi_production.py::_render_rgb_direct for camera
    'robot_cam'.  The camera's intrinsics are already baked into the recorded
    scene.xml as focalpixel/principalpixel, so nothing is re-derived here.
    """
    renderer.update_scene(data, camera=camera, scene_option=option)
    ideal = renderer.render().copy()
    map_x, map_y = fisheye_map
    return cv2.remap(ideal, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def encode_jpeg(rgb: np.ndarray, quality: int) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format='JPEG', quality=int(quality))
    return buf.getvalue()


def parse_frame_range(spec: str, total: int) -> list[int]:
    """'START:END' with an exclusive END; 'START:' means 'to the end'."""
    lo_s, _, hi_s = spec.partition(':')
    lo = int(lo_s) if lo_s.strip() else 0
    hi = int(hi_s) if hi_s.strip() else total
    if not 0 <= lo <= hi <= total:
        raise ValueError(f'--frame-range {spec} outside [0, {total}]')
    return list(range(lo, hi))


def check_output_dir(raw: str, allow_outside: bool) -> Path:
    """Refuse to write frames into the repository; default root is outputs/.

    A 640x480 JPEG is >1 MiB per frame and experiments/ is version controlled,
    so a run that defaults into the repo would put hundreds of megabytes into a
    commit.  The output directory is therefore a required flag with no default
    that lives in the repo.
    """
    out = Path(raw).expanduser().resolve()
    repo = REPO_ROOT.resolve()
    if out == repo or repo in out.parents:
        raise SystemExit(f'refusing to write frames inside the repository: {out}\n'
                         f'  use the outputs root, e.g. --output-dir {DEFAULT_OUTPUTS_ROOT}/<name>')
    if DEFAULT_OUTPUTS_ROOT.resolve() not in out.parents and not allow_outside:
        raise SystemExit(
            f'--output-dir {out} is not under {DEFAULT_OUTPUTS_ROOT}\n'
            '  pass --allow-outside-outputs if this run genuinely belongs elsewhere')
    out.mkdir(parents=True, exist_ok=True)
    return out


def run(args: argparse.Namespace) -> int:
    started = time.time()
    ep_dir = Path(args.episode).expanduser().resolve()
    out_dir = check_output_dir(args.output_dir, args.allow_outside_outputs)
    traj, frames, frames_rel, ep_dir = load_episode(ep_dir, args.robot)

    if args.frame:
        wanted = [int(i) for i in args.frame]
    elif args.frame_range:
        wanted = parse_frame_range(args.frame_range, len(traj))
    else:
        wanted = list(range(len(traj)))
    if not wanted:
        raise SystemExit('no frames selected')

    width, height = 640, 480
    xml = scene_with_wall_height(ep_dir / 'scene.xml', ep_dir / 'inputs' / 'static_map.json',
                                 args.wall_height)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    camera = args.camera or f'{args.robot}__robot_cam'

    wall_geoms = [i for i in range(model.ngeom)
                  if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith(WALL_GEOM_PREFIX)]
    # geom_size[2] is a half-extent, so the height is twice it. Reading it back off
    # the compiled model is the check that the requested height really reached MuJoCo.
    wall_heights = sorted({round(float(model.geom_size[i][2]) * 2.0, 6) for i in wall_geoms})
    if wall_heights != [round(args.wall_height, 6)]:
        raise SystemExit(f'compiled wall heights {wall_heights} != requested {args.wall_height}')

    renderer, option = make_renderer(model, width, height)
    fisheye_map = raw_fisheye_remap(width, height)

    # DETERMINISM. No RNG is consulted anywhere on this path, so a seed would be
    # decoration: there is no sampling to seed. What makes the output byte-stable
    # is that every input is a pure function -- the model is a pure function of
    # (scene.xml, wall height), MjData is set directly from the recorded
    # float64 qpos/qvel text, mj_forward is deterministic and integrates nothing,
    # and the fisheye remap map is a cached pure function of (width, height).
    # Two runs with the same episode, frames and wall height produce identical
    # JPEGs, and --verify-recorded proves the 0.40 m case equals the recording.
    print(f'episode      {ep_dir}')
    print(f'frames       {frames_rel} ({len(traj)} steps, 1:1 with trajectory.jsonl)')
    print(f'camera       {camera}  {width}x{height}  jpeg_quality={args.jpeg_quality}')
    print(f'wall height  {args.wall_height:.3f} m applied to {len(wall_geoms)} wall geoms')
    print(f'output       {out_dir}')
    print()

    verified = 0
    for n, idx in enumerate(wanted):
        if not 0 <= idx < len(traj):
            raise SystemExit(f'frame {idx} outside [0, {len(traj)})')
        step = traj[idx]
        t0 = time.perf_counter()
        data.qpos[:] = np.asarray(step['qpos'], dtype=np.float64)
        data.qvel[:] = np.asarray(step['qvel'], dtype=np.float64)
        data.time = float(step['t'])
        # mj_forward only. See WHY_NO_STEP in the module docstring.
        mujoco.mj_forward(model, data)
        rgb = render_robot_cam(renderer, option, model, data, camera, fisheye_map)
        blob = encode_jpeg(rgb, args.jpeg_quality)
        path = out_dir / f'{args.robot}_{idx:05d}_h{args.wall_height:.3f}.jpg'
        path.write_bytes(blob)
        elapsed = time.perf_counter() - t0

        note = ''
        if args.verify_recorded:
            recorded = cv2.imread(str(ep_dir / frames[idx]['path']), cv2.IMREAD_COLOR)
            mine = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
            diff = np.abs(mine.astype(np.int32) - recorded.astype(np.int32))
            same = hashlib.sha256(blob).hexdigest() == frames[idx]['sha256']
            verified += same
            note = (f'  verify={"sha256-match" if same else "DIFFERS"}'
                    f' mean_abs={diff.mean():.4f} max_abs={diff.max()}')
        print(f'frame {idx:5d} (id {frames[idx]["frame_id"]:5d})  t={float(step["t"]):7.3f}s  '
              f'h={args.wall_height:.3f}m  {elapsed * 1000:6.1f} ms  {path}{note}', flush=True)

    renderer.close()
    if args.verify_recorded:
        print(f'\nverify_recorded: {verified}/{len(wanted)} frames byte-identical to the recorded JPEG '
              f'(sha256) at h={args.wall_height:.3f} m')
    print(f'total {time.time() - started:.2f} s for {len(wanted)} frames')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split('\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'Example:\n  {sys.executable} replay_render.py \\\n'
               f'      --episode {DEFAULT_OUTPUTS_ROOT.parent}/v98-dev-.../zone_wide_door_geometry_v3 \\\n'
               f'      --wall-height 0.50 --frame 100 --output-dir {DEFAULT_OUTPUTS_ROOT}/h050\n')
    ap.add_argument('--episode', required=True, help='recorded episode directory (read-only)')
    ap.add_argument('--wall-height', type=float, required=True, metavar='M',
                    help='wall height in metres to render every wall geom at')
    ap.add_argument('--output-dir', required=True, metavar='DIR',
                    help=f'where to write JPEGs; must be outside the repo, e.g. {DEFAULT_OUTPUTS_ROOT}/<name>')
    ap.add_argument('--allow-outside-outputs', action='store_true',
                    help=f'permit an output dir outside {DEFAULT_OUTPUTS_ROOT}')
    ap.add_argument('--robot', default='r1', help='which robot\'s recorded frames to use (default r1)')
    ap.add_argument('--camera', default=None, help='override camera name (default <robot>__robot_cam)')
    ap.add_argument('--frame', nargs='*', type=int, default=None, metavar='IDX',
                    help='explicit recorded frame indices')
    ap.add_argument('--frame-range', default=None, metavar='START:END',
                    help='half-open frame index range, e.g. 0:50 (END optional)')
    ap.add_argument('--jpeg-quality', type=int, default=82, help='JPEG quality (default 82, the recorded value)')
    ap.add_argument('--verify-recorded', action='store_true',
                    help='diff each render against the recorded JPEG and compare sha256')
    return run(ap.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
