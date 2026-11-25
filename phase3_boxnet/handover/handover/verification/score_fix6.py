"""Score the four fetched FIX6 rows alongside the twenty preselected archived rows."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from handover import layout, score


def score_table(name, archive, rerun, replaced):
    table = layout.trials(name)
    results = []
    print(f"Trial table {name}")
    for number in table:
        fresh = number in replaced
        source = rerun if fresh else archive
        folder = source / "trials" / f"trial-{number:02d}"
        expected_mode = "ignore" if fresh else "strict"
        run = json.loads((folder / "run.json").read_bytes())
        receipt = json.loads((folder / "cloud-meta.json").read_bytes())
        if (run.get("station_tilt", "strict") != expected_mode or receipt.get("station_tilt", "strict") != expected_mode
                or receipt.get("trial_table", layout.TABLE.name) != name or receipt["trial"] != number
                or receipt["task_exit"] != 0):
            raise ValueError(f"{folder} lacks the expected completed task receipt or station mode {expected_mode}")
        result = score.score_dir(folder, table)
        if (result["trial"], result["trial_table"]) != (number, name) or not result["evaluated"]:
            raise ValueError(f"{folder} has incomplete or inconsistent evidence: {result['reason']}")
        results.append(result)
        retries = result["retries"]
        print(f"  {number:02d} {result['status']} {result['stage']}  {result['reason']}  "
              f"retries donor={retries['donor']} receiver={retries['receiver']}  [{folder}]")
    passed, gate = score.aggregate(results)
    print(f"{name}  {passed}/12 successes  |  12 evaluated  |  gate {gate} (requires 10/12)")
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path, help="FIX6 cohort directory for original trials 4 and 6")
    parser.add_argument("swapped", type=Path, help="FIX6 cohort directory for swapped trials 2 and 5")
    args = parser.parse_args(argv)
    runs = ROOT / "cloudrun/runs"
    try:
        original = score_table("trials.csv", runs / "handover-fix4-Zc6HAKV9", args.original, {4, 6})
        swapped = score_table("trials-swapped.csv", runs / "handover-fix5-swap-yimHXMgy", args.swapped, {2, 5})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Comparison incomplete: {exc}\n")
    print(f"Both tables  {original + swapped}/24 successes  |  4 FIX6 measurements and 20 archived measurements")


if __name__ == "__main__":
    main()
