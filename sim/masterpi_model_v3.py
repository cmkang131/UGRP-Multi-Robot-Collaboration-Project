"""MasterPi physical model v3 (Hiwonder dimension drawing + SDK arm).

``build_v3_xml`` is the v3 robot model for new scenes and new execution
bundles.  It starts from :func:`sim.masterpi_dynamics_v2.build_v2_xml` (so the
actuators, joint ranges, damping, masses, inertias, the REAL-fitted
``robot_cam`` pose/intrinsics and every calibration hook stay identical) and
replaces the *geometry* from one parameter set,
:data:`sim.masterpi_geometry_v3.PHYSICAL_V3`:

* arm yaw (ID6) axis 48.2 mm forward of the axle midpoint, yaw joint 93.0 mm and
  shoulder (ID5) axis 127.7 mm above the floor (official drawing);
* upper arm 65.0 mm and forearm 62.0 mm (Hiwonder SDK, render-corroborated);
* finger contact proxies and ``grip_site`` at the physical pad centre
  86.85 mm from the wrist axis (closed tip 94.0 mm, pad 14.3 mm; drawing);
* wheel track 129.9 mm, wheelbase 118.8 mm, width 30 mm (drawing) unless the
  caller passes calibrated/explicit ``track_m``/``wheelbase_m``;
* chassis (185 mm), cover, arm-base box, yaw-servo, pedestal and ultrasonic
  collision proxies from the drawing, plus the ultrasonic site;
* all v2 visual-only geoms replaced by source-traced ``v3_`` visuals.

The controller layer (``harness.visual_arm``) keeps the SDK IK constants
(l1 9.30, l2 6.50, l3 6.20, l4 10.00 cm) and adds only the physical arm mount;
the remaining mismatch is listed in
:data:`sim.masterpi_geometry_v3.CONTROLLER_VS_PHYSICAL_V3`.

:func:`build_v2_appearance_xml` is a diagnostic: v2 physics bit-identical with
the v3 visuals.  v2 sources are not modified, so registered bundles keep
resolving to the same bytes.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Iterable, Mapping, Sequence

import numpy as np

from sim import masterpi_geometry_v3 as G
from sim.masterpi_camera_profile import CAMERA_LOCAL_POS_M, CAMERA_LOCAL_QUAT_WXYZ
from sim.masterpi_dynamics_v2 import WHEEL_RADIUS_M, build_v2_xml
from sim.masterpi_geometry_v3 import PHYSICAL_V3, MasterPiPhysicalGeometry

from sim.masterpi_robot_models import ROBOT_MODEL_V2, ROBOT_MODEL_V3
MODEL_VERSION = "masterpi-model-v3-20260928"
V3_PREFIX = "v3_"
SONAR_SITE = "v3_ultrasonic_site"
# Camera hardware visuals never appear in robot_cam (same rule as v2's runtime
# group-5 loop); they are written with group 5 directly.
CAMERA_HARDWARE_GROUP = 5


def sonar_mount(geometry: MasterPiPhysicalGeometry = PHYSICAL_V3) -> dict:
    """Chassis-fixed ultrasonic mount in the ``robot`` body frame."""
    return {
        "version": geometry.version,
        "pos_body_m": (geometry.sonar_face_x_m, G.SONAR_CENTER_Y_M,
                       geometry.sonar_center_z_floor_m - geometry.wheel_radius_m),
        "pos_floor_m": (geometry.sonar_face_x_m, G.SONAR_CENTER_Y_M, geometry.sonar_center_z_floor_m),
        "axis_body": (math.cos(math.radians(geometry.sonar_pitch_deg)), 0.0,
                      -math.sin(math.radians(geometry.sonar_pitch_deg))),
        "pitch_deg": geometry.sonar_pitch_deg,
        "transducer_spacing_m": G.SONAR_TRANSDUCER_SPACING_M,
        "transducer_diameter_m": G.SONAR_TRANSDUCER_DIAMETER_M,
        "beam_angle_deg": G.OFFICIAL_SONAR_BEAM_ANGLE_DEG,
        "source": "official_drawing: Hiwonder MasterPi dimension drawing + glowing ultrasonic module drawing",
    }


SONAR_MOUNT_V3 = sonar_mount(PHYSICAL_V3)

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
def _add_wheel(b: _Builder, body: ET.Element, prefix: str, handedness: int, radius: float, width: float) -> None:
    half_w = width / 2.0
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
def _pos(el: ET.Element) -> np.ndarray:
    return np.array([float(v) for v in el.get("pos", "0 0 0").split()], float)


def _add_arm(b: _Builder, bodies: Mapping[str, ET.Element], radius: float, grip_x: float) -> None:
    """Arm visuals placed on the kinematic frames actually present in the XML."""
    arm_base = bodies["arm_base"]
    zs = float(_pos(bodies["shoulder_link"])[2])        # shoulder above arm_base origin
    _L2 = float(_pos(bodies["elbow_link"])[0])
    _L3 = float(_pos(bodies["wrist_link"])[0])
    drop = G.SHOULDER_AXIS_Z_FLOOR_M - G.TURNTABLE_TOP_Z_FLOOR_M   # 28.4 mm
    zb = zs - drop                                       # U-bracket floor
    # horn + turntable between the chassis-fixed yaw servo and the U-bracket
    yaw_top_local = (G.YAW_SERVO_TOP_Z_FLOOR_M - radius) - float(_pos(arm_base)[2])
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

    # ---- camera: lens exactly at the REAL-fitted robot_cam pose (not moved).
    # Group 5: the robot never photographs its own camera hardware.
    def _cam(geom: ET.Element) -> ET.Element:
        geom.set("group", str(CAMERA_HARDWARE_GROUP))
        return geom

    cam_p = np.asarray(CAMERA_LOCAL_POS_M, float)
    R = _quat_to_mat(CAMERA_LOCAL_QUAT_WXYZ)
    fwd = R @ np.array([0.0, 0.0, -1.0])
    lens_len = G.CAMERA_LENS_LENGTH_M
    lens_r = G.CAMERA_LENS_DIAMETER_M / 2.0
    _cam(b.cyl(gr, "camera_lens", "servo_black", cam_p - fwd * lens_len, cam_p - fwd * .0020, lens_r))
    _cam(b.cyl(gr, "camera_lens_ring", "gunmetal_edge", cam_p - fwd * .0035, cam_p, lens_r * 1.12))
    _cam(b.cyl(gr, "camera_lens_glass", "lens", cam_p - fwd * .0004, cam_p + fwd * .0002, lens_r * .72))
    mx, my, _ = G.CAMERA_MODULE_M
    pcb_c = cam_p - fwd * (lens_len + .0010)
    _cam(b.box(gr, "camera_pcb", "pcb_black", pcb_c, (mx / 2, my / 2, .0008), quat=CAMERA_LOCAL_QUAT_WXYZ))
    plate_c = cam_p - fwd * (lens_len + .0055)
    _cam(b.box(gr, "camera_mount_plate", "servo_black", plate_c, (mx / 2 + .002, my / 2 + .002, .0008), quat=CAMERA_LOCAL_QUAT_WXYZ))
    right, up = R @ np.array([1.0, 0, 0]), R @ np.array([0, 1.0, 0])
    for i, (a, c) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        p = a * (mx / 2 - .0022) * right + c * (my / 2 - .0022) * up
        _cam(b.cyl(gr, f"camera_standoff_{i}", "copper", plate_c + p, pcb_c + p, .0012))
    # bracket from the gripper top plate up to the camera mount plate
    low = plate_c - up * (my / 2 + .002)
    _cam(b.box_span(gr, "camera_bracket", "silver", (min(low[0], top_end) - .006, -.010, u1 - .0015), (max(low[0], top_end) + .0005, .010, max(u1, low[2]) + .0005)))

    # ---- fingers: visible bars follow the slide jaws; pads sit on the
    # contact proxies (x = grip_x in the jaw frame).
    for jaw, s in (("left_jaw", 1.0), ("right_jaw", -1.0)):
        body = bodies[jaw]
        y_open = s * 0.035  # v2 jaw origin in the gripper frame
        piv = np.array([.0520, s * .0090 - y_open, -.0019])
        mid = np.array([.0700, s * (G.FINGER_OPEN_SPAN_M / 2.0) - y_open, -.0019])
        pl = G.FINGER_PAD_LENGTH_M
        tip = np.array([grip_x + pl / 2 - .0010, 0.0, -.0019])
        b.bar(body, f"{jaw}_finger_a", "silver", piv, mid, .0050, G.FINGER_PLATE_THICKNESS_M)
        b.bar(body, f"{jaw}_finger_b", "silver", mid, tip, .0050, G.FINGER_PLATE_THICKNESS_M)
        b.cyl(body, f"{jaw}_finger_joint", "silver", mid + (0, 0, -.0020), mid + (0, 0, .0020), .0027)
        b.box(body, f"{jaw}_pad", "rubber_orange", (grip_x, 0, -.0019), (pl / 2, .0030, .0048))
        b.cyl(body, f"{jaw}_pad_tip", "rubber_orange", (grip_x + pl / 2, 0, -.0067), (grip_x + pl / 2, 0, .0029), .0030)


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


def _collider(name: str, gtype: str, pos, size, **extra: str) -> ET.Element:
    attrs = {"name": name, "type": gtype, "pos": _f(pos), "size": _f(size),
             "rgba": "0 0 0 0", "contype": "2", "conaffinity": "1"}
    attrs.update(extra)
    return ET.Element("geom", attrs)


def _set_box(geom: ET.Element, lo, hi) -> None:
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    geom.set("pos", _f((lo + hi) / 2.0))
    geom.set("size", _f(np.abs(hi - lo) / 2.0))


def _apply_physical_geometry(robot: ET.Element, bodies: Mapping[str, ET.Element],
                             g: MasterPiPhysicalGeometry, radius: float) -> float:
    """Move frames/colliders to the physical set; return the grip-site x."""
    zf = lambda h: h - radius  # floor height -> robot body z
    geoms = {el.get("name"): el for el in robot.iter("geom")}

    # ---- wheels: collider width (positions come from build_v2_xml hardware)
    for w in ("fl", "fr", "rl", "rr"):
        size = [float(v) for v in geoms[f"wheel_{w}"].get("size").split()]
        size[1] = g.wheel_width_m / 2.0
        geoms[f"wheel_{w}"].set("size", _f(size))

    # ---- chassis / cover / arm-base box proxies (robot body)
    L = G.CHASSIS_LENGTH_M / 2.0
    W = G.CHASSIS_OUTER_WIDTH_M / 2.0
    zb, zt = zf(G.CHASSIS_BOTTOM_Z_FLOOR_M), zf(G.CHASSIS_TOP_Z_FLOOR_M)
    _set_box(geoms["base_lower_collision"], (-L + .002, -W + .003, zb), (L - .002, W - .003, zt - .004))
    _set_box(geoms["base_top"], (-L + G.CHASSIS_END_CHAMFER_M, -W, zt - .004), (L - G.CHASSIS_END_CHAMFER_M, W, zt))
    _set_box(geoms["front_plate"], (L - .003, -W + .003, zb + .002), (L, W - .003, zt - .002))
    cz0, cz1 = zt, zf(G.OFFICIAL_COVER_TOP_Z_FLOOR_M)
    _set_box(geoms["rear_cage_collision"], (G.COVER_REAR_X_M, -G.COVER_SIDE_BOTTOM_HALF_WIDTH_M, cz0),
             (G.COVER_FRONT_X_M, G.COVER_SIDE_BOTTOM_HALF_WIDTH_M, cz1))
    bw = G.ARM_BOX_WIDTH_M / 2.0
    lx, wy, hz = G.LD1501_BODY_M
    servo_front = g.yaw_axis_x_m + G.YAW_SERVO_FRONT_FROM_AXIS_M
    r = G.SONAR_TRANSDUCER_DIAMETER_M / 2.0
    sy = G.SONAR_TRANSDUCER_SPACING_M / 2.0 + r
    sz = zf(g.sonar_center_z_floor_m)
    extra = [
        _collider("arm_box_collision", "box",
                  ((G.ARM_BOX_REAR_X_M + G.ARM_BOX_FRONT_X_M) / 2, 0, (zt + zf(G.ARM_BOX_TOP_Z_FLOOR_M)) / 2),
                  ((G.ARM_BOX_FRONT_X_M - G.ARM_BOX_REAR_X_M) / 2, bw, (G.ARM_BOX_TOP_Z_FLOOR_M - G.CHASSIS_TOP_Z_FLOOR_M) / 2)),
        _collider("yaw_servo_collision", "box",
                  (servo_front - lx / 2, 0, (zf(G.ARM_BOX_TOP_Z_FLOOR_M) + zf(g.yaw_joint_z_floor_m)) / 2),
                  (lx / 2, wy / 2, (g.yaw_joint_z_floor_m - G.ARM_BOX_TOP_Z_FLOOR_M) / 2)),
        _collider("ultrasonic_collision", "box",
                  ((G.ARM_BOX_FRONT_X_M + g.sonar_face_x_m) / 2, 0, sz),
                  ((g.sonar_face_x_m - G.ARM_BOX_FRONT_X_M) / 2, sy, r)),
    ]
    at = list(robot).index(geoms["rear_cage_collision"]) + 1
    for k, el in enumerate(extra):
        robot.insert(at + k, el)

    # ---- arm mount: yaw joint on the chassis-fixed ID6 axis
    arm_base = bodies["arm_base"]
    arm_base.set("pos", _f((g.yaw_axis_x_m, 0.0, zf(g.yaw_joint_z_floor_m))))
    zs = g.shoulder_axis_z_floor_m - g.yaw_joint_z_floor_m
    hb = G.SHOULDER_BRACKET_BOTTOM_LEN_M / 2.0 + .002
    ped = geoms["arm_pedestal_collision"]
    ped.set("type", "box")
    _set_box(ped, (-hb, -G.SHOULDER_BRACKET_OUTER_WIDTH_M / 2, 0.0), (hb, G.SHOULDER_BRACKET_OUTER_WIDTH_M / 2, zs - .004))
    bodies["shoulder_link"].set("pos", _f((0.0, 0.0, zs)))

    # ---- links (inertial masses/inertias unchanged; COM stays mid-link)
    sh, el, wr = bodies["shoulder_link"], bodies["elbow_link"], bodies["wrist_link"]
    el.set("pos", _f((g.upper_arm_m, 0.0, 0.0)))
    sh.find("inertial").set("pos", _f((g.upper_arm_m / 2.0, 0.0, 0.0)))
    geoms["upper_arm_collision"].set("fromto", _f((0, 0, 0, g.upper_arm_m, 0, 0)))
    wr.set("pos", _f((g.forearm_m, 0.0, 0.0)))
    el.find("inertial").set("pos", _f((g.forearm_m / 2.0, 0.0, 0.0)))
    geoms["forearm_collision"].set("fromto", _f((0, 0, 0, g.forearm_m, 0, 0)))

    # ---- gripper: contact proxies and grip_site on the physical pad centre
    grip_x = g.pad_center_from_wrist_m
    v2_x = float(geoms["left_finger"].get("pos").split()[0])
    for side in ("left", "right"):
        finger = geoms[f"{side}_finger"]
        size = [float(v) for v in finger.get("size").split()]
        size[0] = g.finger_pad_length_m / 2.0
        finger.set("size", _f(size))
        finger.set("pos", _f((grip_x, 0.0, 0.0)))
        inertial = bodies[f"{side}_jaw"].find("inertial")
        ipos = [float(v) for v in inertial.get("pos").split()]
        ipos[0] += grip_x - v2_x
        inertial.set("pos", _f(ipos))
    gripper = bodies["gripper"]
    site = next(el_ for el_ in gripper.findall("site") if el_.get("name") == "grip_site")
    site.set("pos", _f((grip_x, 0.0, 0.0)))
    return grip_x


def _strip_and_hide(robot: ET.Element) -> None:
    """Drop v2 visual-only geoms; make colliders (some doubled as panels) invisible."""
    for body in robot.iter("body"):
        for geom in list(body.findall("geom")):
            if _is_visual_only(geom):
                body.remove(geom)
            else:
                geom.attrib.pop("material", None)
                geom.set("rgba", "0 0 0 0")


def _decorate(root: ET.Element, robot: ET.Element, bodies: Mapping[str, ET.Element],
              radius: float, wheel_width: float, grip_x: float) -> None:
    asset = root.find("asset")
    if asset is None:
        asset = ET.SubElement(root, "asset")
    _add_materials(asset)
    builder = _Builder(asset)
    yaw_x = float(_pos(bodies["arm_base"])[0])
    _add_chassis(builder, robot, radius, yaw_x)
    for name, hand in (("fl", 1), ("fr", -1), ("rl", -1), ("rr", 1)):
        _add_wheel(builder, bodies[f"wheel_{name}_body"], f"wheel_{name}", hand, radius, wheel_width)
    _add_arm(builder, bodies, radius, grip_x)


def _robot(root: ET.Element) -> tuple[ET.Element, dict[str, ET.Element]]:
    world = root.find("worldbody")
    robot = next((c for c in list(world) if c.tag == "body" and c.get("name") == "robot"), None)
    if robot is None:
        raise RuntimeError("v2 XML has no robot body")
    bodies = {b.get("name"): b for b in robot.iter("body")}
    bodies["robot"] = robot
    return robot, bodies


def v3_hardware(hardware: Mapping[str, float] | None = None,
                geometry: MasterPiPhysicalGeometry = PHYSICAL_V3) -> dict[str, float]:
    """Hardware mapping for v3: drawing wheel geometry unless the caller overrides it."""
    out = {"wheel_radius_m": geometry.wheel_radius_m, "wheelbase_m": geometry.wheelbase_m,
           "track_m": geometry.track_m}
    out.update(dict(hardware or {}))
    return out


def build_v3_xml(hardware: Mapping[str, float] | None = None, *,
                 geometry: MasterPiPhysicalGeometry = PHYSICAL_V3) -> str:
    """Return the physical v3 single-robot MJCF.

    ``hardware`` keys win over the geometry set for ``wheel_radius_m``,
    ``wheelbase_m`` and ``track_m`` (calibrated or explicit values); every
    other hardware key is passed to ``build_v2_xml`` unchanged.
    """
    if not isinstance(geometry, MasterPiPhysicalGeometry):
        raise TypeError("geometry must be a MasterPiPhysicalGeometry")
    hw = v3_hardware(hardware, geometry)
    root = ET.fromstring(build_v2_xml(hw))
    root.set("model", "ugrp_masterpi_model_v3")
    robot, bodies = _robot(root)
    radius = float(hw["wheel_radius_m"])
    _strip_and_hide(robot)
    grip_x = _apply_physical_geometry(robot, bodies, geometry, radius)
    _decorate(root, robot, bodies, radius, geometry.wheel_width_m, grip_x)
    mount = sonar_mount(geometry)
    ET.SubElement(robot, "site", {
        "name": SONAR_SITE, "pos": _f(mount["pos_body_m"]),
        "zaxis": _f(mount["axis_body"]), "size": ".002", "rgba": "0 0 0 0",
    })
    return ET.tostring(root, encoding="unicode")


def build_v2_appearance_xml(hardware: Mapping[str, float] | None = None) -> str:
    """Diagnostic only: v2 physics bit-identical, v3 visuals on the v2 frames."""
    hw = dict(hardware or {})
    root = ET.fromstring(build_v2_xml(hw))
    root.set("model", "ugrp_masterpi_v2_with_v3_appearance")
    robot, bodies = _robot(root)
    radius = float(hw.get("wheel_radius_m", WHEEL_RADIUS_M))
    _strip_and_hide(robot)
    grip = next(el for el in bodies["gripper"].findall("site") if el.get("name") == "grip_site")
    wheel_width = 2.0 * float(next(g for g in bodies["wheel_fl_body"].findall("geom")
                                   if g.get("name") == "wheel_fl").get("size").split()[1])
    _decorate(root, robot, bodies, radius, wheel_width, float(_pos(grip)[0]))
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
    "CAMERA_HARDWARE_GROUP",
    "MODEL_VERSION",
    "ROBOT_MODEL_V2",
    "ROBOT_MODEL_V3",
    "SONAR_MOUNT_V3",
    "SONAR_SITE",
    "build_v2_appearance_xml",
    "build_v3_xml",
    "sonar_mount",
    "v3_hardware",
    "v3_visual_geom_names",
]
