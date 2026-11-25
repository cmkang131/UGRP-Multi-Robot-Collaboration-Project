import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image

from rooms3 import maps, scene
from rooms3.check_camera import absolute, select_in_room
from rooms3.convert import export


SCENES = maps.ROOT / "rooms3/scenes"
SEEDS = (0, 3, 6)
sys.path.insert(0, str(maps.ROOT / "exec"))
from harness import grasp_act_contract as contract, overhead_v1, robot_tags_v1
from harness.approach_survey_v1 import FAR_POSTURE, SurveyApproach
from harness.approach_survey_v1_parts import ground_projection
from scripts.solo_appearance_v1 import BLUE_RGBA, RED_RGBA


def bundle(seed):
    directory = SCENES / f"seed-{seed}"
    return directory, json.loads((directory / "map.json").read_bytes()), ET.parse(directory / "scene.xml")


def values(node, attribute):
    return tuple(map(float, node.get(attribute).split()))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrist_pixels(points, home, posture=FAR_POSTURE):
    """Project world points using the measured fisheye and command-only FK at the printed start pose."""
    x, y, heading = home
    c, s = math.cos(heading), math.sin(heading)
    to_ego = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    local = (np.asarray(points) - [x, y, 0]) @ to_ego.T
    origin, axes = ground_projection.camera_extrinsics(posture)
    camera = (local - origin) @ axes.T
    if np.any(camera[:, 2] <= 0):
        raise ValueError("geometry behind camera")
    norm = (camera[:, :2] / camera[:, 2:]).reshape(-1, 1, 2)
    return cv2.fisheye.distortPoints(norm, ground_projection.K, ground_projection.D).reshape(-1, 2)


