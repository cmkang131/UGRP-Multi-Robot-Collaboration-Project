"""Map-paired delivery outcomes and an exact sign test of CMAS minus DMAS changes."""
import argparse
from collections import defaultdict
from fractions import Fraction
from math import comb, exp, fsum, isfinite, lgamma, log, log1p

from analysis_runs import arm_value, map_set_value, paired_maps, read_run, show, strict

from relay import RELAY_DISPLAYS, RELAY_TIMINGS, SPEECH_RULES, relay_cell
from storage import local_path
from summarize import assigned_episodes, read_episode_rows


def sign_test(positive, negative):
    n = positive + negative
    if not n:
        return None
    tail = sum(comb(n, i) for i in range(min(positive, negative) + 1))
    return min(Fraction(1), Fraction(2 * tail, 2 ** n))


def outcome_score(row, outcome):
    if outcome == "strict":
        return int(bool(row and row["finished"] and row["strict_success"]))
    return row["change_respected"] if row is not None else None


def report_pairs(assigned, rows, a, b, outcome="strict", arm_field="speech"):
    if a == b:
        raise ValueError("Choose two distinct speech rules")
    observed = {row["episode_id"]: row for row in rows}
    groups = defaultdict(lambda: defaultdict(dict))
    hashes = {}
    for name, item in assigned.items():
        rule = arm_value(item, arm_field)
        if rule not in (a, b):
            continue
        group = item["size"], item["condition"], item["tell"] or "-", map_set_value(item)
        seed, fw = item["env_seed"], item["framework"]
        inputs = item.get("env_sha256"), item.get("event_sha256"), item.get("speech_event_sha256")
        if hashes.setdefault((group, seed), inputs) != inputs:
            raise ValueError(f"Map inputs differ for {group}, slot {seed}")
        arms = groups[group][fw].setdefault(seed, {})
        if rule in arms:
            raise ValueError(f"Duplicate {rule} assignment for {group}, {fw}, slot {seed}")
        arms[rule] = observed.get(name)
    if not groups:
        raise ValueError("Neither requested speech rule has assigned episodes")
    for group, frameworks in sorted(groups.items()):
        print(f"{' / '.join(group)}   a={a}   b={b}   outcome={outcome}")
        print(f"framework | map | {a} | {b} | b-a | {a} misuse before | {a} misuse after | {b} misuse before | {b} misuse after")
        deltas = {}
        for fw, maps in sorted(frameworks.items()):
            changes = {}
            for seed, arms in sorted(maps.items()):
                scores = {rule: outcome_score(row, outcome) for rule, row in arms.items()}
                if scores.get(a) is not None and scores.get(b) is not None:
                    changes[seed] = scores[b] - scores[a]
                shown = [scores.get(rule, "unassigned") for rule in (a, b)]
                misuse = [arms[rule][field] if arms.get(rule) is not None else "NA"
                          for rule in (a, b) for field in ("dropoff_misuse_before", "dropoff_misuse_after")]
                cells = (fw, seed, *shown, changes.get(seed), *misuse)
                print(" | ".join("NA" if v is None else str(v) for v in cells))
            values = list(changes.values())
            print(f"{fw}   b better={values.count(1)}   a better={values.count(-1)}   tie={values.count(0)}"
                  f"   unpaired={len(maps) - len(changes)}")
            deltas[fw] = changes
        cmas, dmas = deltas.get("CMAS", {}), deltas.get("DMAS", {})
        shared = cmas.keys() & dmas.keys()
        differences = [cmas[s] - dmas[s] for s in shared]
        positive, negative = sum(d > 0 for d in differences), sum(d < 0 for d in differences)
        p = sign_test(positive, negative)
        probability = "NA" if p is None else f"{p} ({float(p):.8g})"
        print(f"CMAS minus DMAS   positive={positive}   negative={negative}   ties dropped={differences.count(0)}"
              f"   n used={positive + negative}   exact two-sided sign p={probability}")


def binomial_lower(k, n, tail):
    """One-sided Clopper–Pearson lower endpoint, by inversion of P(X >= k)."""
    if k == 0:
        return 0.
    if k == n:
        return tail ** (1 / n)
    coefficients = [lgamma(n + 1) - lgamma(i + 1) - lgamma(n - i + 1) for i in range(k, n + 1)]
    lo, hi = 0., 1.
    for _ in range(54):
        p = (lo + hi) / 2
        a, b = log(p), log1p(-p)
        probability = fsum(exp(c + i * a + (n - i) * b) for i, c in enumerate(coefficients, k))
        if probability < tail:
            lo = p
        else:
            hi = p
    return (lo + hi) / 2


