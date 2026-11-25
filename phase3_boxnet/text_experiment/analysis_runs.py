"""Read-only access to assigned episodes and matched map inputs."""
from collections import defaultdict

from relay import relay_cell
from storage import local_path, read_json
from summarize import TECHNICAL, assigned_episodes, read_episode_rows, run_settings


def read_run(directory):
    out = local_path(directory)
    rows = read_episode_rows(out)
    assigned = assigned_episodes(out, rows, include_manifest=True)
    return out, assigned, {r["episode_id"]: r for r in rows}


def strict(row):
    return int(bool(row and row["finished"] and row["strict_success"]
                    and row.get("success_failure") not in TECHNICAL))


def arm_value(item, field):
    return "/".join(relay_cell(item)) if field == "relay" else item[field]


def map_set_value(item):
    """Historical assignments predate map sets and are therefore legacy."""
    return item.get("map_set", "legacy")


def paired_maps(assigned, observed, arm_field, arms, *, speech=None):
    """Keep protocols separate. An assigned, unrecorded arm is present with value None."""
    groups = defaultdict(lambda: defaultdict(dict))
    hashes = {}
    split_auto = any(relay_cell(item) not in (("-", "-"), ("immediate", "persistent")) for item in assigned.values())
    for name, item in sorted(assigned.items()):
        arm = arm_value(item, arm_field)
        if arm not in arms or (speech is not None and item["speech"] != speech):
            continue
        group = item["size"], item["condition"], item["tell"] or "-", map_set_value(item)
        other = item["speech"] if arm_field == "framework" else item["framework"]
        if arm_field == "framework" and other == "auto" and split_auto:
            other += "/" + arm_value(item, "relay")
        slot = item["env_seed"]
        for field in ("env_sha256", "event_sha256", "speech_event_sha256"):
            value = item.get(field)
            if value is not None and hashes.setdefault((group, slot, field), value) != value:
                raise ValueError(f"Map inputs differ for {group}, slot {slot} ({field})")
        pair = groups[group, other][slot]
        if arm in pair:
            raise ValueError(f"Duplicate {arm} assignment for {group}, {other}, slot {slot}")
        pair[arm] = observed.get(name)
    return groups


def show(value, digits=6):
    return "NA" if value is None else f"{value:.{digits}f}"


def check_call_settings(call, record, path):
    # Some older/synthetic traces only identify the model at the episode boundary.
    if "model" in record and call.get("model", record["model"]) != record["model"]:
        raise ValueError(f"Mixed model in {path}")
    setting = record.get("reasoning_setting", "default")
    if call.get("reasoning_setting", setting) != setting:
        raise ValueError(f"Mixed reasoning_setting in {path}")


def recorded_calls(out, row):
    """Read the settled prefix represented by the atomic episode, even during resume."""
    folder = out / "episodes" / row["episode_id"] / "calls"
    calls = []
    remaining = row["api_calls"]
    for path in sorted(folder.glob("[0-9]*.json")):
        if not remaining and not row["finished"]:
            break
        call = read_json(path)
        if call["number"] != len(calls) + 1:
            raise ValueError(f"Nonconsecutive call files in {folder}")
        check_call_settings(call, row, path)
        attempts = call["attempts"]
        physical = sum(a["api_calls"] for a in attempts)
        if physical > remaining or call["status"] == "pending":
            if row["finished"] or physical < remaining:
                raise ValueError(f"Call trace disagrees with published episode: {path}")
            # A resumed final call may already have more attempts and a new reply.
            prefix, used = [], 0
            for attempt in attempts:
                if used == remaining:
                    break
                prefix.append(attempt)
                used += attempt["api_calls"]
            call = dict(call, attempts=prefix, response=None)
            for key in ("completion_tokens", "reasoning_tokens"):
                values = [a.get(key) for a in prefix]
                call[key] = sum(values) if None not in values else None
            physical = used
        calls.append(call)
        remaining -= physical
    if remaining:
        raise ValueError(f"Missing {remaining} published attempts in {folder}")
    return calls


USAGE = ("api_calls", "prompt_tokens", "completion_tokens", "reasoning_tokens", "cost_usd",
         "guard_cost_usd", "relay_calls", "lenient_rescues")


def episode_usage(out, name, row):
    if row is not None:
        # Older protocols had no relay stage. Missing metering fields are unknown.
        return {k: row.get(k, 0 if k == "relay_calls" else None) for k in USAGE}
    # A stopped process can leave settled call files before publishing episode.json.
    total = dict.fromkeys(USAGE, 0)
    paths = sorted((out / "episodes" / name / "calls").glob("[0-9]*.json"))
    if paths:
        settings = run_settings(out)
    for path in paths:
        call = read_json(path)
        check_call_settings(call, settings, path)
        if call["status"] == "pending":
            return dict.fromkeys(USAGE)
        for k in USAGE:
            if k == "relay_calls":
                value = call["api_calls"] if call.get("role") == "relay" else 0
            elif k == "lenient_rescues":
                value = int(bool(call.get("lenient_rescue")))
            else:
                value = call.get(k)
            total[k] = total[k] + value if None not in (total[k], value) else None
    return total