class Enrolment(unittest.TestCase):
    def test_all_sixteen_maps_keep_source_owner_order_targets_and_multiplicity(self):
        for seed in range(16):
            config = maps.convert(seed)
            path = maps.REGISTRY / config["source"]["file"]
            original = json.loads(path.read_bytes())
            self.assertEqual(config["source"]["sha256"], digest(path))
            self.assertEqual(config["source"]["seed"], seed)
            self.assertEqual(len(config["boxes"]), 3)
            for cell, rid in zip(maps.CELLS, maps.ROBOTS):
                mapped = []
                for token in original[cell]:
                    kind, colour = token.split("_")
                    mapped.append(f"{kind}_{maps.COLOURS[colour]}")
                self.assertEqual(config["board"][cell], mapped)
                colours = [t[4:] for t in mapped if t.startswith("box_")]
                self.assertEqual([b["colour"] for b in config["boxes"] if b["room"] == rid], colours)
                sign = str(config["rooms"][rid]["sign"])
                self.assertEqual(config["signs"][sign]["targets"], [t[7:] for t in mapped if t.startswith("target_")])

    def test_manifest_mismatch_is_rejected_without_modifying_source(self):
        with tempfile.TemporaryDirectory(dir=maps.ROOT / ".tmp") as tmp:
            root = Path(tmp)
            folder = root / "r1/1x3"
            folder.mkdir(parents=True)
            (folder / "manifest.json").write_text('{"env0.json":"mismatch"}')
            (folder / "env0.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "enrolment hash"):
                maps.convert(0, registry=root)
            self.assertEqual((folder / "env0.json").read_text(), "{}")
            self.assertEqual(len(list(folder.iterdir())), 2)

    def test_open_defaults_can_be_changed_without_reassigning_boxes(self):
        rules = maps.Rules(room_length=2.45, room_width=1.9, door_width=.90, pad_capacity=2, boxes_per_robot="2.0")
        colours = dict(maps.COLOURS, green="blue", blue="red", red="blue")
        config = maps.convert(0, rules, colours)
        self.assertEqual(len(config["boxes"]), 6)
        self.assertEqual(config["source"]["map_set"], "scaled:2")
        self.assertEqual(len({tuple(b["start"]) for b in config["boxes"]}), 6)
        self.assertTrue(all(b["colour"] == colours[b["source_colour"]] for b in config["boxes"]))
        self.assertTrue(all(b["capacity"] == 2 and abs(b["xy"][1]) == .225 for b in config["pads"].values()))
        with self.assertRaises(ValueError):
            maps.Rules(door_width=2.9)
        with self.assertRaises(ValueError):
            maps.Rules(pad_capacity=0)
        with self.assertRaises(ValueError):
            maps.convert(0, colours={"red": "green"})

    def test_three_bundles_match_converter_and_cover_each_wrist_in_both_colours(self):
        seen = {rid: set() for rid in maps.ROBOTS}
        for seed in SEEDS:
            path, config, _ = bundle(seed)
            self.assertEqual(maps.convert(seed), config)
            self.assertEqual([b["room"] for b in config["boxes"]], list(maps.ROBOTS))
            for box in config["boxes"]:
                seen[box["room"]].add(box["colour"])
            with Image.open(path / "map.png") as picture:
                self.assertEqual(picture.size, (1160, 538))
                self.assertEqual(picture.format, "PNG")
        self.assertEqual(seen, dict.fromkeys(maps.ROBOTS, {"red", "blue"}))


class NativeDescription(unittest.TestCase):
    def test_multiple_library_exports_load_their_own_camera_and_room_geometry(self):
        with tempfile.TemporaryDirectory(dir=maps.ROOT / ".tmp") as tmp:
            for idx, length in enumerate((1.9, 2.65)):
                rules = maps.Rules(room_length=length, room_width=1.9, door_width=.90)
                directory = Path(tmp) / f"bundle-{idx}"
                export(3, directory, rules, maps.COLOURS, maps.REGISTRY)
                config = json.loads((directory / "map.json").read_bytes())
                xml = ET.parse(directory / "scene.xml")
                for sign_id, sign in config["signs"].items():
                    node = xml.find(f"worldbody/geom[@name='destination_sign_{sign_id}']")
                    np.testing.assert_allclose(values(node, "pos")[:2], sign["pos"])
                cameras = [node for node in xml.findall("worldbody/camera") if node.get("name").startswith("top")]
                self.assertEqual(len(cameras), len(overhead_v1.camera_tiles(config["bounds"])))

    def test_robot_trees_actuators_and_native_contact_pairs(self):
        reference = ET.parse(scene.TEMPLATE)
        template = reference.find(".//body[@name='r1__robot']")
        template_geom_count = len(list(template.iter("geom")))
        for seed in SEEDS:
            _, config, xml = bundle(seed)
            world = xml.find("worldbody")
            self.assertIsNone(xml.find("equality"))
            self.assertIsNone(xml.find("keyframe"))
            self.assertEqual(len(world.findall("body")), 6)
            self.assertEqual(len(xml.findall("actuator/*")), 30)
            self.assertEqual(len(xml.findall("contact/exclude")), 3 * 432)
            expected = set()
            for rid in maps.ROBOTS:
                robot = world.find(f"body[@name='{rid}__robot']")
                self.assertEqual(len(list(robot.iter("geom"))), template_geom_count)
                self.assertIsNotNone(robot.find(f".//camera[@name='{rid}__robot_cam']"))
                self.assertIsNotNone(robot.find(f"freejoint[@name='{rid}__base_free']"))
                for box in config["boxes"]:
                    for finger in ("left", "right"):
                        expected.add((f"{rid}__{finger}_finger", box["id"] + "_geom"))
            pairs = xml.findall("contact/pair")
            self.assertEqual(len(pairs), len(expected))
            self.assertEqual({(p.get("geom1"), p.get("geom2")) for p in pairs}, expected)
            joints = {j.get("name") for j in world.iter("joint")}
            bodies = {b.get("name") for b in world.iter("body")}
            for motor in xml.findall("actuator/*"):
                self.assertIn(motor.get("joint"), joints)
            for exclusion in xml.findall("contact/exclude"):
                self.assertTrue(set(exclusion.attrib.values()) <= bodies)
            for box in config["boxes"]:
                node = world.find(f"body[@name='{box['id']}']")
                self.assertEqual(node.find("joint").get("type"), "free")
                geom = node.find("geom")
                self.assertEqual(values(geom, "size"), (.017, .020, .016))
                self.assertEqual(geom.get("rgba"), {"blue": BLUE_RGBA, "red": RED_RGBA}[box["colour"]])

    def test_two_doors_four_directed_places_and_room_extents(self):
        for seed in SEEDS:
            _, config, xml = bundle(seed)
            world = xml.find("worldbody")
            self.assertEqual(set(config["pads"]), {"r1_r2", "r2_r1", "r2_r3", "r3_r2"})
            for i, rid in enumerate(maps.ROBOTS):
                x0, x1, y0, y1 = config["rooms"][rid]["bounds"]
                self.assertAlmostEqual(x1 - x0, 2.65)
                self.assertAlmostEqual(y1 - y0, 2.70)
                for box in (b for b in config["boxes"] if b["room"] == rid):
                    self.assertTrue(x0 < box["start"][0] < x1 and y0 < box["start"][1] < y1)
                if i == 2:
                    continue
                lower = world.find(f"geom[@name='jamb_{i}_-1']")
                upper = world.find(f"geom[@name='jamb_{i}_1']")
                opening = values(upper, "pos")[1] - values(upper, "size")[1] - (
                    values(lower, "pos")[1] + values(lower, "size")[1])
                self.assertAlmostEqual(opening, 1.10)
                self.assertEqual(values(upper, "pos")[0], x1)
                pads = [pad for pad in config["pads"].values() if pad["xy"][0] == x1]
                self.assertEqual(len(pads), 2)
                self.assertGreater(math.dist(pads[0]["xy"], pads[1]["xy"]), 2 * pads[0]["radius"])
                self.assertTrue(all(p["capacity"] == 1 and abs(p["xy"][1]) + p["radius"] < opening/2 for p in pads))

    def test_relative_assets_ceiling_coverage_and_marker_ids(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        detector = cv2.aruco.ArucoDetector(dictionary)
        for seed in SEEDS:
            directory, config, xml = bundle(seed)
            for item in xml.findall("asset/*[@file]"):
                path = Path(item.get("file"))
                self.assertFalse(path.is_absolute())
                self.assertTrue((directory / path).is_file())
            self.assertEqual(digest(directory / "assets/fuji_roller.stl"), scene.ROLLER_SHA)
            tiles = overhead_v1.camera_tiles(config["bounds"])
            self.assertEqual(len(tiles), 2)
            for i, centre in enumerate(tiles):
                name = "top" if i == 0 else f"top_{i}"
                camera = xml.find(f"worldbody/camera[@name='{name}']")
                np.testing.assert_allclose(values(camera, "pos")[:2], centre, atol=.00051)
            for j, rid in enumerate(maps.ROBOTS):
                for name, number, mirror in ((f"{rid}__tag_top", 40+j, False),
                                             (f"destination_sign_{11+j}", 11+j, True)):
                    geom = xml.find(f".//geom[@name='{name}']")
                    material = xml.find(f"asset/material[@name='{geom.get('material')}']")
                    texture = xml.find(f"asset/texture[@name='{material.get('texture')}']")
                    gray = cv2.imread(str(directory / texture.get("file")), cv2.IMREAD_GRAYSCALE)
                    _, ids, _ = detector.detectMarkers(cv2.flip(gray, 1) if mirror else gray)
                    self.assertEqual(ids.ravel().tolist(), [number])

    def test_portable_export_is_byte_reproducible_and_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory(dir=maps.ROOT / ".tmp") as tmp:
            dest = Path(tmp) / "out"
            cmd = [sys.executable, "-B", "-m", "rooms3.convert", "--seed", "3", "--out", str(dest)]
            subprocess.run(cmd, cwd=maps.ROOT, capture_output=True, check=True)
            expected = Path(tmp) / "second"
            subprocess.run([*cmd[:-1], str(expected)], cwd=maps.ROOT, capture_output=True, check=True)
            files = sorted(p.relative_to(dest) for p in dest.rglob("*") if p.is_file())
            self.assertEqual(files, sorted(p.relative_to(expected) for p in expected.rglob("*") if p.is_file()))
            for name in files:
                self.assertEqual(digest(dest / name), digest(expected / name), str(name))
            self.assertEqual(digest(dest / "scene.xml"), digest(SCENES / "seed-3/scene.xml"))
            self.assertNotEqual(subprocess.run(cmd, cwd=maps.ROOT, capture_output=True).returncode, 0)
            self.assertEqual(digest(dest / "scene.xml"), digest(expected / "scene.xml"))


class CameraControls(unittest.TestCase):
    def test_projected_top_cards_are_read_at_the_three_printed_start_poses(self):
        """Use the bundle's camera and card geometry to make flat, unoccluded tile fixtures."""
        directory, config, xml = bundle(0)
        names, tiles = [], {}
        for cam in xml.findall("worldbody/camera"):
            name = cam.get("name")
            if not name.startswith("top"):
                continue
            cx, cy, cz = values(cam, "pos")
            names.append((name, (cx, cy)))
            height, width = overhead_v1.HEIGHT, overhead_v1.WIDTH
            focal = height / (2 * math.tan(math.radians(float(cam.get("fovy"))) / 2))
            tile = np.full((height, width), 255, np.uint8)
            for rid in maps.ROBOTS:
                room = config["rooms"][rid]
                robot = xml.find(f"worldbody/body[@name='{rid}__robot']")
                card = robot.find(f"geom[@name='{rid}__tag_top']")
                geom_x, geom_y, geom_z = values(card, "pos")
                half = values(card, "size")[0]
                depth = cz - values(robot, "pos")[2] - geom_z
                quad = []
                for dx, dy in ((-half,half),(half,half),(half,-half),(-half,-half)):
                    x, y = absolute(room["start"], geom_x+dx, geom_y+dy)
                    quad.append([width/2 + (x-cx)*focal/depth, height/2 - (y-cy)*focal/depth])
                path = xml.find(f"asset/texture[@name='{card.get('material')}']").get("file")
                texture = cv2.imread(str(directory / path), cv2.IMREAD_GRAYSCALE)
                h, w = texture.shape
                source = np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
                warp = cv2.getPerspectiveTransform(source, np.float32(quad))
                tile = np.minimum(tile, cv2.warpPerspective(texture, warp, (width,height), borderValue=255))
            tiles[name] = tile
        with patch.object(overhead_v1, "CAMERAS", names):
            poses = overhead_v1.OverheadReader().read(tiles)
        self.assertEqual(set(poses), set(maps.ROBOTS))
        for rid, pose in poses.items():
            start = config["rooms"][rid]["start"]
            self.assertLess(math.dist(pose[:2], start[:2]), .0112)
            self.assertLess(abs(math.remainder(pose[2] - start[2], 2*math.pi)), .10)

    def test_own_wrist_frustum_and_planar_wall_card_decoding(self):
        """Analytic optical fixture; no lighting, occlusion, contact or simulated dynamics."""
        reader = robot_tags_v1.TagReader(ground_projection.K, ground_projection.D)
        for seed in SEEDS:
            directory, config, xml = bundle(seed)
            for rid in maps.ROBOTS:
                room = config["rooms"][rid]
                box = next(b for b in config["boxes"] if b["room"] == rid)
                cargo = xml.find(f"worldbody/body[@name='{box['id']}']")
                x, y, z = values(cargo, "pos")
                a, b, c = values(cargo.find("geom"), "size")
                corners = [[x+dx, y+dy, z+dz] for dx in (-a,a) for dy in (-b,b) for dz in (-c,c)]
                sign = room["sign"]
                geom = xml.find(f"worldbody/geom[@name='destination_sign_{sign}']")
                x, y, z = values(geom, "pos")
                a, b, _ = values(geom, "size")
                # Facing south (-world y) from the robot, image right points to -world x.
                card = wrist_pixels([[x+a,y,z+b], [x-a,y,z+b], [x-a,y,z-b], [x+a,y,z-b]], room["start"])
                uv = np.vstack((card, wrist_pixels(corners, room["start"])))
                self.assertTrue(np.all((uv > [1,1]) & (uv < [638,478])), (seed, rid, uv))
                texture = xml.find(f"asset/texture[@name='{geom.get('material')}']")
                gray = cv2.flip(cv2.imread(str(directory / texture.get("file")), cv2.IMREAD_GRAYSCALE), 1)
                h,w = gray.shape
                src = np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
                warp = cv2.getPerspectiveTransform(src, card.astype(np.float32))
                planar = cv2.warpPerspective(gray, warp, (640,480), borderValue=160)
                jpeg = cv2.imencode(".jpg", planar)[1].tobytes()
                found = reader.read(jpeg) + reader.read_signs_raw(jpeg)
                self.assertIn(sign, [item.get("sign") for item in found])

    def test_frozen_pan_selects_synthetic_silhouettes_of_the_nine_mapped_boxes(self):
        """Exercise pan, observation and choice with analytic wrist images."""
        for seed in SEEDS:
            _, config, xml = bundle(seed)
            for box in config["boxes"]:
                rid = box["room"]
                home = config["rooms"][rid]["start"]
                bounds = config["rooms"][rid]["bounds"]
                kind = {"blue": "cyan", "red": "red"}[box["colour"]]
                cargo = xml.find(f"worldbody/body[@name='{box['id']}']")
                x, y, z = values(cargo, "pos")
                geom = cargo.find("geom")
                a, b, c = values(geom, "size")
                colour = tuple(round(255 * ch) for ch in reversed(values(geom, "rgba")[:3]))
                points = [[x+dx, y+dy, z+dz] for dx in (-a,a) for dy in (-b,b) for dz in (-c,c)]
                chooser = lambda entries: select_in_room(entries, kind, home, bounds)
                survey = SurveyApproach(contract, chooser, survey_fast=True, align_fast=True, approach_visual=True)
                posture = dict(FAR_POSTURE)
                for tick in range(100):
                    jpeg = b""
                    if survey.needs_frame():
                        pixels = np.full((480, 640, 3), 170, dtype=np.uint8)
                        try:
                            uv = wrist_pixels(points, home, posture)
                        except ValueError:  # Box behind the lens during this pan.
                            uv = None
                        if uv is not None and np.all((uv >= [0,0]) & (uv <= [639,479])):
                            cv2.fillConvexPoly(pixels, cv2.convexHull(uv.round().astype(np.int32)), colour)
                        jpeg = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes()
                    row = survey.step(jpeg, tick * .1)
                    if survey.index is not None or survey.arrived:
                        break
                    self.assertFalse(any(row["wheels"]))
                    posture = {int(s): p for s, p in row["pwm"].items()}
                self.assertIsNotNone(survey.index, (seed, rid, survey.entries))
                selected = survey.entries[survey.index]
                self.assertEqual(selected["kind"], kind)
                self.assertGreaterEqual(selected["observations"], 2)
                self.assertLessEqual(math.dist(absolute(home, selected["x"], selected["y"]), (x,y)),
                                     survey.baseline.POS_GATE_M)

    def test_archived_fix4_red_and_blue_first_frames_reach_frozen_projection(self):
        archive = scene.TEMPLATE.parents[1]
        for number, kind in ((1, "red"), (2, "cyan")):
            trial = archive / f"trial-{number:02}"
            setup = json.loads((trial / "trial.json").read_text())
            jpg = (trial / "0003-donor-first-wrist.jpg").read_bytes()
            approach = SurveyApproach(contract, lambda entries: 0, survey_fast=True)
            first = approach.student.Survey(approach.baseline)
            first.observe(jpg, FAR_POSTURE)
            origin = setup["starts"][setup["donor"]]
            points = [absolute(origin, *t["points"][0]) for t in first._tracks if t["kind"] == kind]
            error = min(math.dist(p, setup["box_start"][:2]) for p in points)
            self.assertLessEqual(error, approach.baseline.POS_GATE_M)
            print(f"archived FIX4 {kind}: first wrist error {error:.4f} m")

    def test_chooser_only_uses_visible_entries_in_requesting_room(self):
        entries = [{"kind": "cyan", "x": .5, "y": 0},
                   {"kind": "red", "x": 2, "y": 0}, {"kind": "red", "x": .75, "y": .1}]
        self.assertEqual(select_in_room(entries, "red", (0.,0.,0.), [-1,1,-1,1]), 2)
        self.assertIsNone(select_in_room(entries[:2], "red", (0.,0.,0.), [-1,1,-1,1]))
        self.assertIsNone(select_in_room([], "red", (0.,0.,0.), [-1,1,-1,1]))


if __name__ == "__main__":
    unittest.main()
