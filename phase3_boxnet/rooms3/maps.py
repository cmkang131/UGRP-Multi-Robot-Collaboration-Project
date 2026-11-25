"""Convert a published BoxNet map in place order. The source registry is read-only."""
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path

from handover import layout


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT.parent / "20261124-chen2d-snap-v20" / "envs-scaled"
CELLS = ("0.5_0.5", "0.5_1.5", "0.5_2.5")
ROBOTS = ("r1", "r2", "r3")
COLOURS = {"blue": "blue", "red": "red", "green": "red", "purple": "blue", "orange": "red"}


@dataclass(frozen=True)
class Rules:
    room_length: float = layout.DEPTH
    room_width: float = 2 * layout.HALF_SPAN
    door_width: float = layout.OPENING
    pad_capacity: int = 1
    boxes_per_robot: str = "1"

    def __post_init__(self):
        dims = self.room_length, self.room_width, self.door_width
        if not all(math.isfinite(v) and v > 0 for v in dims):
            raise ValueError("room and door dimensions must be finite and positive")
        if self.door_width >= self.room_width or self.door_width / 4 <= layout.RELEASE_RADIUS:
            raise ValueError("the opening must fit two disjoint pad footprints and leave two jambs")
        if type(self.pad_capacity) is not int or self.pad_capacity < 1:
            raise ValueError("pad capacity must be a positive integer")
        try:
            rate = Decimal(str(self.boxes_per_robot))
        except InvalidOperation as error:
            raise ValueError("boxes per robot must be a decimal number") from error
        if not rate.is_finite() or rate <= 0:
            raise ValueError("boxes per robot must be finite and positive")
        object.__setattr__(self, "boxes_per_robot", format(rate.normalize(), "f"))


def load_source(seed, rules, registry=REGISTRY):
    folder = registry / ("r" + rules.boxes_per_robot) / "1x3"
    name = f"env{seed}.json"
    manifest = json.loads((folder / "manifest.json").read_bytes())
    data = (folder / name).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if manifest.get(name) != sha:
        raise ValueError(f"source map does not match its enrolment hash: {name}")
    return json.loads(data), {"seed": seed, "map_set": "scaled:" + rules.boxes_per_robot,
                              "file": str((folder / name).relative_to(registry)), "sha256": sha}


def convert(seed, rules=Rules(), colours=None, *, registry=REGISTRY):
    colours = dict(COLOURS if colours is None else colours)
    if not colours or set(colours.values()) - {"blue", "red"}:
        raise ValueError("the frozen camera supports blue and red paint")
    source, provenance = load_source(seed, rules, registry)
    if set(source) != set(CELLS):
        raise ValueError("expected exactly the enrolled 1 by 3 board")
    length, width = rules.room_length, rules.room_width
    wall = layout.WALL_HALF
    rooms, boxes, pads, signs, board = {}, [], {}, {}, {}
    for i, (cell, rid) in enumerate(zip(CELLS, ROBOTS)):
        centre = (i - 1) * length
        bounds = [centre - length / 2, centre + length / 2, -width / 2, width / 2]
        sign = str(11 + i)
        wall_y = -width / 2 + wall + .002
        home = [centre, max(.20 * width, wall_y + .65 + .10 + .75), -math.pi / 2]
        targets = []
        signs[sign] = {"pos": [centre, wall_y], "facing": "+y",
                       "area": [centre - .50, centre + .50, wall_y, wall_y + .65], "targets": targets}
        rooms[rid] = {"cell": cell, "bounds": bounds, "start": home, "sign": int(sign)}
        board[cell] = []
        room_boxes = []
        for token in source[cell]:
            kind, _, original = token.partition("_")
            if kind not in ("box", "target") or original not in colours:
                raise ValueError(f"unsupported BoxNet token or missing paint assignment: {token}")
            colour = colours[original]
            board[cell].append(f"{kind}_{colour}")
            if kind == "target":
                targets.append(colour)
            else:
                room_boxes.append({"id": f"box_{len(boxes) + len(room_boxes) + 1:02}",
                                   "source_colour": original, "colour": colour, "room": rid})
        # Keep each box in its enrolled square. Multiple boxes use separate pickup lanes.
        for j, box in enumerate(room_boxes):
            lateral = .30 * (j - (len(room_boxes) - 1) / 2)
            x, y = centre + lateral, home[1] - .75
            if (abs(lateral) + .10 >= length / 2 - wall or y <= wall_y + .65
                    or home[1] + .21 >= width / 2 - wall or length / 2 - wall < .50):
                raise ValueError("the selected dimensions cannot fit the pickup lanes and sign area")
            box["start"] = [x, y, 0.]
            boxes.append(box)
    expected = max(1, round(Decimal(rules.boxes_per_robot) * len(ROBOTS)))
    if len(boxes) != expected:
        raise ValueError("box count differs from the declared BoxNet density")
    if Counter(b["colour"] for b in boxes) != Counter(t for sign in signs.values() for t in sign["targets"]):
        raise ValueError("target multiplicities must match the physical boxes")
    for west, east in zip(ROBOTS, ROBOTS[1:]):
        door_x = rooms[west]["bounds"][1]
        for src, dst, side in ((west, east, -1), (east, west, 1)):
            pads[f"{src}_{dst}"] = {"from": src, "to": dst,
                                   "xy": [door_x, side * rules.door_width / 4],
                                   "radius": layout.RELEASE_RADIUS, "capacity": rules.pad_capacity}
    return {"schema": "rooms3.map.v1", "source": provenance, "rules": asdict(rules),
            "colour_map": colours, "board": board, "rooms": rooms, "boxes": boxes, "pads": pads,
            "bounds": [-1.5 * length, 1.5 * length, -width / 2, width / 2], "signs": signs,
            "markers": {"robot_top_id0": 40, "robot_side_id0": 20, "n_robots": 3,
                        "dictionary": "DICT_4X4_50"}}
