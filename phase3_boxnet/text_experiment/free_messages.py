"""CSV for hand coding free-speech episodes. Multi-sender cells contain aligned JSON arrays."""
import argparse
import csv
import json
import re
import sys

from analysis_runs import read_run
from relay import free_checks
from storage import read_json


def old_target_wrong(text):
    return bool(re.search(r"(?<![a-z0-9])targets?(?![a-z0-9])", text, re.I)
                and re.search(r"\b(?:wrong|no\s+longer|not)\b", text, re.I))


def cell(values):
    if not values:
        return ""
    if len(values) == 1:
        return "" if values[0] is None else values[0]
    return json.dumps(values, ensure_ascii=False)


def report(out, assigned, rows):
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(("map", "framework", "episode_id", "condition", "tell", "sender", "reply_class", "text",
                     "delivered_text", "names_colour", "names_dropoff_or_D", "old_target_wrong",
                     "first_plan_respected", "change_respected"))
    for name, item in sorted(assigned.items()):
        if item["speech"] != "free":
            continue
        row = rows.get(name) or {}
        entries = []
        for record in row.get("relay_records", []):
            sent = record["delivered_text"]
            number = record["call_number"]
            raw = None
            if number is not None:
                path = out / "episodes" / name / "calls" / f"{number:05d}.json"
                if not path.is_file():
                    raise ValueError(f"Missing free reply: {path}")
                raw = read_json(path)["response"]
            flags = free_checks(sent, row["event"]) if sent is not None else {}
            entries.append((record["sender"], record["reply_class"] or record["status"], raw, sent,
                            flags.get("names_colour"), flags.get("names_destination"),
                            old_target_wrong(sent) if sent is not None else None))
        first = next((it for it in row.get("iterations", []) if row.get("event") and it["executed"]
                      and it["step"] > row["event"]["step"]), {})
        columns = zip(*entries) if entries else ((),) * 7
        writer.writerow((f"{item['size']}/env{item['env_seed']}", item["framework"], name, item["condition"],
                         item["tell"], *(cell(v) for v in columns), first.get("executed_plan_respected_change"),
                         row.get("change_respected")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rundir")
    args = parser.parse_args()
    try:
        report(*read_run(args.rundir))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
