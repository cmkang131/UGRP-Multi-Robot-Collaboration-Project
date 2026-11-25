"""Board catalogs and selection rules shared by the Chen command-line tools."""

LEGACY_GRIDS = ((2, 2), (2, 4), (4, 4), (4, 8))
LEGACY_SIZES = tuple(f"{rows}x{cols}" for rows, cols in LEGACY_GRIDS)
SCALED_ONLY_SIZES = ("1x3", "2x3", "3x3")
ENROL_SIZES = (*LEGACY_SIZES, *SCALED_ONLY_SIZES)
MATCHED_SIZES = (*LEGACY_SIZES, "2x8", "4x6", "6x6", "8x8", *SCALED_ONLY_SIZES)


def selection(value, allowed=None):
    items = [s.strip() for s in value.split(",")]
    if not all(items) or len(set(items)) != len(items) or (allowed and set(items) - set(allowed)):
        raise ValueError(f"Invalid selection {value!r}. Choices: {allowed}")
    return items


def size_filter(value):
    """An omitted analysis selector includes all sizes in the recorded input."""
    return None if value is None else selection(value, MATCHED_SIZES)


def validate_board(size, map_set, protocol=None, conditions=()):
    if size not in SCALED_ONLY_SIZES:
        return
    if not (map_set or "").startswith("scaled:"):
        raise ValueError(f"{size} has no legacy maps (--map-set legacy). Use --map-set scaled:R "
                         "or enrol_maps.py --boxes-per-robot R.")
    if protocol is not None and protocol != "matched":
        raise ValueError(f"{size} requires --protocol matched.")
    if any(condition != "static" for condition in conditions):
        raise ValueError(f"{size} supports --conditions static only. Changed-order event placement "
                         "is not guaranteed on these scaled boards.")