def paired_interval(positive, negative, n, confidence):
    """Exact conservative interval for p(positive discordance) - p(negative discordance)."""
    if not n:
        return None, None, None
    tail = (1 - confidence) / 4
    lower = binomial_lower(positive, n, tail) - (1 - binomial_lower(n - negative, n, tail))
    upper = (1 - binomial_lower(n - positive, n, tail)) - binomial_lower(negative, n, tail)
    return (positive - negative) / n, max(-1., lower), min(1., upper)


def discordance(maps, plus, minus, outcome):
    positive = negative = dropped = 0
    for seed, pair in maps.items():
        if plus not in pair or minus not in pair:
            raise ValueError(f"Unassigned arm at slot {seed}; paired inference needs both {plus} and {minus} assigned")
        if outcome == "strict":
            x, y = strict(pair[plus]), strict(pair[minus])
        else:
            x, y = (outcome_score(pair[arm], outcome) for arm in (plus, minus))
        if x is None or y is None:
            dropped += 1
        else:
            positive += int(x > y)
            negative += int(x < y)
    return positive, negative, len(maps) - dropped, dropped


def holm(pvalues):
    # The prespecified family is CMAS and DMAS. An unavailable test spends no alpha.
    adjusted = {}
    maximum = Fraction(0)
    ordered = sorted((p, fw) for fw, p in pvalues.items() if fw in ("CMAS", "DMAS") and p is not None)
    for index, (p, fw) in enumerate(ordered):
        maximum = max(maximum, min(1, (2 - index) * p))
        adjusted[fw] = maximum
    return adjusted


def mcnemar(assigned, observed, a, b, outcome, arm_field="speech"):
    if a == b:
        raise ValueError("Choose two distinct speech rules")
    groups = paired_maps(assigned, observed, arm_field, (a, b))
    if not groups:
        raise ValueError("Neither requested speech rule has assigned episodes")
    print(f"Exact two-sided McNemar; difference = {b} minus {a}; outcome = {outcome}")
    print("95% exact conservative paired CI: simultaneous Bonferroni–Clopper–Pearson bounds on the two discordant probabilities.")
    if arm_field == "speech":
        print("Holm family: CMAS and DMAS within each size, condition and tell.")
    else:
        print("Each relay contrast has its own exact p-value and 95% interval.")
    include_map_set = any(group[3] != "legacy" for group, _ in groups)
    header = f"size | condition | tell" + (" | map_set" if include_map_set else "") + f" | framework | assigned maps | paired n | NA pairs | {b} only | {a} only | difference | lower95 | upper95 | exact p"
    print(header + (" | Holm p" if arm_field == "speech" else ""))
    results = defaultdict(dict)
    for (group, fw), maps in sorted(groups.items()):
        pos, neg, n, dropped = discordance(maps, b, a, outcome)
        p = (sign_test(pos, neg) if pos + neg else Fraction(1)) if n else None
        results[group][fw] = (len(maps), n, dropped, pos, neg, *paired_interval(pos, neg, n, .95), p)
    for group, frameworks in results.items():
        adjusted = holm({fw: values[-1] for fw, values in frameworks.items()}) if arm_field == "speech" else {}
        for fw, (total, n, dropped, pos, neg, delta, lo, hi, p) in frameworks.items():
            cells = (*(group if include_map_set else group[:3]), fw, total, n, dropped, pos, neg, show(delta), show(lo), show(hi), probability_text(p))
            if arm_field == "speech":
                cells += (probability_text(adjusted.get(fw)),)
            print(" | ".join(map(str, cells)))


def probability_text(p):
    return "NA" if p is None else f"{p} ({float(p):.8g})"


