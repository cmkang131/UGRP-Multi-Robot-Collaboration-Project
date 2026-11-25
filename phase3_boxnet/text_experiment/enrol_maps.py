"""Enrol missing Chen maps and verify the requested maps against the D0 reference."""
import argparse
import re
from collections import Counter

from board_sizes import ENROL_SIZES, LEGACY_SIZES as SIZE_NAMES, selection, validate_board
from env1_create import action_from_response, main_maps, saved_env
from map_sets import parse_map_set, saved_scaled_env
from map_events import STRATIFIED_SLOTS, event_path, map_assignment, speech_fields, stratified_set
from storage import ROOT, digest, read_json, write_json

def seed_selection(value):
    seeds = []
    for part in selection(value):
        match = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", part)
        if not match:
            raise ValueError(f"Expected a nonnegative seed or inclusive range: {part!r}")
        first = int(match[1])
        last = int(match[2]) if match[2] is not None else first
        if last < first:
            raise ValueError(f"Descending seed range: {part!r}")
        seeds.extend(range(first, last + 1))
    if len(seeds) != len(set(seeds)):
        raise ValueError("Environment indices must be distinct")
    return seeds


def speech_event(path, rows, cols, slot):
    original = event_path(path)
    event = read_json(original)
    if "wording" in event:
        return original
    companion = path.with_suffix(".speech.event.json")
    # Scaled registries carry their identity in their base event.  Do not turn
    # their speech companion into a misleading legacy-labelled sidecar.
    map_metadata = {key: event[key] for key in ("map_set", "boxes_per_robot", "box_count") if key in event}
    data = dict(event, source_event_sha256=digest(original.read_bytes()),
                map_set=map_metadata.pop("map_set", "legacy"), slot_seed=slot, skipped_seeds=[],
                **map_metadata, **speech_fields(event, rows, cols, slot))
    if not companion.exists():
        write_json(companion, data)
    elif read_json(companion) != data:
        raise ValueError(f"Changed legacy speech event: {companion}")
    return companion


def enrol(sizes, seeds, directory=ROOT / "envs", map_set=None):
    sizes = tuple(sizes)
    for size in sizes:
        validate_board(size, "legacy")
    if map_set in STRATIFIED_SLOTS:
        allowed = STRATIFIED_SLOTS[map_set]
        if any(set(seeds) - set(allowed.get(tuple(map(int, s.split("x"))), ())) for s in sizes):
            raise ValueError({"confirm": "Confirm slots are 200–327 on 2x4 and 200–231 on 2x2",
                              "main": "Main slots are 100–123 on 2x4 and 4x4",
                              "cause": "Cause slots are 328–351 on 2x4"}[map_set])
        print("size | slot | seed | skipped | stratum | M position | wording | A | D | step | boxes left | L")
    else:
        print("size | maps | reference boxes of A left >= 1 | D = [0.5, 0.5]")
    for size in sizes:
        rows, cols = map(int, size.split("x"))
        remaining = first_speaker = 0
        counts = Counter()
        for seed in seeds:
            enrolled = stratified_set(rows, cols, seed)
            if map_set is not None and (enrolled or "legacy") != map_set:
                raise ValueError(f"Map already belongs to another set: {size}, slot {seed}")
            path, sha = saved_env(rows, cols, seed, directory)
            assignment = read_json(event_path(path))
            reference = (main_maps(rows, cols, enrolled)[seed][1] if enrolled else
                         map_assignment(read_json(path), seed, sha, rows, cols, action_from_response))
            if assignment != reference or reference["reference_box_A_left"] < 1:
                raise ValueError(f"D0 reference verification failed for {path}")
            if map_set is not None:
                speech_event(path, rows, cols, seed)
            if map_set in STRATIFIED_SLOTS:
                counts[reference["stratum"], reference["wording"]] += 1
                print(" | ".join(map(str, (size, seed, reference["seed"], reference["skipped_seeds"],
                    reference["stratum"], reference["member_position"], reference["wording"], reference["A"],
                    reference["D"], reference["event_step"], reference["reference_box_A_left"], reference["L"]))))
            remaining += reference["reference_box_A_left"] >= 1
            first_speaker += reference["D"] == [0.5, 0.5]
        if map_set in ("confirm", "cause"):
            print("size | stratum | wording 1 | wording 2 | maps")
            for stratum in ("first_column", "other_columns"):
                one, two = counts[stratum, 1], counts[stratum, 2]
                print(f"{size} | {stratum} | {one} | {two} | {one + two}")
        elif map_set != "main":
            print(f"{size} | {len(seeds)} | {remaining} | {first_speaker}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", choices=("main", "legacy", "confirm", "cause"), dest="map_set")
    parser.add_argument("--map-set", dest="family", help="legacy or scaled:R, as in run_chen2d.py")
    parser.add_argument("--sizes")
    parser.add_argument("--boxes-per-robot", metavar="R",
                        help="opt in to isolated scaled:R maps; total boxes is round(R * robots)")
    parser.add_argument("--envs", required=True, help="seeds and inclusive ranges, e.g. 0-19")
    args = parser.parse_args()
    try:
        sizes = args.sizes or {"main": "2x4,4x4", "confirm": "2x4", "cause": "2x4"}.get(args.map_set, ",".join(SIZE_NAMES))
        selected_sizes, seeds = selection(sizes, ENROL_SIZES), seed_selection(args.envs)
        if args.family is not None and (args.boxes_per_robot is not None or args.map_set is not None):
            raise ValueError("Use --map-set on its own, or use --boxes-per-robot or --set")
        if args.boxes_per_robot is not None and args.map_set is not None:
            raise ValueError("--boxes-per-robot cannot be combined with --set")
        selected = parse_map_set(args.family if args.boxes_per_robot is None else "scaled:" + args.boxes_per_robot)
        if selected.boxes_per_robot is None:
            enrol(selected_sizes, seeds, map_set=args.map_set)
        else:
            print("size | seed | map set | boxes per robot | boxes | path")
            for size in selected_sizes:
                rows, cols = map(int, size.split("x"))
                for seed in seeds:
                    path, _, meta = saved_scaled_env(rows, cols, seed, selected)
                    print(f"{size} | {seed} | {meta['map_set']} | {meta['boxes_per_robot']} | {meta['box_count']} | {path}")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
