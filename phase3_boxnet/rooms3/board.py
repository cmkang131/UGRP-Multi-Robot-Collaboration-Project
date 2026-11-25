"""Rebuild the referee and camera boards independently from current measurements."""
from collections import Counter
import math

from handover import criteria, layout
from rooms3.check_camera import absolute
from rooms3.maps import ROBOTS


def location(scene, x, y, *, on_floor=True):
    if not all(math.isfinite(v) for v in (x, y)):
        raise ValueError("nonfinite box measurement")
    if on_floor:
        for name, pad in scene["pads"].items():
            if math.dist((x, y), pad["xy"]) <= pad["radius"]:
                return pad["to"], name
    # At an unmarked shared boundary the half-open intervals assign the centre to the east room.
    for rid in ROBOTS:
        west, east, south, north = scene["rooms"][rid]["bounds"]
        if south <= y <= north and west <= x and (x < east or rid == ROBOTS[-1] and x == east):
            return rid, None
    return None, None


def landed(witness):
    # A free, settled box is scored wherever it landed, including on its side.
    return (criteria.free(witness) and abs(witness["clearance_m"]) <= layout.FLOOR_EPS
            and witness["speed_m_s"] <= layout.REST_SPEED)


def rebuild(scene, measurements, seen_signs):
    """Measurements have an ID local to their reader. Each decoded sign reveals that room's target list."""
    boxes, remaining = [], {}
    for rid in ROBOTS:
        sign = str(scene["rooms"][rid]["sign"])
        remaining[rid] = list(scene["signs"][sign]["targets"]) if int(sign) in seen_signs else None
    for item in measurements:
        x, y = item["xy"]
        rid, pad = location(scene, x, y, on_floor=item["on_floor"])
        rid = item.get("held_by") or rid
        box = dict(item, room=rid, pad=pad, delivered=False)
        if rid and pad is None and item["on_floor"] and remaining[rid] and item["colour"] in remaining[rid]:
            area = scene["signs"][str(scene["rooms"][rid]["sign"])]["area"]
            if layout.margin(area, x, y) >= 0:
                remaining[rid].remove(item["colour"])
                box["delivered"] = True
        boxes.append(box)
    cells = {}
    for rid in ROBOTS:
        tokens = ["box_" + b["colour"] for b in boxes if b["room"] == rid and b["on_floor"] and not b["delivered"]]
        tokens.extend("target_" + c for c in remaining[rid] or ())
        cells[scene["rooms"][rid]["cell"]] = tokens
    return {"boxes": boxes, "remaining_targets": remaining, "cells": cells,
            "pads": {name: sum(b["pad"] == name for b in boxes) for name in scene["pads"]},
            "delivered": sum(b["delivered"] for b in boxes)}


def referee_board(scene, witnesses):
    cargo = []
    for box in scene["boxes"]:
        p = witnesses[box["id"]]
        holding = next((r for r in p["finger_n"] if criteria.held(p, r, ignore_tilt=True)), None)
        cargo.append({"id": box["id"], "colour": box["colour"], "xy": [p["x"], p["y"]],
                      "on_floor": landed(p), "held_by": holding})
    return rebuild(scene, cargo, {int(s) for s in scene["signs"]})


def camera_board(scene, views):
    cargo, signs = [], set()
    for rid in ROBOTS:
        view = views.get(rid)
        if not view:
            continue
        expected = scene["rooms"][rid]["sign"]
        if expected in view["sign_ids"]:
            signs.add(expected)
        if view["pose"] is None:
            continue
        for i, entry in enumerate(view["entries"]):
            xy = absolute(view["pose"], entry["x"], entry["y"])
            owner, _ = location(scene, *xy)
            if owner == rid and entry["kind"] in ("red", "cyan"):
                # Only the owning robot contributes this colour track. A floor projection estimates rest.
                cargo.append({"id": f"{rid}-track-{i}", "colour": "blue" if entry["kind"] == "cyan" else "red",
                              "xy": xy, "on_floor": True})
    return rebuild(scene, cargo, signs)


def differences(scene, truth, perceived):
    rows = []
    for rid in ROBOTS:
        cell = scene["rooms"][rid]["cell"]
        actual, seen = Counter(truth["cells"][cell]), Counter(perceived["cells"][cell])
        if actual != seen or perceived["remaining_targets"][rid] is None:
            rows.append({"room": rid, "missing": list((actual - seen).elements()),
                         "extra": list((seen - actual).elements()),
                         "sign_seen": perceived["remaining_targets"][rid] is not None})
    pads = {p: [n, perceived["pads"][p]] for p, n in truth["pads"].items() if n != perceived["pads"][p]}
    distances = sorted((math.dist(b["xy"], v["xy"]), b["id"], v["id"])
                       for b in truth["boxes"] for v in perceived["boxes"]
                       if b["room"] == v["room"] and b["colour"] == v["colour"])
    unpaired_bodies = {b["id"] for b in truth["boxes"]}
    unpaired_tracks = {v["id"] for v in perceived["boxes"]}
    pairs = []
    for metres, body, track in distances:
        if body in unpaired_bodies and track in unpaired_tracks:
            pairs.append({"body": body, "track": track, "xy_error_m": metres})
            unpaired_bodies.remove(body)
            unpaired_tracks.remove(track)
    return {"rooms": rows, "pads_truth_perceived": pads, "delivered_truth_perceived":
            [truth["delivered"], perceived["delivered"]], "spatial_pairs": pairs,
            "unpaired_bodies": sorted(unpaired_bodies), "unpaired_tracks": sorted(unpaired_tracks)}
