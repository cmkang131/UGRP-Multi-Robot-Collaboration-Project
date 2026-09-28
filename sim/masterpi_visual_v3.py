"""MasterPi visual model v3 (appearance remodel from Hiwonder sources).

``build_v3_xml`` starts from :func:`sim.masterpi_dynamics_v2.build_v2_xml` and
changes only what the chosen profile declares:

``appearance_only``
    Physics identical to v2.  Every body, joint, inertial, actuator, camera,
    site and every colliding geom keeps its v2 value; colliding geoms that v2
    also used as visible panels are made transparent.  All v2 visual-only geoms
    (``contype=0`` and ``conaffinity=0``) are replaced by source-traced v3
    visual geoms.  The arm therefore stays on the v2 kinematic mount (yaw axis
    at the axle midpoint), which the official drawing places 48 mm further
    forward; renders of this profile show that conflict honestly.

``drawing_layout_proposal``
    Opt-in structural *proposal* for review only.  Same visuals, plus the arm
    yaw mount moved to the drawing position and the chassis/cover/arm-box
    collision proxies resized to the drawing.  Inertials, masses, actuators,
    link lengths, wheel geometry and every calibration parameter stay v2.
    Nothing selects this profile; switching scenes needs a separate PR.

v2 sources (``sim/masterpi_dynamics_v2.py``, ``sim/masterpi_geometry.py``,
``sim/masterpi_scene*.xml``) are not modified, so registered execution bundles
keep resolving to the same bytes.

Provenance of every dimension lives in :mod:`sim.masterpi_geometry_v3`.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Iterable, Mapping, Sequence

import numpy as np

from sim import masterpi_geometry_v3 as G
from sim.masterpi_camera_profile import CAMERA_LOCAL_POS_M, CAMERA_LOCAL_QUAT_WXYZ
from sim.masterpi_dynamics_v2 import (
    GRIPPER_MAX_CLOSE_M,
    TRACK_M,
    WHEEL_RADIUS_M,
    build_v2_xml,
)
from sim.masterpi_geometry import NOMINAL_YAW_AXIS_FROM_BASE_M, NOMINAL_YAW_TO_SHOULDER_M
from harness.real_geometry import LINK_2_CM, LINK_3_CM

VISUAL_MODEL_VERSION = "masterpi-visual-v3"
PROFILE_APPEARANCE_ONLY = "appearance_only"
PROFILE_DRAWING_LAYOUT = "drawing_layout_proposal"
PROFILES = (PROFILE_APPEARANCE_ONLY, PROFILE_DRAWING_LAYOUT)
V3_PREFIX = "v3_"
SONAR_SITE = "v3_ultrasonic_site"

_L2 = LINK_2_CM / 100.0
_L3 = LINK_3_CM / 100.0

# Chassis-fixed ultrasonic mount in the v2 ``robot`` body frame (origin at the
# axle midpoint, z at axle height).  The mount is on the chassis-fixed arm-base
# box, so it does not depend on the profile.  ``pos_floor_m`` is floor-referenced.
SONAR_MOUNT_V3 = {
    "version": G.GEOMETRY_VERSION,
    "pos_body_m": (G.SONAR_FACE_X_M, G.SONAR_CENTER_Y_M, G.SONAR_CENTER_Z_FLOOR_M - WHEEL_RADIUS_M),
    "pos_floor_m": (G.SONAR_FACE_X_M, G.SONAR_CENTER_Y_M, G.SONAR_CENTER_Z_FLOOR_M),
    "axis_body": (1.0, 0.0, 0.0),
    "pitch_deg": G.SONAR_PITCH_DEG,
    "transducer_spacing_m": G.SONAR_TRANSDUCER_SPACING_M,
    "transducer_diameter_m": G.SONAR_TRANSDUCER_DIAMETER_M,
    "source": "public_measured: Hiwonder MasterPi dimension drawing + glowing ultrasonic module drawing",
}

_MATERIALS = {
    "gunmetal": ("0.35", "0.45"),
    "gunmetal_edge": ("0.2", "0.3"),
    "orange_anodized": ("0.45", "0.55"),
    "servo_black": ("0.25", "0.35"),
    "silver": ("0.6", "0.6"),
    "copper": ("0.6", "0.6"),
    "rubber_orange": ("0.05", "0.1"),
    "hub_grey": ("0.1", "0.2"),
    "pcb_green": ("0.3", "0.4"),
    "pcb_black": ("0.3", "0.4"),
    "sonar_can": ("0.7", "0.7"),
    "sonar_mesh": ("0.1", "0.1"),
    "hole": ("0", "0"),
    "lens": ("0.9", "0.9"),
    "port_metal": ("0.7", "0.7"),
    "port_blue": ("0.3", "0.3"),
}


def _f(values: Iterable[float]) -> str:
    return " ".join(f"{float(v):.6f}" for v in values)


class _Builder:
    """Tiny helper that appends named, massless, non-colliding visual geoms."""

    def __init__(self, asset: ET.Element) -> None:
        self.asset = asset
        self.meshes: set[str] = set()

    def geom(self, body: ET.Element, name: str, gtype: str, mat: str, **attrs: str) -> ET.Element:
        el = ET.SubElement(body, "geom", {
            "name": V3_PREFIX + name, "type": gtype, "material": "v3_" + mat,
            "mass": "0", "contype": "0", "conaffinity": "0", "group": "0",
        })
        for key, value in attrs.items():
            el.set(key, value)
        return el

    def box(self, body, name, mat, center, half, euler=None, quat=None):
        attrs = {"pos": _f(center), "size": _f(half)}
        if euler is not None:
            attrs["euler"] = _f(euler)
        if quat is not None:
            attrs["quat"] = _f(quat)
        return self.geom(body, name, "box", mat, **attrs)

    def box_span(self, body, name, mat, lo, hi):
        lo = np.asarray(lo, float)
        hi = np.asarray(hi, float)
        return self.box(body, name, mat, (lo + hi) / 2.0, np.abs(hi - lo) / 2.0)

    def cyl(self, body, name, mat, p0, p1, radius):
        return self.geom(body, name, "cylinder", mat, fromto=_f((*p0, *p1)), size=f"{radius:.6f}")

    def capsule(self, body, name, mat, p0, p1, radius):
        return self.geom(body, name, "capsule", mat, fromto=_f((*p0, *p1)), size=f"{radius:.6f}")

    def bar(self, body, name, mat, p0, p1, width, thickness, plane="xy"):
        """Flat bar between two points; ``plane`` is the plane containing the bar width."""
        p0 = np.asarray(p0, float)
        p1 = np.asarray(p1, float)
        mid = (p0 + p1) / 2.0
        d = p1 - p0
        length = float(np.linalg.norm(d))
        if plane == "xy":
            ang = math.atan2(d[1], d[0])
            return self.box(body, name, mat, mid, (length / 2.0, width / 2.0, thickness / 2.0), euler=(0, 0, ang))
        # "xz": width lies in the x-z plane, thickness along y
        ang = -math.atan2(d[2], d[0])
        return self.box(body, name, mat, mid, (length / 2.0, thickness / 2.0, width / 2.0), euler=(0, ang, 0))

    def mesh(self, body, name, mat, prism):
        """Flat-shaded convex prism: every face gets its own vertices."""
        mesh_name = "v3_mesh_" + name
        if mesh_name not in self.meshes:
            verts, faces = _flat_faces(prism)
            ET.SubElement(self.asset, "mesh", {
                "name": mesh_name,
                "vertex": " ".join(_f(v) for v in verts),
                "face": " ".join(" ".join(str(i) for i in f) for f in faces),
            })
            self.meshes.add(mesh_name)
        return self.geom(body, name, "mesh", mat, mesh=mesh_name)


def _prism(poly_uv: Sequence[tuple[float, float]], origin, u, v, n, half_thickness: float):
    """Convex prism from a counter-clockwise 2-D polygon in the (u, v) plane.

    Returns ``(top, bottom)`` vertex rings; ``top`` is offset along ``+n``.
    """
    origin = np.asarray(origin, float)
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    n = np.asarray(n, float)
    ring = [origin + a * u + b * v for a, b in poly_uv]
    return [p + half_thickness * n for p in ring], [p - half_thickness * n for p in ring]


def _flat_faces(prism):
    """Triangles with per-face vertices so MuJoCo shades each face flat."""
    top, bot = prism
    k = len(top)
    tris = []
    for i in range(1, k - 1):
        tris.append((top[0], top[i], top[i + 1]))
        tris.append((bot[0], bot[i + 1], bot[i]))
    for i in range(k):
        j = (i + 1) % k
        tris.append((bot[i], bot[j], top[j]))
        tris.append((bot[i], top[j], top[i]))
    centre = np.mean(np.vstack(top + bot), axis=0)
    verts, faces = [], []
    for a, b, c in tris:
        a, b, c = (np.asarray(x, float) for x in (a, b, c))
        normal = np.cross(b - a, c - a)
        if float(np.linalg.norm(normal)) < 1e-12:
            continue
        if float(np.dot(normal, (a + b + c) / 3.0 - centre)) < 0:  # outward winding
            b, c = c, b
        base = len(verts)
        verts.extend((a, b, c))
        faces.append((base, base + 1, base + 2))
    return verts, faces


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, count: int) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / (count - 1)),
             cy + r * math.sin(a0 + (a1 - a0) * i / (count - 1))) for i in range(count)]


def _quat_to_mat(q: Sequence[float]) -> np.ndarray:
    w, x, y, z = (float(c) for c in q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


# --------------------------------------------------------------- chassis side
def _add_chassis(b: _Builder, robot: ET.Element, radius: float, yaw_axis_x: float) -> None:
    zf = lambda h: h - radius  # floor-referenced height -> robot body z
    L = G.CHASSIS_LENGTH_M / 2.0
    W = G.CHASSIS_OUTER_WIDTH_M / 2.0
    zb, zt, c = zf(G.CHASSIS_BOTTOM_Z_FLOOR_M), zf(G.CHASSIS_TOP_Z_FLOOR_M), G.CHASSIS_END_CHAMFER_M
    profile = [(-L, zb), (L, zb), (L, zt - c), (L - c, zt), (-L + c, zt), (-L, zt - c)]
    b.mesh(robot, "chassis", "gunmetal", _prism(profile, (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), W))
    # front plate holes (drawing front view: 2+2 outer, 3 centre) and side H-slot
    for i, (y, z) in enumerate([(-.0340, .0405), (-.0340, .0270), (.0340, .0405), (.0340, .0270),
                                 (-.0080, .0335), (0.0, .0335), (.0080, .0335)]):
        r = .0019 if abs(y) > .01 else .0018
        b.cyl(robot, f"chassis_front_hole_{i}", "hole", (L - .0004, y, zf(z)), (L + .0003, y, zf(z)), r)
        b.cyl(robot, f"chassis_rear_hole_{i}", "hole", (-L + .0004, y, zf(z)), (-L - .0003, y, zf(z)), r)
    for side, s in (("left", 1.0), ("right", -1.0)):
        y0, y1 = s * (W - .0004), s * (W + .0003)
        for j, x in enumerate((-.0050, .0050)):
            b.box_span(robot, f"chassis_{side}_hslot_{j}", "hole", (x - .0012, min(y0, y1), zf(.0235)), (x + .0012, max(y0, y1), zf(.0395)))
        b.box_span(robot, f"chassis_{side}_hslot_bar", "hole", (-.0050, min(y0, y1), zf(.0308)), (.0050, max(y0, y1), zf(.0322)))
        for j, x in enumerate((-.030, .030)):
            b.box_span(robot, f"chassis_{side}_slot_{j}", "hole", (x - .0012, min(y0, y1), zf(.027)), (x + .0012, max(y0, y1), zf(.036)))
    # TT motor gearboxes are hidden inside the inverted-U body; visible from below.
    for name, x, y in (("fl", 1, 1), ("fr", 1, -1), ("rl", -1, 1), ("rr", -1, -1)):
        b.box_span(robot, f"motor_{name}", "servo_black", (x * .060 - .011, y * .044, zf(.021)), (x * .060 + .011, y * .018, zf(.040)))

    # ---- chassis-fixed arm-base box with the ultrasonic module in its front face
    bx0, bx1 = G.ARM_BOX_REAR_X_M, G.ARM_BOX_FRONT_X_M
    bw = G.ARM_BOX_WIDTH_M / 2.0
    b.box_span(robot, "arm_box", "gunmetal", (bx0, -bw, zf(G.ARM_BOX_BOTTOM_Z_FLOOR_M)), (bx1, bw, zf(G.ARM_BOX_TOP_Z_FLOOR_M)))
    for side, s in (("left", 1.0), ("right", -1.0)):  # mounting feet
        b.box_span(robot, f"arm_box_foot_{side}_front", "gunmetal_edge", (bx1 - .012, s * bw - .004 if s > 0 else s * bw - .006, zf(.0500)), (bx1 - .002, s * bw + .006 if s > 0 else s * bw + .004, zf(.0515)))
    # recessed front window + module PCB
    sz = G.SONAR_CENTER_Z_FLOOR_M
    board_zc = sz + .0029
    b.box(robot, "sonar_board", "pcb_black", (bx1 + .0006, 0, zf(board_zc)), (.0006, G.SONAR_BOARD_WIDTH_M / 2, G.SONAR_BOARD_HEIGHT_M / 2))
    for i, y in enumerate((-G.SONAR_BOARD_WIDTH_M / 2 + .0035, G.SONAR_BOARD_WIDTH_M / 2 - .0035)):
        for j, dz in enumerate((-.0105, .0105)):
            b.cyl(robot, f"sonar_screw_{i}{j}", "silver", (bx1 + .0010, y, zf(board_zc + dz)), (bx1 + .0020, y, zf(board_zc + dz)), .0016)
    r = G.SONAR_TRANSDUCER_DIAMETER_M / 2.0
    for side, s in (("left", 1.0), ("right", -1.0)):
        y = s * G.SONAR_TRANSDUCER_SPACING_M / 2.0
        b.cyl(robot, f"sonar_ring_{side}", "sonar_can", (bx1 + .0010, y, zf(sz)), (bx1 + .0022, y, zf(sz)), r + .0010)
        b.cyl(robot, f"sonar_can_{side}", "sonar_can", (bx1 + .0010, y, zf(sz)), (G.SONAR_FACE_X_M, y, zf(sz)), r)
        b.cyl(robot, f"sonar_mesh_{side}", "sonar_mesh", (G.SONAR_FACE_X_M - .0004, y, zf(sz)), (G.SONAR_FACE_X_M + .0002, y, zf(sz)), r * .78)
    b.box(robot, "sonar_led_slot", "hole", (bx1 + .0013, 0, zf(G.SONAR_LED_SLOT_Z_FLOOR_M)), (.0003, .0062, .0017))

    # ---- ID6 yaw servo (LD-1501MG, vertical).  Its body is chassis-fixed; it is
    # drawn around the kinematic yaw axis of the chosen profile.
    lx, wy, hz = G.LD1501_BODY_M
    front = yaw_axis_x + G.YAW_SERVO_FRONT_FROM_AXIS_M
    top = G.YAW_SERVO_TOP_Z_FLOOR_M
    b.box_span(robot, "yaw_servo", "servo_black", (front - lx, -wy / 2, zf(top - hz)), (front, wy / 2, zf(top)))
    ear = (G.LD1501_EAR_LENGTH_M - lx) / 2.0
    b.box_span(robot, "yaw_servo_ears", "servo_black", (front - lx - ear, -wy / 2, zf(G.ARM_BOX_TOP_Z_FLOOR_M)), (front + ear, wy / 2, zf(G.ARM_BOX_TOP_Z_FLOOR_M + .0025)))
    b.cyl(robot, "yaw_servo_spline", "silver", (yaw_axis_x, 0, zf(top)), (yaw_axis_x, 0, zf(top + .0015)), .0030)

    # ---- electronics stack (Pi long side along x, ports to the rear)
    pl, pw, pt = G.PI_BOARD_M
    pcx, pz = G.PI_BOARD_CENTER_X_M, G.PI_BOARD_Z_FLOOR_M
    b.box(robot, "pi_board", "pcb_green", (pcx, 0, zf(pz)), (pl / 2, pw / 2, pt / 2))
    for i, (dx, dy) in enumerate(((-.0385, -.0245), (-.0385, .0245), (.0195, -.0245), (.0195, .0245))):
        b.cyl(robot, f"pi_nylon_standoff_{i}", "port_metal", (pcx + dx, dy, zf(G.CHASSIS_TOP_Z_FLOOR_M)), (pcx + dx, dy, zf(G.EXPANSION_BOARD_Z_FLOOR_M)), .0022)
    b.box_span(robot, "pi_heatsink_fan", "servo_black", (pcx - .002, -.020, zf(pz + .0008)), (pcx + .026, .014, zf(pz + .0085)))
    rear = pcx - pl / 2
    b.box_span(robot, "pi_ethernet", "port_metal", (rear - .003, -.0265, zf(pz + .0008)), (rear + .018, -.0105, zf(pz + .0143)))
    for i, (y0, y1) in enumerate(((-.0085, .0060), (.0080, .0225))):
        b.box_span(robot, f"pi_usb_{i}", "port_metal", (rear - .003, y0, zf(pz + .0008)), (rear + .015, y1, zf(pz + .0164)))
        b.box_span(robot, f"pi_usb_{i}_tongue", "port_blue", (rear - .0032, y0 + .002, zf(pz + .0095)), (rear - .0026, y1 - .002, zf(pz + .0105)))
    b.box(robot, "expansion_board", "pcb_black", (pcx + .004, 0, zf(G.EXPANSION_BOARD_Z_FLOOR_M)), (pl / 2 - .006, pw / 2, .0008))
    for i, x in enumerate((-.030, -.018, -.006, .006)):
        b.box_span(robot, f"expansion_header_{i}", "servo_black", (pcx + x - .004, .010, zf(G.EXPANSION_BOARD_Z_FLOOR_M + .0008)), (pcx + x + .004, .026, zf(G.EXPANSION_BOARD_Z_FLOOR_M + .0090)))
    b.box_span(robot, "expansion_switch", "port_blue", (pcx + .018, -.024, zf(G.EXPANSION_BOARD_Z_FLOOR_M + .0008)), (pcx + .026, -.016, zf(G.EXPANSION_BOARD_Z_FLOOR_M + .0060)))

    # ---- copper M4x50 columns and the dark cover
    top_z = G.OFFICIAL_COVER_TOP_Z_FLOOR_M
    ct = .0016
    for i, x in enumerate(G.STANDOFF_X_M):
        for j, s in enumerate((1.0, -1.0)):
            b.cyl(robot, f"standoff_{i}{j}", "copper", (x, s * G.STANDOFF_HALF_SPAN_Y_M, zf(G.CHASSIS_TOP_Z_FLOOR_M)), (x, s * G.STANDOFF_HALF_SPAN_Y_M, zf(top_z - ct)), G.STANDOFF_DIAMETER_M / 2)
    cf, cr, cw = G.COVER_FRONT_X_M, G.COVER_REAR_X_M, G.COVER_TOP_HALF_WIDTH_M
    b.box_span(robot, "cover_top", "gunmetal", (cr, -cw, zf(top_z - ct)), (cf, cw, zf(top_z)))
    for i, y in enumerate((-.022, -.011, 0.0, .011, .022)):
        b.box_span(robot, f"cover_slot_{i}", "hole", (-.062, y - .0016, zf(top_z)), (-.030, y + .0016, zf(top_z + .0003)))
    b.box_span(robot, "cover_front_window", "hole", (-.020, -.011, zf(top_z)), (-.004, .011, zf(top_z + .0003)))
    for side, s in (("left", 1.0), ("right", -1.0)):
        b.cyl(robot, f"cover_screw_{side}_front", "silver", (G.STANDOFF_X_M[0], s * G.STANDOFF_HALF_SPAN_Y_M, zf(top_z)), (G.STANDOFF_X_M[0], s * G.STANDOFF_HALF_SPAN_Y_M, zf(top_z + .0018)), .0035)
        b.cyl(robot, f"cover_screw_{side}_rear", "silver", (G.STANDOFF_X_M[1], s * G.STANDOFF_HALF_SPAN_Y_M, zf(top_z)), (G.STANDOFF_X_M[1], s * G.STANDOFF_HALF_SPAN_Y_M, zf(top_z + .0018)), .0035)
        # flared side panel: top edge at the cover, lower edge further out
        y_top, y_bot = s * cw, s * G.COVER_SIDE_BOTTOM_HALF_WIDTH_M
        z_top, z_bot = zf(top_z - ct), zf(G.COVER_SIDE_BOTTOM_Z_FLOOR_M)
        u = np.array([1.0, 0.0, 0.0])
        v = np.array([0.0, y_bot - y_top, z_bot - z_top])
        vlen = float(np.linalg.norm(v))
        v /= vlen
        n = np.cross(u, v)
        n = n / np.linalg.norm(n)
        if n[1] * s < 0:
            n = -n
        poly = [(cf - .001, 0.0), (G.COVER_SIDE_REAR_X_M, 0.0), (G.COVER_SIDE_REAR_X_M, vlen), (cf - .010, vlen), (cf - .004, vlen * .45)]
        b.mesh(robot, f"cover_side_{side}", "gunmetal", _prism(poly, (0, y_top, z_top), u, v, n, .0006))
        # triangular windows ("V A V" pattern of the official cover)
        wz0 = (top_z - ct - G.COVER_WINDOW_Z_FLOOR_M[1]) / (top_z - ct - G.COVER_SIDE_BOTTOM_Z_FLOOR_M) * vlen
        wz1 = (top_z - ct - G.COVER_WINDOW_Z_FLOOR_M[0]) / (top_z - ct - G.COVER_SIDE_BOTTOM_Z_FLOOR_M) * vlen
        tris = []
        x0 = -.0115
        for k in range(3):
            xa = x0 - k * .0185
            tris.append([(xa, wz0), (xa - .0150, wz0), (xa - .0020, wz1)])
            tris.append([(xa - .0045, wz1), (xa - .0175, wz0 + .0015), (xa - .0175, wz1)])
        for k, tri in enumerate(tris):
            b.mesh(robot, f"cover_window_{side}_{k}", "hole", _prism(tri, np.array([0, y_top, z_top]) + n * .0007, u, v, n, .0002))


# ------------------------------------------------------------------ wheels
def _add_wheel(b: _Builder, body: ET.Element, prefix: str, handedness: int, radius: float) -> None:
    half_w = G.OFFICIAL_WHEEL_WIDTH_M / 2.0
    hub_r = G.WHEEL_HUB_DIAMETER_M / 2.0
    b.cyl(body, f"{prefix}_hub", "hub_grey", (0, -half_w + .0015, 0), (0, half_w - .0015, 0), hub_r)
    n = G.WHEEL_ROLLER_COUNT
    for side, s in (("a", 1.0), ("b", -1.0)):
        y = s * (half_w - .0012)
        b.cyl(body, f"{prefix}_face_{side}", "gunmetal_edge", (0, y, 0), (0, y + s * .0006, 0), hub_r * .78)
        for k in range(G.WHEEL_SPOKE_COUNT):
            phi = 2 * math.pi * k / G.WHEEL_SPOKE_COUNT
            p0 = (.0045 * math.cos(phi), y + s * .0007, .0045 * math.sin(phi))
            p1 = (hub_r * .74 * math.cos(phi), y + s * .0007, hub_r * .74 * math.sin(phi))
            b.bar(body, f"{prefix}_spoke_{side}_{k}", "hub_grey", p0, p1, .0030, .0010, plane="xz")
        b.cyl(body, f"{prefix}_cap_{side}", "silver", (0, y, 0), (0, y + s * .0020, 0), .0040)
        for k in range(n):  # grey "star" side plates carrying the rollers
            phi = 2 * math.pi * (k + .5) / n
            p0 = (hub_r * .9 * math.cos(phi), y, hub_r * .9 * math.sin(phi))
            p1 = ((radius - .0065) * math.cos(phi), y, (radius - .0065) * math.sin(phi))
            b.bar(body, f"{prefix}_tooth_{side}_{k}", "hub_grey", p0, p1, .0070, .0022, plane="xz")
    rr = .0058
    r_axis = radius - rr - .0009
    half = .0125
    for k in range(n):
        phi = 2 * math.pi * k / n
        cx, cz = r_axis * math.cos(phi), r_axis * math.sin(phi)
        tx, tz = -math.sin(phi), math.cos(phi)
        ay = math.cos(math.radians(45.0))
        at = math.sin(math.radians(45.0)) * float(handedness)
        p0 = (cx - half * at * tx, -half * ay, cz - half * at * tz)
        p1 = (cx + half * at * tx, half * ay, cz + half * at * tz)
        b.capsule(body, f"{prefix}_roller_{k}", "rubber_orange", p0, p1, rr)


# -------------------------------------------------------------------- arm
def _add_arm(b: _Builder, bodies: Mapping[str, ET.Element], radius: float) -> None:
    arm_base = bodies["arm_base"]
    zs = NOMINAL_YAW_TO_SHOULDER_M                      # shoulder above arm_base origin
    drop = G.SHOULDER_AXIS_Z_FLOOR_M - G.TURNTABLE_TOP_Z_FLOOR_M   # 28.4 mm
    zb = zs - drop                                       # U-bracket floor
    # horn + turntable between the chassis-fixed yaw servo and the U-bracket
    yaw_top_local = (G.YAW_SERVO_TOP_Z_FLOOR_M - radius) - NOMINAL_YAW_AXIS_FROM_BASE_M
    b.cyl(arm_base, "yaw_horn", "silver", (0, 0, yaw_top_local + .0015), (0, 0, zb - .0020), .0095)
    ow = G.SHOULDER_BRACKET_OUTER_WIDTH_M / 2.0
    hb = G.SHOULDER_BRACKET_BOTTOM_LEN_M / 2.0
    b.box_span(arm_base, "shoulder_bracket_floor", "orange_anodized", (-hb - .002, -ow, zb - .0020), (hb + .002, ow, zb))
    for i, (x, y) in enumerate(((-.006, -.006), (-.006, .006), (.006, -.006), (.006, .006))):
        b.cyl(arm_base, f"shoulder_bracket_screw_{i}", "silver", (x, y, zb), (x, y, zb + .0012), .0020)
    top_r = G.SHOULDER_BRACKET_TOP_Z_FLOOR_M - G.SHOULDER_AXIS_Z_FLOOR_M
    poly = [(-hb, zb), (hb, zb)] + _arc(0.0, zs, top_r, math.radians(-10), math.radians(190), 14)
    for side, s in (("left", 1.0), ("right", -1.0)):
        y = s * (ow - .0010)
        b.mesh(arm_base, f"shoulder_bracket_plate_{side}", "orange_anodized", _prism(poly, (0, y, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), .0010))
        b.box(arm_base, f"shoulder_bracket_slot_{side}", "hole", (0, y + s * .0011, zb + .0070), (.0110, .0002, .0022))
    # ID5 horn with four screws on the +y plate (visible side in the drawing)
    y_h = ow + .0005
    b.cyl(arm_base, "shoulder_horn", "silver", (0, y_h, zs), (0, y_h + .0020, zs), .0070)
    for i, a in enumerate((0, 90, 180, 270)):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        b.cyl(arm_base, f"shoulder_horn_screw_{i}", "silver", (.0105 * ca, y_h, zs + .0105 * sa), (.0105 * ca, y_h + .0015, zs + .0105 * sa), .0017)
    b.cyl(arm_base, "shoulder_bearing", "silver", (0, -y_h, zs), (0, -y_h - .0015, zs), .0050)

    # ---- upper arm (shoulder_link frame: x along the link, y = joint axis)
    sh = bodies["shoulder_link"]
    lx, wy, hz = G.LD1501_BODY_M
    s0, s1 = G.SHOULDER_SERVO_ALONG_M
    b.box_span(sh, "shoulder_servo", "servo_black", (s0, -hz / 2, -wy / 2), (s1, hz / 2, wy / 2))
    ear = (G.LD1501_EAR_LENGTH_M - lx) / 2.0
    b.box_span(sh, "shoulder_servo_ears", "servo_black", (s0 - ear, hz / 2 - .0110, -wy / 2), (s1 + ear, hz / 2 - .0085, wy / 2))
    b.box_span(sh, "shoulder_servo_label", "gunmetal_edge", (s0 + .012, -hz / 2 + .004, wy / 2), (s1 - .004, hz / 2 - .004, wy / 2 + .0003))
    b.cyl(sh, "shoulder_servo_spline", "silver", (0, hz / 2, 0), (0, ow - .0010, 0), .0030)
    fw = G.ARM_FRAME_OUTER_WIDTH_M / 2.0 - G.ARM_PLATE_THICKNESS_M / 2.0
    pw = G.ARM_PLATE_WIDTH_M / 2.0
    cap = G.UPPER_ARM_CAP_ALONG_M
    b.box_span(sh, "upper_arm_cap", "orange_anodized", (cap - .0010, -fw - .001, -pw), (cap + .0010, fw + .001, pw))
    _link_frame(b, sh, "upper_arm", cap, _L2, fw, pw, far_round=True)

    # ---- forearm (elbow_link frame) incl. ID4 and ID3 bodies
    el = bodies["elbow_link"]
    fl, fwid, fh = G.LFD01M_BODY_M
    e0, e1 = G.ELBOW_SERVO_ALONG_M
    b.box_span(el, "elbow_servo", "servo_black", (e0, -fh / 2, -fwid / 2), (e1, fh / 2, fwid / 2))
    lear = (G.LFD01M_EAR_LENGTH_M - fl) / 2.0
    b.box_span(el, "elbow_servo_ears", "servo_black", (e0 - lear, -fh / 2 + .0040, -fwid / 2), (e1 + lear, -fh / 2 + .0063, fwid / 2))
    w0, w1 = G.WRIST_SERVO_ALONG_M
    b.box_span(el, "wrist_servo", "servo_black", (_L3 + w0, -fh / 2, -fwid / 2), (_L3 + w1, fh / 2, fwid / 2))
    b.box_span(el, "wrist_servo_ears", "servo_black", (_L3 + w0 - lear, -fh / 2 + .0040, -fwid / 2), (_L3 + w1 + lear, -fh / 2 + .0063, fwid / 2))
    fw2 = fw + G.ARM_PLATE_THICKNESS_M  # forearm plates sit just outside the upper-arm plates
    for name, x in (("elbow", 0.0), ("wrist", _L3)):
        b.cyl(el, f"{name}_horn", "silver", (x, -fh / 2, 0), (x, -fw2 - .0010, 0), .0060)
    _link_frame(b, el, "forearm", 0.0, _L3, fw2, pw, near_round=True, far_round=True)

    # ---- wrist bracket + gripper (gripper body frame == wrist_link frame)
    gr = bodies["gripper"]
    g0 = G.GRIPPER_BASE_PLATE_ALONG_M
    for side, s in (("left", 1.0), ("right", -1.0)):
        y = s * (fw2 + G.ARM_PLATE_THICKNESS_M)
        poly = _arc(0.0, 0.0, pw, math.radians(90), math.radians(270), 9) + [(g0, -pw), (g0, pw)]
        b.mesh(gr, f"wrist_bracket_{side}", "orange_anodized", _prism(poly, (0, y, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), G.ARM_PLATE_THICKNESS_M / 2))
        b.cyl(gr, f"wrist_bearing_{side}", "hole" if s > 0 else "silver", (0, y + s * .0010, 0), (0, y + s * .0016, 0), .0045)
    u0, u1 = G.GRIPPER_BRACKET_UP_M
    gw = G.ARM_FRAME_OUTER_WIDTH_M / 2.0 + .0010
    b.box_span(gr, "gripper_base_plate", "silver", (g0, -gw, u0), (g0 + .0020, gw, u1))
    top_end = G.GRIPPER_BRACKET_TOP_ALONG_M - .001
    b.box_span(gr, "gripper_top_plate", "silver", (g0, -gw, u1 - .0015), (top_end, gw, u1))
    b.box_span(gr, "gripper_bottom_plate", "silver", (g0, -gw, u0), (G.GRIPPER_BRACKET_TOP_ALONG_M + .006, gw, u0 + .0015))
    # ID1 LFD-01M through the bottom plate, output shaft upward into the linkage
    a0, a1 = G.GRIPPER_SERVO_ALONG_M
    d0, d1 = G.GRIPPER_SERVO_BELOW_M
    b.box_span(gr, "gripper_servo", "servo_black", (a0, -fl / 2, -d1), (a1, fl / 2, -d0))
    b.box_span(gr, "gripper_servo_ears", "servo_black", (a0, -G.LFD01M_EAR_LENGTH_M / 2, u0 - .0023), (a1, G.LFD01M_EAR_LENGTH_M / 2, u0))
    b.cyl(gr, "gripper_gear", "silver", ((a0 + a1) / 2, 0, u0 + .0015), ((a0 + a1) / 2, 0, -.0040), .0045)
    for i, y in enumerate((-.0090, .0090)):
        b.cyl(gr, f"gripper_pivot_{i}", "silver", (.0520, y, u0 + .0015), (.0520, y, u1 - .0015), .0022)

    # ---- camera: lens exactly at the REAL-fitted robot_cam pose (not moved)
    cam_p = np.asarray(CAMERA_LOCAL_POS_M, float)
    R = _quat_to_mat(CAMERA_LOCAL_QUAT_WXYZ)
    fwd = R @ np.array([0.0, 0.0, -1.0])
    lens_len = G.CAMERA_LENS_LENGTH_M
    lens_r = G.CAMERA_LENS_DIAMETER_M / 2.0
    b.cyl(gr, "camera_lens", "servo_black", cam_p - fwd * lens_len, cam_p - fwd * .0020, lens_r)
    b.cyl(gr, "camera_lens_ring", "gunmetal_edge", cam_p - fwd * .0035, cam_p, lens_r * 1.12)
    b.cyl(gr, "camera_lens_glass", "lens", cam_p - fwd * .0004, cam_p + fwd * .0002, lens_r * .72)
    mx, my, _ = G.CAMERA_MODULE_M
    pcb_c = cam_p - fwd * (lens_len + .0010)
    b.box(gr, "camera_pcb", "pcb_black", pcb_c, (mx / 2, my / 2, .0008), quat=CAMERA_LOCAL_QUAT_WXYZ)
    plate_c = cam_p - fwd * (lens_len + .0055)
    b.box(gr, "camera_mount_plate", "servo_black", plate_c, (mx / 2 + .002, my / 2 + .002, .0008), quat=CAMERA_LOCAL_QUAT_WXYZ)
    right, up = R @ np.array([1.0, 0, 0]), R @ np.array([0, 1.0, 0])
    for i, (a, c) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        p = a * (mx / 2 - .0022) * right + c * (my / 2 - .0022) * up
        b.cyl(gr, f"camera_standoff_{i}", "copper", plate_c + p, pcb_c + p, .0012)
    # bracket from the gripper top plate up to the camera mount plate
    low = plate_c - up * (my / 2 + .002)
    b.box_span(gr, "camera_bracket", "silver", (min(low[0], top_end) - .006, -.010, u1 - .0015), (max(low[0], top_end) + .0005, .010, max(u1, low[2]) + .0005))

    # ---- fingers: visible bars follow the v2 slide jaws; pads sit on the
    # physical contact proxies (x = 0.100 m in the jaw frame).
    for jaw, s in (("left_jaw", 1.0), ("right_jaw", -1.0)):
        body = bodies[jaw]
        y_open = s * 0.035  # v2 jaw origin in the gripper frame
        piv = np.array([.0520, s * .0090 - y_open, -.0019])
        mid = np.array([.0700, s * (G.FINGER_OPEN_SPAN_M / 2.0) - y_open, -.0019])
        tip = np.array([.0930, 0.0, -.0019])
        b.bar(body, f"{jaw}_finger_a", "silver", piv, mid, .0050, G.FINGER_PLATE_THICKNESS_M)
        b.bar(body, f"{jaw}_finger_b", "silver", mid, tip, .0050, G.FINGER_PLATE_THICKNESS_M)
        b.cyl(body, f"{jaw}_finger_joint", "silver", mid + (0, 0, -.0020), mid + (0, 0, .0020), .0027)
        pl = G.FINGER_PAD_LENGTH_M
        b.box(body, f"{jaw}_pad", "rubber_orange", (.1000, 0, -.0019), (pl / 2, .0030, .0048))
        b.cyl(body, f"{jaw}_pad_tip", "rubber_orange", (.1000 + pl / 2, 0, -.0067), (.1000 + pl / 2, 0, .0029), .0030)


def _link_frame(b, body, name, x0, x1, half_span, pw, near_round=False, far_round=False):
    """Open orange side frames (two rails, N-braces, round joint ends)."""
    t = G.ARM_PLATE_THICKNESS_M
    rail = .0032
    for side, s in (("left", 1.0), ("right", -1.0)):
        y = s * half_span
        xa = x0 + (pw if near_round else 0.0)
        xb = x1 - (pw if far_round else 0.0)
        b.box_span(body, f"{name}_rail_top_{side}", "orange_anodized", (xa, y - t / 2, pw - rail), (xb, y + t / 2, pw))
        b.box_span(body, f"{name}_rail_bot_{side}", "orange_anodized", (xa, y - t / 2, -pw), (xb, y + t / 2, -pw + rail))
        length = xb - xa
        n = max(2, int(round(length / .022)))
        for k in range(n):
            p0 = (xa + length * k / n, y, -pw + rail / 2)
            p1 = (xa + length * (k + 1) / n, y, pw - rail / 2)
            if k % 2:
                p0, p1 = (p0[0], y, pw - rail / 2), (p1[0], y, -pw + rail / 2)
            b.bar(body, f"{name}_brace_{side}_{k}", "orange_anodized", p0, p1, .0030, t, plane="xz")
        for k in range(n + 1):
            if (k == 0 and near_round) or (k == n and far_round):
                continue
            x = xa + length * k / n
            b.box_span(body, f"{name}_post_{side}_{k}", "orange_anodized", (x - .0016, y - t / 2, -pw), (x + .0016, y + t / 2, pw))
        for end, x, flag in (("near", x0, near_round), ("far", x1, far_round)):
            if flag:
                b.cyl(body, f"{name}_{end}_disc_{side}", "orange_anodized", (x, y - t / 2, 0), (x, y + t / 2, 0), pw)
                b.cyl(body, f"{name}_{end}_hole_{side}", "hole", (x, y + s * t / 2, 0), (x, y + s * (t / 2 + .0003), 0), .0042)


# ------------------------------------------------------------------ build
def _is_visual_only(geom: ET.Element) -> bool:
    return geom.get("contype", "1") == "0" and geom.get("conaffinity", "1") == "0"


def _add_materials(asset: ET.Element) -> None:
    for key, (spec, shin) in _MATERIALS.items():
        ET.SubElement(asset, "material", {
            "name": "v3_" + key, "rgba": _f(G.RGBA[key]), "specular": spec, "shininess": shin,
        })


def _apply_drawing_layout(robot: ET.Element, bodies: Mapping[str, ET.Element], radius: float) -> None:
    """Structural proposal: arm mount + collision proxies from the drawing."""
    bodies["arm_base"].set("pos", _f((G.YAW_AXIS_X_M, 0.0, NOMINAL_YAW_AXIS_FROM_BASE_M)))
    zf = lambda h: h - radius
    geoms = {g.get("name"): g for g in robot.findall("geom")}
    L = G.CHASSIS_LENGTH_M / 2.0
    W = G.CHASSIS_OUTER_WIDTH_M / 2.0
    zb, zt = zf(G.CHASSIS_BOTTOM_Z_FLOOR_M), zf(G.CHASSIS_TOP_Z_FLOOR_M)
    geoms["base_lower_collision"].set("pos", _f((0, 0, (zb + zt - .004) / 2)))
    geoms["base_lower_collision"].set("size", _f((L - .002, W - .003, (zt - .004 - zb) / 2)))
    geoms["base_top"].set("pos", _f((0, 0, zt - .002)))
    geoms["base_top"].set("size", _f((L - G.CHASSIS_END_CHAMFER_M, W, .002)))
    geoms["front_plate"].set("pos", _f((L - .0015, 0, (zb + zt) / 2)))
    geoms["front_plate"].set("size", _f((.0015, W - .003, (zt - zb) / 2 - .002)))
    cz0, cz1 = zf(G.CHASSIS_TOP_Z_FLOOR_M), zf(G.OFFICIAL_COVER_TOP_Z_FLOOR_M)
    geoms["rear_cage_collision"].set("pos", _f(((G.COVER_FRONT_X_M + G.COVER_REAR_X_M) / 2, 0, (cz0 + cz1) / 2)))
    geoms["rear_cage_collision"].set("size", _f(((G.COVER_FRONT_X_M - G.COVER_REAR_X_M) / 2, G.COVER_SIDE_BOTTOM_HALF_WIDTH_M, (cz1 - cz0) / 2)))
    box = ET.Element("geom", {
        "name": "arm_box_collision", "type": "box",
        "pos": _f(((G.ARM_BOX_REAR_X_M + G.ARM_BOX_FRONT_X_M) / 2, 0, (zf(G.ARM_BOX_BOTTOM_Z_FLOOR_M) + zf(G.ARM_BOX_TOP_Z_FLOOR_M)) / 2)),
        "size": _f(((G.ARM_BOX_FRONT_X_M - G.ARM_BOX_REAR_X_M) / 2, G.ARM_BOX_WIDTH_M / 2, (G.ARM_BOX_TOP_Z_FLOOR_M - G.ARM_BOX_BOTTOM_Z_FLOOR_M) / 2)),
        "rgba": "0 0 0 0", "contype": "2", "conaffinity": "1",
    })
    robot.insert(list(robot).index(geoms["rear_cage_collision"]) + 1, box)


def build_v3_xml(hardware: Mapping[str, float] | None = None, *, profile: str) -> str:
    """Return the v3 single-robot MJCF.  ``profile`` must be named explicitly."""
    if profile not in PROFILES:
        raise ValueError(f"unknown MasterPi v3 profile {profile!r}; expected one of {PROFILES}")
    hardware = dict(hardware or {})
    root = ET.fromstring(build_v2_xml(hardware))
    root.set("model", f"ugrp_masterpi_visual_v3_{profile}")
    asset = root.find("asset")
    if asset is None:
        asset = ET.SubElement(root, "asset")
    world = root.find("worldbody")
    robot = next((c for c in list(world) if c.tag == "body" and c.get("name") == "robot"), None)
    if robot is None:
        raise RuntimeError("v2 XML has no robot body")
    radius = float(hardware.get("wheel_radius_m", WHEEL_RADIUS_M))

    # 1) drop v2 visual-only geoms; hide colliding geoms v2 also used as panels
    for body in robot.iter("body"):
        for geom in list(body.findall("geom")):
            if _is_visual_only(geom):
                body.remove(geom)
            else:
                geom.attrib.pop("material", None)
                geom.set("rgba", "0 0 0 0")
    bodies = {b.get("name"): b for b in robot.iter("body")}
    bodies["robot"] = robot

    if profile == PROFILE_DRAWING_LAYOUT:
        _apply_drawing_layout(robot, bodies, radius)

    _add_materials(asset)
    builder = _Builder(asset)
    yaw_x = float(bodies["arm_base"].get("pos").split()[0])
    _add_chassis(builder, robot, radius, yaw_x)
    for name, hand in (("fl", 1), ("fr", -1), ("rl", -1), ("rr", 1)):
        _add_wheel(builder, bodies[f"wheel_{name}_body"], f"wheel_{name}", hand, radius)
    _add_arm(builder, bodies, radius)
    site = ET.SubElement(robot, "site", {
        "name": SONAR_SITE, "pos": _f(SONAR_MOUNT_V3["pos_body_m"]),
        "zaxis": "1 0 0", "size": ".002", "rgba": "0 0 0 0",
    })
    del site
    return ET.tostring(root, encoding="unicode")


def v3_visual_geom_names(model) -> list[str]:
    """Names of v3 visual geoms in a compiled model (for audits/tests)."""
    import mujoco

    out = []
    for i in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or ""
        if name.startswith(V3_PREFIX):
            out.append(name)
    return out


__all__ = [
    "PROFILES",
    "PROFILE_APPEARANCE_ONLY",
    "PROFILE_DRAWING_LAYOUT",
    "SONAR_MOUNT_V3",
    "SONAR_SITE",
    "VISUAL_MODEL_VERSION",
    "build_v3_xml",
    "v3_visual_geom_names",
]