def noninferiority(assigned, observed, frameworks, speech, margin):
    if len(frameworks) != 2 or len(set(frameworks)) != 2:
        raise ValueError("--frameworks needs two distinct framework names")
    if not isfinite(margin) or not 0 <= margin <= 1:
        raise ValueError("--margin must be a finite proportion in [0, 1]")
    plus, minus = frameworks
    groups = paired_maps(assigned, observed, "framework", frameworks, speech=speech)
    if not groups:
        raise ValueError("No assignments for the requested frameworks and speech")
    print(f"Strict success, {plus} minus {minus}; margin = {margin:g}. Two-sided 90% exact conservative paired CI "
          "(simultaneous Bonferroni–Clopper–Pearson discordance bounds).")
    include_map_set = any(group[3] != "legacy" for group, _ in groups)
    print(f"size | condition | tell" + (" | map_set" if include_map_set else "") +
          f" | speech | paired maps | {plus} only | {minus} only | difference | lower90 | upper90 | verdict")
    for (group, rule), maps in sorted(groups.items()):
        pos, neg, n, _ = discordance(maps, plus, minus, "strict")
        delta, lo, hi = paired_interval(pos, neg, n, .90)
        verdict = "non-inferior" if lo > -margin else "non-inferiority not established"
        print(" | ".join(map(str, (*(group if include_map_set else group[:3]), rule, n, pos, neg, show(delta), show(lo), show(hi), verdict))))


def relay_contrasts(a, b):
    if (a is None) != (b is None) or (a is not None and a == b):
        raise ValueError("Supply two distinct relay arms with --a and --b, or omit both")
    contrasts = []
    if a is None or {a, b} == set(RELAY_TIMINGS):
        early, late = (a, b) if a is not None else RELAY_TIMINGS
        contrasts.extend((f"{early}/{d}", f"{late}/{d}") for d in RELAY_DISPLAYS)
    if a is None or {a, b} == set(RELAY_DISPLAYS):
        long, short = (a, b) if a is not None else RELAY_DISPLAYS
        contrasts.extend((f"{t}/{long}", f"{t}/{short}") for t in RELAY_TIMINGS)
    if contrasts:
        return contrasts
    cells = {f"{t}/{d}" for t in RELAY_TIMINGS for d in RELAY_DISPLAYS}
    if {a, b} <= cells:
        return [(a, b)]
    raise ValueError("--by relay compares two timings, two displays, or two timing/display cells")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rundir")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test", choices=("sign", "mcnemar"))
    mode.add_argument("--noninferiority", action="store_true")
    parser.add_argument("--by", choices=("relay",), help="pair auto cells on each map, holding the other relay factor fixed")
    parser.add_argument("--a", help="reference speech rule, or a relay arm with --by relay")
    parser.add_argument("--b", help="comparison speech rule, or a relay arm with --by relay")
    parser.add_argument("--frameworks", default="CMAS,DMAS")
    parser.add_argument("--speech", choices=SPEECH_RULES)
    parser.add_argument("--margin", type=float, default=.10)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--outcome", choices=("strict", "change_respected"), default="strict",
                        help="default strict; change_respected compares maps with two eligible outcomes")
    args = parser.parse_args()
    try:
        out = local_path(args.rundir)
        test = args.test or ("mcnemar" if args.by else "sign")
        if not args.by and not args.noninferiority and (args.a not in SPEECH_RULES or args.b not in SPEECH_RULES):
            parser.error("--a and --b are required for speech comparisons and must be valid speech rules")
        if not args.by and not args.noninferiority and test == "sign":
            rows = read_episode_rows(out, require_model=False)
            report_pairs(assigned_episodes(out, rows), rows, args.a, args.b, args.outcome)
            return
        _, assigned, observed = read_run(out)
        missing = len(assigned.keys() - observed.keys())
        if missing:
            if not args.allow_partial:
                raise ValueError(f"{missing} unrecorded episodes; use --allow-partial for a partial analysis")
            print(f"WARNING: {missing} unrecorded episodes. Strict counts them as failures; change_respected drops NA pairs.")
        if args.noninferiority:
            if args.outcome != "strict":
                raise ValueError("Non-inferiority uses strict success")
            speech = args.speech or ("auto" if args.by else "choice")
            noninferiority(assigned, observed, [s.strip() for s in args.frameworks.split(",")], speech, args.margin)
        elif args.by == "relay":
            available = {"/".join(relay_cell(r)) for r in assigned.values() if r["speech"] == "auto"}
            contrasts = relay_contrasts(args.a, args.b)
            comparisons = [(a, b) for a, b in contrasts if {a, b} <= available]
            if not comparisons:
                raise ValueError("Paired analysis needs assignments to both requested auto relay cells")
            for a, b in comparisons:
                print(f"Relay cells (relay_timing/relay_display): {b} minus {a}")
                if test == "sign":
                    report_pairs(assigned, observed.values(), a, b, args.outcome, "relay")
                else:
                    mcnemar(assigned, observed, a, b, args.outcome, "relay")
        else:
            mcnemar(assigned, observed, args.a, args.b, args.outcome)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
