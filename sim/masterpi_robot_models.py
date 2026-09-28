"""Robot models a zone scene version can carry (MasterPi v2 / v3).

Manager decision 2026-09-28 (PR #249): the robot model is part of the scene
version.  Every scene version registered before PR #249 is pinned to
``masterpi_v2`` and keeps its bytes, hashes and the 0.155 m station convention.
New scene versions name ``masterpi_v3`` explicitly.  Nothing here changes an
existing module or default; v3 enters only through the per-instance
``xml_transform`` hook of :class:`sim.multi_masterpi_production.MultiMasterPiProductionV2`
and through :func:`station_grasp_convention`.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Mapping

from sim.masterpi_geometry_v3 import PHYSICAL_V3
from sim.masterpi_model_v3 import ROBOT_MODEL_V2, ROBOT_MODEL_V3, build_v3_xml, v3_hardware

# Hardware keys that v3 takes from the drawing unless the calibration manifest
# (sim/masterpi_dynamics_calibration.json) or the caller supplies them.
V3_DRAWING_HARDWARE_KEYS = ("wheelbase_m", "track_m")


@dataclass(frozen=True)
class RobotModel:
    id: str
    geometry_version: str
    # ID6 arm yaw axis forward of the chassis origin (axle midpoint), metres.
    arm_mount_x_m: float


ROBOT_MODELS: Mapping[str, RobotModel] = {
    ROBOT_MODEL_V2: RobotModel(ROBOT_MODEL_V2, "masterpi-v2", 0.0),
    ROBOT_MODEL_V3: RobotModel(ROBOT_MODEL_V3, PHYSICAL_V3.version, PHYSICAL_V3.yaw_axis_x_m),
}
# Scene versions registered before PR #249 carry this model implicitly.
LEGACY_SCENE_ROBOT_MODEL = ROBOT_MODEL_V2


def robot_model(model_id: str) -> RobotModel:
    try:
        return ROBOT_MODELS[model_id]
    except KeyError:
        raise ValueError(f"unknown robot_model {model_id!r}; expected one of {tuple(ROBOT_MODELS)}") from None


def station_grasp_convention(model_id: str) -> dict:
    """Station/grasp convention derived from the robot model.

    The calibrated reach (``sim.zone_cargo.GRASP_RADIUS_M`` = 0.155 m, measured
    from the arm yaw axis on the v2 model where that axis is the chassis
    origin) stays the arm radius; the chassis-frame station distance adds the
    model's arm mount so the arm radius stays inside the calibrated envelope.
    """
    from harness.visual_arm import CALIBRATED_GRASP_RADIUS_CM
    from sim.zone_cargo import GRASP_RADIUS_M, GRASP_Z_M

    model = robot_model(model_id)
    arm_radius = float(GRASP_RADIUS_M)
    lo, hi = (v / 100.0 for v in CALIBRATED_GRASP_RADIUS_CM)
    if not lo <= arm_radius <= hi:
        raise ValueError("calibrated reach is outside the calibrated grasp envelope")
    return {
        "robot_model": model.id,
        "geometry_version": model.geometry_version,
        "arm_radius_m": arm_radius,
        "arm_mount_x_m": model.arm_mount_x_m,
        "station_radius_m": round(model.arm_mount_x_m + arm_radius, 6),
        "grasp_z_m": float(GRASP_Z_M),
    }


def _v3_robot_body(hardware: Mapping[str, float] | None) -> tuple[ET.Element, list[ET.Element]]:
    root = ET.fromstring(build_v3_xml(hardware))
    world = root.find("worldbody")
    robot = next(c for c in list(world) if c.tag == "body" and c.get("name") == "robot")
    assets = [el for el in root.find("asset") if str(el.get("name", "")).startswith("v3_")]
    return robot, assets


def v3_robot_xml_transform(hardware: Mapping[str, float] | None = None,
                           *, calibrated_keys=()) -> Callable[[str], str]:
    """``xml_transform`` that swaps every ``<rid>__robot`` body for the v3 robot.

    ``hardware`` is the v2 template's ``physical_params``; wheelbase/track that
    are not in ``calibrated_keys`` are replaced by the drawing values.  Robot
    pose, the peer-contact affinity rule and children the multi-robot builder
    added (navigation camera, peer band) are kept.  Actuators, equality welds
    and all body/joint names are unchanged, so controllers bind as before.
    """
    hw = dict(hardware or {})
    for key in V3_DRAWING_HARDWARE_KEYS:
        if key not in set(calibrated_keys):
            hw.pop(key, None)
    hw = v3_hardware(hw)

    def transform(xml: str) -> str:
        from sim.multi_masterpi_production import _prefix_named_tree

        root = ET.fromstring(xml)
        world = root.find("worldbody")
        v3_robot, v3_assets = _v3_robot_body(hw)
        v2_child_names = None
        swapped = 0
        for index, node in enumerate(list(world)):
            name = str(node.get("name", ""))
            if node.tag != "body" or not name.endswith("__robot"):
                continue
            prefix = name[: -len("robot")]
            if v2_child_names is None:
                from sim.masterpi_dynamics_v2 import build_v2_xml
                v2_root = ET.fromstring(build_v2_xml(hardware))
                v2_robot = next(c for c in v2_root.find("worldbody") if c.get("name") == "robot")
                v2_child_names = {str(c.get("name")) for c in v2_robot if c.get("name")}
            clone = _prefix_named_tree(v3_robot, prefix)
            for geom in clone.iter("geom"):
                if int(geom.get("contype", "1")) & 2:
                    geom.set("conaffinity", str(int(geom.get("conaffinity", "1")) | 2))
            for attr in ("pos", "quat"):
                if node.get(attr) is not None:
                    clone.set(attr, node.get(attr))
            for child in node:
                if child.get("name") and child.get("name")[len(prefix):] not in v2_child_names:
                    clone.append(copy.deepcopy(child))   # e.g. nav camera, peer band
            world.remove(node)
            world.insert(index, clone)
            swapped += 1
        if not swapped:
            raise ValueError("no <rid>__robot bodies to swap")
        asset = root.find("asset")
        present = {el.get("name") for el in asset}
        for el in v3_assets:
            if el.get("name") not in present:
                asset.append(copy.deepcopy(el))
        root.set("model", str(root.get("model", "")) + "+" + ROBOT_MODEL_V3)
        return ET.tostring(root, encoding="unicode")

    return transform


__all__ = [
    "LEGACY_SCENE_ROBOT_MODEL",
    "ROBOT_MODELS",
    "RobotModel",
    "V3_DRAWING_HARDWARE_KEYS",
    "robot_model",
    "station_grasp_convention",
    "v3_robot_xml_transform",
]
