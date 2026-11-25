"""Lenient-parser rescues by framework and speech, including failed episodes."""
import argparse
from collections import defaultdict

from analysis_runs import episode_usage, read_run, show, strict


def report(out, assigned, rows):
    groups = defaultdict(list)
    for name, item in assigned.items():
        row = rows.get(name)
        usage = episode_usage(out, name, row)
        groups[item["framework"], item["speech"]].append((strict(row), usage["lenient_rescues"], usage["api_calls"]))
    print("framework | speech | episodes | strict successes | episodes with rescue | rescues | calls | "
          "rescues per 100 calls | strict successes with rescue")
    for group, counts in sorted(groups.items()):
        successes, rescues, calls = zip(*counts)
        rescued = None if None in rescues else sum(r > 0 for r in rescues)
        numerator = None if None in rescues else sum(rescues)
        denominator = None if None in calls else sum(calls)
        rate = 100 * numerator / denominator if numerator is not None and denominator else None
        wins = [r for win, r, _ in counts if win]
        rescued_wins = None if None in wins else sum(r > 0 for r in wins)
        cells = (*group, len(counts), sum(successes), rescued, numerator, denominator, show(rate), rescued_wins)
        print(" | ".join("NA" if c is None else str(c) for c in cells))


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
