"""Audit the actual producing prompt for every executed post-event plan."""
import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from relay import HEADER, STATE_HEADERS, free_checks, relay_cell
from storage import read_json


DIALOGUE = re.compile(r"The previous dialogue history is: \{(.*?)\}\s*\n\s*Think step-by-step", re.S)
# A sender's address is metadata. Only the words (or plan) the sender contributed count.
SPEAKER = re.compile(r"^\s*\[?(?:Agent\[[^\]\n]+\]|Central Planner):\s*", re.M)
RELAY_LINE = re.compile(r"^\[Agent\[[^\]\n]+\], after step \d+\]: ", re.M)


@dataclass
class PlanStep:
    step: int
    executed: bool
    call: int | None
    source: str | None
    respected: bool | None
    detail: str


def dialogue_has_news(text, event):
    for contribution in SPEAKER.split(text):
        evidence = free_checks(contribution, event)
        if evidence["names_colour"] and evidence["names_destination"]:
            return True
    return False


def news_source(call, event):
    if call["step"] <= event["step"]:
        return "none"  # A retained pre-event proposal.
    users = [m["content"] for m in call["messages"] if m["role"] == "user"]
    if not users:
        raise ValueError("Plan-producing call has no user prompt")
    task = users[0]
    marker = STATE_HEADERS["central" if call["role"] == "central" else "local"]
    prefix, present, task_body = task.partition(marker)
    if not present:
        raise ValueError("Plan-producing call lacks its current-state heading")
    direct, relay, inbox = prefix.partition(HEADER)
    if direct.rstrip().endswith(event["announcement"]):
        return "direct"
    if relay and RELAY_LINE.search(inbox):
        return "relay"
    # The public rule, state, previous actions and output examples contain these same words.
    section = DIALOGUE.search(task_body)
    if section and dialogue_has_news(section[1], event):
        return "dialogue"
    for user in users[1:]:
        # HMAS-2 appends boilerplate including example coordinates after the local feedback.
        feedback = user.partition("\nThis is the feedback from local agents.")[0]
        feedback = feedback.partition("If your answer is empty dict")[0]
        if dialogue_has_news(feedback, event):
            return "dialogue"
    return "none"


def inspect_episode(folder, row):
    event = row.get("event") if row else None
    if not event:
        return []
    result, sources = [], {}
    for it in row["iterations"]:
        if it["step"] <= event["step"]:
            continue
        number = it.get("plan_maker_call")
        source = None
        if it["executed"] and number is not None:
            if number not in sources:
                path = folder / "calls" / f"{number:05d}.json"
                if not path.is_file():
                    raise ValueError(f"Missing plan-producing call: {path}")
                call = read_json(path)
                if call["number"] != number or call["step"] > it["step"] or call["role"] == "relay":
                    raise ValueError(f"Inconsistent plan attribution: {path}")
                sources[number] = news_source(call, event)
            source = sources[number]
        if "producer_news_source" in it:
            had_news = source != "none" if source is not None else None
            if (it["producer_news_source"], it["producer_had_news"]) != (source, had_news):
                raise ValueError(f"Stored producer news disagrees with the prompt at {folder}, step {it['step']}")
        if not it["executed"]:
            detail = "unexecuted"
        elif "plan_maker_call" not in it:
            detail = "attribution-unavailable"
        else:
            detail = source or "no-maker"
        result.append(PlanStep(it["step"], it["executed"], number, source, it.get("executed_plan_respected_change"), detail))
    return result


def boolean(value):
    return "NA" if value is None else "yes" if value else "no"


def print_cross_table(table, group_header):
    print(f"{group_header} | had news | respected yes | respected no | respected NA")
    for group, counts in sorted(table.items()):
        for had in ("yes", "no", "NA"):
            print(" | ".join((*group, had, *(str(counts[had, r]) for r in ("yes", "no", "NA")))))


def report(out, assigned, rows, *, by_relay=False):
    table = defaultdict(Counter)
    all_steps = defaultdict(Counter)
    by_relay = by_relay or any("relay_timing" in item for item in assigned.values())
    group_header = "framework | speech" + (" | relay_timing | relay_display" if by_relay else "")
    print(f"episode | {group_header} | first plan-maker news | iterations with news / post-event iterations | "
          "share | iterations without an attributable plan | first executed plan respected | step:call:source")
    for name, item in sorted(assigned.items()):
        group = item["framework"], item["speech"]
        if by_relay:
            group += relay_cell(item)
        steps = inspect_episode(out / "episodes" / name, rows.get(name))
        first = next((step for step in steps if step.executed), None)
        source, respected = (first.source, first.respected) if first else (None, None)
        hits = sum(s.source in ("direct", "relay", "dialogue") for s in steps)
        unknown = sum(s.source is None for s in steps)
        trace = ", ".join(f"{s.step}:{s.call or '-'}:{s.detail}" for s in steps)
        fraction = f"{hits / len(steps):.6f}" if steps else "NA"
        print(" | ".join((name, *group, source or "NA", f"{hits}/{len(steps)}", fraction, str(unknown),
                          boolean(respected), trace or "—")))
        table[group][boolean(None if source is None else source != "none"), boolean(respected)] += 1
        if by_relay:
            counts = all_steps[group]
            for step in steps:
                if step.executed:
                    counts[boolean(None if step.source is None else step.source != "none"), boolean(step.respected)] += 1
    print("First executed plan: news in its producing prompt x respected change (episode counts).")
    print_cross_table(table, group_header)
    if by_relay:
        print("All executed post-event plans: producer had news x plan respected (iteration counts).")
        print_cross_table(all_steps, group_header)


def main():
    from analysis_runs import read_run

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rundir")
    parser.add_argument("--by", choices=("relay",), help="split the tables by relay timing and display")
    args = parser.parse_args()
    try:
        report(*read_run(args.rundir), by_relay=args.by == "relay")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
