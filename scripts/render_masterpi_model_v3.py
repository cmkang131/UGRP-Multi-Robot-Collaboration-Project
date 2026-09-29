#!/usr/bin/env python3
"""Offscreen still renders for the MasterPi visual v3 review (no physics steps).

Only ``mj_forward`` is called: joint angles are written into ``qpos`` for a
static pose, then MuJoCo's offscreen renderer draws the frame.  Nothing is
simulated and no model is called.

Usage::

    python scripts/render_masterpi_model_v3.py --out outputs/masterpi-model-v3 \
        [--reference-dir DIR]

``--reference-dir`` may hold the official Hiwonder images (not committed; see
experiments/2026-09-28-masterpi-visual-v3/README.md for URLs).  When present the
comparison sheets include them next to the renders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim import masterpi_geometry_v3 as G  # noqa: E402
from sim.masterpi_dynamics_v2 import WHEEL_RADIUS_M, build_v2_xml  # noqa: E402
from sim.masterpi_model_v3 import (  # noqa: E402
    CAMERA_HARDWARE_GROUP,
    SONAR_MOUNT_V3,
    build_v2_appearance_xml,
    build_v3_xml,
)

POSES = {
    # arm straight up, as in Hiwonder's dimension drawing / "reset servo" pose
    "straight_up": {"arm_yaw": 0.0, "shoulder": math.pi / 2, "elbow": 0.0, "wrist_pitch": 0.0},
    # bent pose resembling the official product render
    "product": {"arm_yaw": 0.0, "shoulder": 1.25, "elbow": -0.85, "wrist_pitch": -0.25},
    # wrist camera looking at the floor ahead (search-like pose)
    "look_down": {"arm_yaw": 0.0, "shoulder": 1.6, "elbow": -1.7, "wrist_pitch": -0.95},
}
FONT_PATHS = ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf")


def _font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def load(xml: str, width: int, height: int):
    model = mujoco.MjModel.from_xml_string(xml)
    model.vis.global_.offwidth = max(width, int(model.vis.global_.offwidth))
    model.vis.global_.offheight = max(height, int(model.vis.global_.offheight))
    model.vis.quality.shadowsize = 4096
    data = mujoco.MjData(model)
    for i in range(model.ngeom):  # hide task blocks / props
        body = model.body(model.geom_bodyid[i]).name
        if body.endswith("_block") or body.startswith("beam"):
            model.geom_rgba[i][3] = 0.0
    return model, data


def pose(model, data, name: str) -> None:
    mujoco.mj_resetData(model, data)
    for joint, value in POSES[name].items():
        data.qpos[model.jnt_qposadr[model.joint(joint).id]] = value
    mujoco.mj_forward(model, data)


def _line(scene, a, b, rgba, width=2.0):
    if scene.ngeom >= scene.maxgeom:
        return
    g = scene.geoms[scene.ngeom]
    mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_LINE, np.zeros(3), np.zeros(3), np.zeros(9), np.asarray(rgba, np.float32))
    mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_LINE, width, np.asarray(a, float), np.asarray(b, float))
    scene.ngeom += 1


def _sphere(scene, p, r, rgba):
    if scene.ngeom >= scene.maxgeom:
        return
    g = scene.geoms[scene.ngeom]
    mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_SPHERE, np.array([r, r, r]), np.asarray(p, float), np.eye(3).ravel(), np.asarray(rgba, np.float32))
    scene.ngeom += 1


def render(model, data, *, lookat, distance, azimuth, elevation, width, height, ortho=False, fovy=45.0,
           sonar=None, ruler=None):
    renderer = mujoco.Renderer(model, height, width)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = lookat
    cam.distance = distance
    cam.azimuth = azimuth
    cam.elevation = elevation
    model.vis.global_.orthographic = 1 if ortho else 0
    model.vis.global_.fovy = fovy
    opt = mujoco.MjvOption()
    opt.geomgroup[CAMERA_HARDWARE_GROUP] = 1  # observer views show the camera hardware
    renderer.update_scene(data, cam, scene_option=opt)
    if ruler is not None:  # vertical cm ruler: (x, y) world, 0..top_cm
        x, y, top_cm = ruler
        _line(renderer.scene, (x, y, 0), (x, y, top_cm / 100.0), (0, 0, 0, 1), 3)
        for c in range(top_cm + 1):
            w = .014 if c % 5 == 0 else .007
            _line(renderer.scene, (x, y, c / 100.0), (x + w, y, c / 100.0), (0, 0, 0, 1), 2)
    if sonar is not None:
        p, axis = sonar
        _sphere(renderer.scene, p, .0025, (0, .45, 1, 1))
        _line(renderer.scene, p, p + .06 * np.asarray(axis), (0, .45, 1, 1), 3)
        if ruler is not None:
            _line(renderer.scene, p, (ruler[0], ruler[1], p[2]), (0, .45, 1, 1), 1.5)
    img = Image.fromarray(renderer.render())
    renderer.close()
    return img


def sonar_world(model, data):
    """World position/axis of the ultrasonic emitter centre for the overlay."""
    try:
        sid = model.site("v3_ultrasonic_site").id
        return data.site_xpos[sid].copy(), data.site_xmat[sid].reshape(3, 3)[:, 2].copy()
    except KeyError:  # v2: midpoint of the two visual cans, front face
        a, b = data.geom("ultrasonic_left"), data.geom("ultrasonic_right")
        mid = (a.xpos + b.xpos) / 2.0
        axis = data.body("robot").xmat.reshape(3, 3)[:, 0].copy()
        return mid + axis * model.geom("ultrasonic_left").size[1], axis


def caption(img: Image.Image, text: str, size=30) -> Image.Image:
    out = Image.new("RGB", (img.width, img.height + size + 22), "white")
    out.paste(img, (0, size + 22))
    ImageDraw.Draw(out).text((12, 8), text, fill=(0, 0, 0), font=_font(size))
    return out


def fit(img: Image.Image, w: int, h: int) -> Image.Image:
    img = img.convert("RGB")
    s = min(w / img.width, h / img.height)
    img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    out = Image.new("RGB", (w, h), "white")
    out.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--reference-dir", type=Path)
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    W, H = 1200, 900
    variants = {
        "v2": build_v2_xml(),
        "v2_physics_v3_look": build_v2_appearance_xml(),
        "v3_physical": build_v3_xml(),
    }
    files: dict[str, str] = {}
    sonar_report = {}
    tiles: dict[tuple[str, str], Image.Image] = {}
    for key, xml in variants.items():
        model, data = load(xml, W, H)
        # 3/4 view similar to the official product render (front-left, above)
        pose(model, data, "product")
        base = data.body("robot").xpos.copy()
        img = render(model, data, lookat=base + (0.03, 0, .12), distance=.46, azimuth=215, elevation=-16, width=W, height=H)
        tiles[(key, "product")] = img
        # side orthographic, arm straight up (matches the dimension drawing)
        pose(model, data, "straight_up")
        p, axis = sonar_world(model, data)
        sonar_report[key] = {"sonar_center_floor_m": [round(float(v), 4) for v in (p - (base[0], base[1], 0))],
                             "sonar_axis": [round(float(v), 4) for v in axis]}
        img = render(model, data, lookat=base + (0, 0, .17), distance=1.0, azimuth=270, elevation=0, width=W, height=H,
                     ortho=True, fovy=.40, sonar=(p, axis), ruler=(base[0] + .115, base[1] - .09, 35))
        tiles[(key, "side")] = img
        img = render(model, data, lookat=base + (0, 0, .17), distance=1.0, azimuth=180, elevation=0, width=W, height=H,
                     ortho=True, fovy=.40, sonar=(p, axis), ruler=(base[0] + .09, base[1] + .105, 35))
        tiles[(key, "front")] = img
        # what the wrist camera itself sees (the v3 visuals must not intrude)
        pose(model, data, "look_down")
        cam_r = mujoco.Renderer(model, 480, 640)
        cam_r.update_scene(data, camera="robot_cam")
        tiles[(key, "robot_cam")] = Image.fromarray(cam_r.render())
        cam_r.close()
        for view in ("product", "side", "front", "robot_cam"):
            path = out / f"{key}_{view}.png"
            tiles[(key, view)].save(path)
            files[path.name] = sha256(path)

    refs = {}
    if args.reference_dir and args.reference_dir.is_dir():
        for name, fname in (("product", "hiwonder_masterpi_render.png"), ("drawing", "hiwonder_masterpi_dimension_drawing.jpg")):
            p = args.reference_dir / fname
            if p.is_file():
                ref = Image.open(p)
                if ref.mode in ("RGBA", "LA", "P"):
                    ref = ref.convert("RGBA")
                    bg = Image.new("RGBA", ref.size, (255, 255, 255, 255))
                    ref = Image.alpha_composite(bg, ref)
                refs[name] = ref.convert("RGB")

    # comparison sheet 1: product-like 3/4 view
    tw, th = 700, 560
    row = [caption(fit(tiles[("v2", "product")], tw, th), "v2 (현재)"),
           caption(fit(tiles[("v3_drawing_layout", "product")], tw, th), "v3 drawing_layout_proposal"),
           caption(fit(tiles[("v3_appearance_only", "product")], tw, th), "v3 appearance_only (v2 물리 그대로)")]
    if "product" in refs:
        row.append(caption(fit(refs["product"], tw, th), "Hiwonder 공식 렌더 (참고)"))
    sheet = Image.new("RGB", (tw * len(row), row[0].height), "white")
    for i, t in enumerate(row):
        sheet.paste(t, (i * tw, 0))
    path = out / "compare_product_view.png"
    sheet.save(path)
    files[path.name] = sha256(path)

    # comparison sheet 2: side orthographic (arm up) vs official drawing
    row = [caption(fit(tiles[("v2", "side")], tw, th), "v2 옆 (정사영, 1 cm 눈금)"),
           caption(fit(tiles[("v3_drawing_layout", "side")], tw, th), "v3 drawing_layout 옆"),
           caption(fit(tiles[("v3_appearance_only", "side")], tw, th), "v3 appearance_only 옆")]
    if "drawing" in refs:
        d = refs["drawing"]
        row.append(caption(fit(d.crop((560, 150, 1180, 1060)), tw, th), "Hiwonder 공식 치수도 (옆)"))
    sheet = Image.new("RGB", (tw * len(row), row[0].height + 70), "white")
    for i, t in enumerate(row):
        sheet.paste(t, (i * tw, 0))
    v2s = sonar_report["v2"]["sonar_center_floor_m"]
    v3s = sonar_report["v3_drawing_layout"]["sonar_center_floor_m"]
    ImageDraw.Draw(sheet).text(
        (12, row[0].height + 14),
        f"파란 점·선 = 초음파 송수신면 중심과 축.  v2: 앞 {v2s[0]*1000:.1f} mm, 높이 {v2s[2]*1000:.1f} mm  →  "
        f"v3: 앞 {v3s[0]*1000:.1f} mm, 높이 {v3s[2]*1000:.1f} mm (공식 치수도에서 축척 측정, 실측 아님)",
        fill=(0, 0, 0), font=_font(26))
    path = out / "compare_side_ortho.png"
    sheet.save(path)
    files[path.name] = sha256(path)

    row = [caption(fit(tiles[(k, "front")], tw, th), f"{k} 앞 (정사영)") for k in ("v2", "v3_drawing_layout")]
    if "drawing" in refs:
        row.append(caption(fit(refs["drawing"].crop((0, 150, 560, 1060)), tw, th), "Hiwonder 공식 치수도 (앞)"))
    sheet = Image.new("RGB", (tw * len(row), row[0].height), "white")
    for i, t in enumerate(row):
        sheet.paste(t, (i * tw, 0))
    path = out / "compare_front_ortho.png"
    sheet.save(path)
    files[path.name] = sha256(path)

    row = [caption(fit(tiles[(k, "robot_cam")], 640, 480), f"{k} robot_cam") for k in variants]
    sheet = Image.new("RGB", (640 * len(row), row[0].height), "white")
    for i, t in enumerate(row):
        sheet.paste(t, (i * 640, 0))
    path = out / "compare_robot_cam.png"
    sheet.save(path)
    files[path.name] = sha256(path)

    manifest = {
        "schema": "ugrp.masterpi_model_v3.renders.v1",
        "physics_steps": 0,
        "model_calls": 0,
        "sonar_mount_v3": SONAR_MOUNT_V3,
        "sonar_measured_in_render": sonar_report,
        "wheel_radius_m": WHEEL_RADIUS_M,
        "geometry_version": G.GEOMETRY_VERSION,
        "files_sha256": files,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"out": str(out), "files": len(files)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
