"""The preselected cohort, floor markings and referee geometry. Distances are metres."""
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TABLE = ROOT / "scenes" / "trials.csv"
TRIAL_TABLES = (TABLE.name, "trials-swapped.csv")
STATION_TILT_MODES = ("strict", "ignore")
DEPTH, HALF_SPAN, OPENING = 2.65, 1.35, 1.10
WALL_HALF = 0.025
RELEASE_STAND, SCAN_STAND = 0.31, 0.80
RELEASE_RADIUS, YAW_TOL, TILT_TOL = 0.10, 25.0, 10.0
PARK = (-0.85, 0.75)
FLOOR_EPS, REST_SPEED = 0.004, 0.035
LIFT_FLOOR, FINGER_N, LIFT_SECONDS = 0.012, 0.5, 3.0
BODY = "dispatch_box"
AXES = {"W-E": (1, 0), "E-W": (-1, 0), "S-N": (0, 1), "N-S": (0, -1)}
ROLES = ("donor", "receiver")


def xy(direction, u, v):
    nx, ny = AXES[direction]
    return [nx*u - ny*v, ny*u + nx*v]


def uv(direction, x, y):
    nx, ny = AXES[direction]
    return [x*nx + y*ny, -x*ny + y*nx]


def yaw(direction, degrees):
    nx, ny = AXES[direction]
    angle = math.atan2(ny, nx) + math.radians(degrees)
    return math.atan2(math.sin(angle), math.cos(angle))


def trials(table_name=TABLE.name):
    if table_name not in TRIAL_TABLES:
        raise ValueError(f"unknown trial table: {table_name!r}")
    with TABLE.with_name(table_name).open(newline="") as stream:
        rows = {int(row["trial"]): definition(row) for row in csv.DictReader(stream)}
    if table_name != TABLE.name:
        for trial in rows.values():
            trial["trial_table"] = table_name
    return rows


def definition(row):
    direction = row["direction"]
    donor, receiver = ("r1", "r2") if direction in ("W-E", "S-N") else ("r2", "r1")
    def pose(prefix):
        return [*xy(direction, float(row[prefix+"_u"]), float(row[prefix+"_v"])),
                yaw(direction, float(row[prefix+"_deg"]))]
    return {"schema": "handover.trial.v1", "trial": int(row["trial"]), "seed": int(row["seed"]),
            "colour": row["colour"], "body": BODY, "direction": direction,
            "wall": "north-south" if direction in ("W-E", "E-W") else "east-west",
            "donor": donor, "receiver": receiver, "starts": {donor: pose("donor"), receiver: pose("receiver")},
            "box_start": pose("box"), "mark": [0.0, 0.0, yaw(direction, 0)],
            "receiver_sign": 10 + int(receiver[1]), "opening_m": OPENING}


def rect(direction, u0, u1, v0, v1):
    (ax, ay), (bx, by) = xy(direction, u0, v0), xy(direction, u1, v1)
    return [min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)]


def room(trial, rid):
    face = DEPTH - WALL_HALF
    u0, u1 = (-face, 0) if rid == trial["donor"] else (0, face)
    return rect(trial["direction"], u0, u1, -HALF_SPAN + WALL_HALF, HALF_SPAN - WALL_HALF)


def margin(bounds, x, y):
    x0, x1, y0, y1 = bounds
    return min(x - x0, x1 - x, y - y0, y1 - y)


def map_config(trial):
    direction = trial["direction"]
    face = DEPTH - WALL_HALF - 0.002
    signs = {}
    for role, side in (("donor", -1), ("receiver", 1)):
        nx, ny = xy(direction, -side, 0)
        facing = {(1, 0): "+x", (-1, 0): "-x", (0, 1): "+y", (0, -1): "-y"}[nx, ny]
        signs[str(10 + int(trial[role][1]))] = {
            "pos": xy(direction, side*face, 0), "facing": facing,
            "area": rect(direction, side*face, side*(face - 0.65), -0.5, 0.5)}
    return {"bounds": rect(direction, -DEPTH, DEPTH, -HALF_SPAN, HALF_SPAN), "signs": signs,
            "markers": {"robot_top_id0": 40, "robot_side_id0": 20, "n_robots": 2,
                        "dictionary": "DICT_4X4_50"}}


def sign_relative(trial, x, y):
    u, v = uv(trial["direction"], x, y)
    return [DEPTH - WALL_HALF - 0.002 - u, v]  # inward distance from card, signed lateral distance


def pose_at_sign(trial, pose):
    depth, lateral = sign_relative(trial, pose["x"], pose["y"])
    return {"inward_m": depth, "lateral_m": lateral, "height_m": pose["z"], "tilt_deg": pose["tilt_deg"],
            "yaw_from_inward_rad": math.remainder(pose["yaw"] - trial["mark"][2] - math.pi, 2*math.pi)}


def park_clear(trial, x, y):
    u, v = uv(trial["direction"], x, y)
    return u <= -0.65 and abs(v) >= 0.50 and math.dist((u, v), PARK) <= 0.20


def yaw_error(angle, nominal):
    # A plain rectangular box has the same footprint after half a turn.
    return abs(math.degrees(math.remainder(angle - nominal, math.pi)))
