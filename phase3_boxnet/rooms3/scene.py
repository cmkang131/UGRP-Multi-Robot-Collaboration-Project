"""Assemble native MJCF from the archived, compiled-in-FIX4 MasterPi input."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from handover import layout
from rooms3.maps import ROBOTS, ROOT


TEMPLATE = ROOT / "cloudrun/runs/handover-fix4-Zc6HAKV9/trials/trial-01/scene.xml"
TEMPLATE_SHA = "8cee8198fdb8a86e3920dd8df6b8a73579f2eee687e1f06b1224b245d76c13da"
ROLLER = ROOT / "exec-repo/sim/assets/masterpi_drive_friction_v2/fuji_roller.stl"
ROLLER_SHA = "2bea3228aa5766e2ce42f4f4a46cdf4bc3e63802958fa7f0ffb9688d9393a424"


def verified(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"unexpected source digest for {path.name}")
    return data


def clone(element, old, new):
    node = copy.deepcopy(element)
    for item in node.iter():
        for field, value in item.attrib.items():
            if value.startswith(old):
                item.set(field, new + value[len(old):])
    return node


def numbers(*values):
    return " ".join(f"{v:.12g}" for v in values)


def set_pose(body, pose, z):
    x, y, angle = pose
    body.set("pos", numbers(x, y, z))
    body.set("quat", numbers(math.cos(angle / 2), 0, 0, math.sin(angle / 2)))


def build_rooms(world, scene):
    def slab(name, x, y, half_x, half_y, height, *, tape=False):
        ET.SubElement(world, "geom", name=name, type="box", pos=numbers(x, y, height),
                      size=numbers(half_x, half_y, height), mass="0",
                      rgba=".17 .17 .17 1" if tape else ".23 .28 .33 1",
                      contype="0" if tape else "1", conaffinity="0" if tape else "3")

    lo, hi, south, north = scene["bounds"]
    half, jamb = layout.WALL_HALF, scene["rules"]["door_width"] / 2
    for i, x in enumerate((lo, hi)):
        slab(f"end_{i}", x, 0, half, north + half, .20)
    for i, y in enumerate((south, north)):
        slab(f"side_{i}", 0, y, hi, half, .20)
    for i, rid in enumerate(ROBOTS[:-1]):
        x = scene["rooms"][rid]["bounds"][1]
        for side in (-1, 1):
            slab(f"jamb_{i}_{side}", x, side * (north + jamb) / 2,
                 half, (north - jamb) / 2, .20)
    for name, pad in scene["pads"].items():
        x, y = pad["xy"]
        for side in (-1, 1):
            slab(f"pad_{name}_x_{side}", x + side * .037, y, .002, .049, .00025, tape=True)
            slab(f"pad_{name}_y_{side}", x, y + side * .047, .037, .002, .00025, tape=True)
    world.find("geom[@name='floor']").set("size", numbers(hi + .3, north + .3, .1))
    ET.SubElement(world, "camera", name="rooms3_overview", pos=numbers(0, 0, 1.65 * hi),
                  xyaxes="1 0 0 0 1 0", fovy="52")


def write_scene(scene, directory):
    """Run once per converter process, as both frozen card modules read their map on import."""
    sys.path.insert(0, str(ROOT / "exec"))
    os.environ["UGRP_MAP_SCENE"] = str((directory / "map.json").resolve())
    from harness import overhead_v1 as overhead, robot_tags_v1 as tags
    from scripts.solo_appearance_v1 import BLUE_RGBA, RED_RGBA

    if overhead._MAP != scene or tags._MAP != scene:
        raise RuntimeError("launch the scene converter in a fresh process for this map")
    root = ET.fromstring(verified(TEMPLATE, TEMPLATE_SHA))
    asset, world = root.find("asset"), root.find("worldbody")
    actuators, contacts = root.find("actuator"), root.find("contact")
    robot = world.find("body[@name='r1__robot']")
    box = world.find("body[@name='dispatch_box']")
    motors = [n for n in actuators if n.get("joint").startswith("r1__")]
    excludes = [n for n in contacts.findall("exclude") if n.get("body1").startswith("r1__")]
    pairs = [n for n in contacts.findall("pair") if n.get("geom1").startswith("r1__")]
    for name in ("r1__tag_mast", "r1__tag_top"):
        robot.remove(robot.find(f"geom[@name='{name}']"))
    for node in list(world):
        if node.tag != "light" and node.get("name") != "floor":
            world.remove(node)
    for node in list(asset):
        if node.get("name", "").startswith(("sign_tag_", "robot_top_")):
            asset.remove(node)
    del actuators[:], contacts[:]
    assets = directory / "assets"
    assets.mkdir()
    (assets / ROLLER.name).write_bytes(verified(ROLLER, ROLLER_SHA))
    asset.find("mesh[@name='fuji_roller_v2']").set("file", "assets/" + ROLLER.name)
    for rid in ROBOTS:
        base = clone(robot, "r1__", rid + "__")
        set_pose(base, scene["rooms"][rid]["start"], float(robot.get("pos").split()[2]))
        world.append(base)
        actuators.extend(clone(n, "r1__", rid + "__") for n in motors)
        contacts.extend(clone(n, "r1__", rid + "__") for n in excludes)
    for cargo in scene["boxes"]:
        body = clone(box, "dispatch_box", cargo["id"])
        set_pose(body, cargo["start"], .016)
        body.find("geom").set("rgba", {"red": RED_RGBA, "blue": BLUE_RGBA}[cargo["colour"]])
        world.append(body)
        for pair in pairs:
            for rid in ROBOTS:
                entry = clone(pair, "r1__", rid + "__")
                entry.set("geom2", cargo["id"] + "_geom")
                contacts.append(entry)
    build_rooms(world, scene)
    sign_ids = [int(s) for s in scene["signs"]]
    textures = tags.write_textures(assets, [*sign_ids, *overhead.card_numbers(ROBOTS)])
    textures = {k: "assets/" + Path(v).name for k, v in textures.items()}
    xml = tags.add_signs(ET.tostring(root, encoding="unicode"), textures, sign_ids)
    xml = overhead.add_to_scene(xml, ROBOTS, textures)
    (directory / "scene.xml").write_text(xml)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="converter staging directory containing map.json")
    directory = parser.parse_args().bundle.resolve()
    write_scene(json.loads((directory / "map.json").read_bytes()), directory)
