"""Episode resource totals and paired map-bootstrap cost ratios. Reads run folders only."""
import argparse
from collections import defaultdict
from math import fsum
from statistics import median

import numpy as np

from analysis_runs import episode_usage, map_set_value, paired_maps, read_run, show, strict
from board_sizes import size_filter


def total(values):
    return None if None in values else fsum(values)


def divide(value, denominator):
    return value / denominator if value is not None and denominator else None


def bootstrap_ratio(pairs, seed, draws):
    """Ratio of matched totals; resample whole map pairs, preserving within-map dependence."""
    if not pairs or any(None in pair for pair in pairs):
        return None, None, None
    data = np.asarray(pairs, dtype=float)
    left, right = data.sum(axis=0)
    if right == 0:
        return None, None, None
    rng = np.random.default_rng(seed)
    samples = []
    for start in range(0, draws, 256):
        indices = rng.integers(len(pairs), size=(min(256, draws - start), len(pairs)))
        totals = data[indices].sum(axis=1)
        if (totals[:, 1] == 0).any():
            return left / right, None, None
        samples.extend(totals[:, 0] / totals[:, 1])
    low, high = np.quantile(samples, [.025, .975])
    return left / right, low, high


def report(out, assigned, rows, seed, draws, sizes=None):
    if sizes is not None:
        assigned = {name: item for name, item in assigned.items() if item["size"] in sizes}
    groups = defaultdict(list)
    usage = {}
    matched = any(item.get("protocol") == "matched" for item in assigned.values())
    by_size = sizes is not None or matched
    for name, item in sorted(assigned.items()):
        row = rows.get(name)
        record = episode_usage(out, name, row)
        if matched:
            record["box_count"] = item.get("box_count")
            record["correct_deliveries"] = (row.get("correct_deliveries") if row is not None
                                            else 0 if record["api_calls"] == 0 else None)
        record["usd"] = record["cost_usd"] if record["cost_usd"] is not None else record["guard_cost_usd"]
        usage[name] = record
        key = (item["size"] if by_size else None, item["framework"], item.get("group_size"), item["speech"], map_set_value(item),
               item.get("horizon", 1), item.get("state_position", "before"))
        groups[key].append((record, row))
    print("Assigned episodes; usage includes failed episodes, retries and relays. Unrecorded episodes use settled call files to date.")
    print("USD uses reported cost when available, otherwise the episode guard total. Reasoning is included in completion tokens.")
    include_map_set = any(map_set_value(item) != "legacy" for item in assigned.values())
    include_group = any(item["framework"] == "GROUP" for item in assigned.values())
    delivery_columns = " | delivered boxes | total boxes | total tokens | tokens per delivered box" if matched else ""
    strict_tokens_column = "" if matched else "tokens per strict success | "
    print(("size | " if by_size else "") + "framework" + (" | group_size" if include_group else "") + " | speech" + (" | map_set" if include_map_set else "") + delivery_columns + " | episodes | recorded | strict successes | calls sum | calls mean | calls median | "
          "prompt tokens | completion tokens | reasoning tokens | USD sum | USD mean | missing reported cost | guard used | "
          "unknown USD | relay calls | calls per strict success | " + strict_tokens_column + "USD per strict success | horizon | "
          "recorded environment steps | recorded planning rounds | state_position")
    for (size, fw, group_size, speech, map_set, horizon, position), group in sorted(groups.items()):
        n = len(group)
        successes = sum(strict(row) for _, row in group)
        records = [r for r, _ in group]
        calls = [r["api_calls"] for r in records]
        sums = {k: total([r[k] for r in records]) for k in ("api_calls", "prompt_tokens", "completion_tokens",
                                                              "reasoning_tokens", "usd", "relay_calls")}
        tokens = total([sums["prompt_tokens"], sums["completion_tokens"]])
        delivery_cells = ()
        if matched:
            delivered = total([r["correct_deliveries"] for r in records])
            boxes = total([r["box_count"] for r in records])
            delivery_cells = (show(delivered, 0), show(boxes, 0), show(tokens, 0), show(divide(tokens, delivered)))
        missing = [r for r in records if r["cost_usd"] is None]
        guarded = sum(r["usd"] is not None for r in missing)
        cells = (fw, *((group_size or "-",) if include_group else ()), speech, *((map_set,) if include_map_set else ()), *delivery_cells, n, sum(row is not None for _, row in group), successes, show(sums["api_calls"], 0),
                 show(divide(sums["api_calls"], n)), show(median(calls) if None not in calls else None),
                 *(show(sums[k], 0) for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens")),
                 show(sums["usd"], 8), show(divide(sums["usd"], n), 8), len(missing), guarded, len(missing) - guarded,
                 show(sums["relay_calls"], 0), show(divide(sums["api_calls"], successes)),
                 *((show(divide(tokens, successes)),) if not matched else ()), show(divide(sums["usd"], successes), 8), horizon,
                 show(total([row.get("steps") for _, row in group if row is not None]), 0),
                 show(total([row.get("planning_rounds") for _, row in group if row is not None]), 0), position)
        if by_size:
            cells = (size, *cells)
        print(" | ".join(map(str, cells)))
    protocols = {(item.get("horizon", 1), item.get("state_position", "before")) for item in assigned.values()}
    for horizon, position in sorted(protocols):
        cohort = {k: v for k, v in assigned.items() if (v.get("horizon", 1), v.get("state_position", "before")) == (horizon, position)}
        frameworks = {item["framework"] for item in cohort.values()}
        if "DMAS" in frameworks or ("OWN" not in frameworks and "GROUP" not in frameworks):
            paired_cost(cohort, usage, "DMAS", horizon, seed, draws, position)
        if "OWN" in frameworks and "CMAS" in frameworks:
            paired_cost(cohort, usage, "OWN", horizon, seed, draws, position)


def paired_cost(assigned, usage, other, horizon, seed, draws, position="before"):
    groups = paired_maps(assigned, usage, "framework", ("CMAS", other))
    print(f"CMAS / {other} ratio of totals on matched maps, 95% paired percentile bootstrap, seed={seed}, draws={draws}.")
    print("An unknown total or a zero bootstrap denominator leaves the corresponding interval NA.")
    include_map_set = any(group[3] != "legacy" for group, _ in groups)
    print("size | condition | tell" + (" | map_set" if include_map_set else "") +
          " | speech | paired maps | unpaired maps | metric | ratio | lower95 | upper95 | horizon | state_position")
    for (group, speech), maps in sorted(groups.items()):
        matched = [p for _, p in sorted(maps.items()) if "CMAS" in p and other in p]
        for metric in ("api_calls", "usd"):
            pairs = [(p["CMAS"][metric], p[other][metric]) for p in matched]
            result = bootstrap_ratio(pairs, seed, draws)
            shown = group if include_map_set else group[:3]
            print(" | ".join(map(str, (*shown, speech, len(pairs), len(maps) - len(pairs), metric,
                                       *(show(v) for v in result), horizon, position))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rundir")
    parser.add_argument("--sizes", help="show separate cost totals for these comma-separated grid sizes")
    parser.add_argument("--seed", type=int, default=20261124)
    parser.add_argument("--bootstrap", type=int, default=10000, metavar="DRAWS")
    args = parser.parse_args()
    try:
        if args.bootstrap < 1 or args.seed < 0:
            raise ValueError("Bootstrap draws must be positive and seed nonnegative")
        sizes = size_filter(args.sizes)
        report(*read_run(args.rundir), args.seed, args.bootstrap, sizes)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
