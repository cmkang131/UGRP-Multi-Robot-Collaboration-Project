"""Measure FIX4 handoffs and end-of-grasp images without running a controller."""
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
TRIALS = HERE.parents[1] / "cloudrun/runs/handover-fix4-Zc6HAKV9/trials"


def degrees(angle):
    return math.degrees(math.atan2(math.sin(angle), math.cos(angle)))


def measure(folder):
    trial = json.loads((folder / "trial.json").read_bytes())
    with (folder / "events.jsonl").open() as stream:
        events = list(map(json.loads, stream))
    with (folder / "chassis.csv").open() as stream:
        trace = {round(float(r["sim_s"]), 3): r for r in csv.DictReader(stream)}
    bx, by, yaw = trial["box_start"]
    source, box_time = "initial layout", 0.
    for e in events:
        if e["event"] == "approach_end":
            a = e
        elif e["event"] == "grasp_attempt":
            rid = e["robot"]
            assert (a["robot"], a["attempt"]) == (rid, e["attempt"])
            def base(t):
                row = trace[round(t, 3)]
                return [float(row[rid+"_x"]), float(row[rid+"_y"])]
            role = "donor" if rid == trial["donor"] else "receiver"
            start, end = a["sim_s"], e["sim_s"]
            p, m, samples = e["pose"], a["alignment_measurement"], e["lift_samples"]
            entry = a["entries"][a["selected"]]
            with Image.open(folder / e["wrist_frame"]) as im:
                pixels = np.asarray(im.convert("RGB"), dtype=np.int16)
            # Frozen face-estimator colour predicate, applied to the whole 640 x 480 endpoint JPEG.
            r, g, b = pixels.transpose(2, 0, 1)
            target, other = (r, b) if trial["colour"] == "red" else (b, r)
            paint = (target > 90) & (target - np.maximum(g, other) > 60)
            yield dict(trial=trial["trial"], colour=trial["colour"], robot=rid, role=role,
                       attempt=e["attempt"], outcome=e["outcome"], approach_line=a["seq"]+1,
                       result_line=e["seq"]+1, selected=a["selected"], selected_kind=entry["kind"],
                       survey_m=round(entry["distance_m"],4), approach=a["reason"], alignment=a["alignment"],
                       align_time_s=round(a["alignment_sim_s"],1), handoff_s=round(start,1),
                       prior_box_source=source, box_time_s=round(box_time,1),
                       range_mm=round(1000*math.dist((bx,by),base(start)),2),
                       contact_x_mm=round(1000*m["contact_x_m"],2), cx_px=round(m["cx_error_px"],2),
                       face_yaw_deg=round(math.degrees(m["yaw_rad"]),2), align_area_px=m["area"],
                       edge_mm=None if a["face_check"]["long_edge_m"] is None else round(a["face_check"]["long_edge_m"]*1000,2),
                       edge_samples=a["face_check"]["samples"], end_s=round(end,1), duration_s=round(end-start,1),
                       base_shift_mm=round(1000*math.dist(base(start),base(end)),2),
                       box_shift_mm=round(1000*math.dist((bx,by),(p["x"],p["y"])),2),
                       prior_box_yaw_from_mark_deg=round(degrees(yaw-trial["mark"][2]),2),
                       end_box_yaw_from_mark_deg=round(degrees(p["yaw"]-trial["mark"][2]),2),
                       left_N=round(p["finger_n"][rid][0],3),right_N=round(p["finger_n"][rid][1],3),
                       clearance_mm=round(1000*p["clearance_m"],2),tilt_deg=round(p["tilt_deg"],2),
                       held_samples=len(samples), held_s=round(samples[-1][0]-samples[0][0],1) if samples else 0,
                       first_saved_hold_s=round(samples[0][0],1) if samples else None,
                       end_paint_pixels=int(paint.sum()), end_paint_pct=round(100*paint.mean(),2),
                       wrist=e["wrist_frame"])
        if "pose" in e:
            pose = e["pose"]
            bx, by, yaw = pose["x"], pose["y"], pose["yaw"]
            source, box_time = e["event"], pose["sim_s"]


def main():
    rows = [row for folder in sorted(TRIALS.glob("trial-*")) for row in measure(folder)]
    writer = csv.DictWriter(sys.stdout, fieldnames=rows[0], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    sheet = Image.new("RGB", (5*172, 6*152), "white")
    draw = ImageDraw.Draw(sheet)
    for i, row in enumerate(rows):
        x, y = i % 5 * 172 + 4, i // 5 * 152 + 4
        with Image.open(TRIALS / f"trial-{row['trial']:02}" / row["wrist"]) as im:
            sheet.paste(im.resize((160,120), Image.Resampling.LANCZOS), (x,y))
        draw.text((x,y+122), f"{row['trial']:02} {row['role']} {row['attempt']}  {row['outcome']}", fill="black")
    sheet.save(HERE / "fix5-grasp-wrists.jpg", quality=89)


if __name__ == "__main__":
    main()
