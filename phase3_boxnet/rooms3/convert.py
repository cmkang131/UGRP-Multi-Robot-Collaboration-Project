"""Convert one enrolled 1x3 seed to a portable MJCF, calibrated map and floor plan."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from rooms3 import maps
from rooms3.picture import draw


def export(seed, out, rules, colours, registry):
    scene = maps.convert(seed, rules, colours, registry=registry)
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    with tempfile.TemporaryDirectory(prefix=".rooms3-", dir=out.parent) as tmp:
        bundle = Path(tmp) / "bundle"
        bundle.mkdir()
        (bundle / "map.json").write_text(json.dumps(scene, indent=2, allow_nan=False) + "\n")
        # The frozen sign and overhead modules bind their map at import. Isolate
        # them so a caller can convert several different maps in one process.
        subprocess.run([sys.executable, "-B", "-m", "rooms3.scene", str(bundle)],
                       cwd=maps.ROOT, check=True)
        draw(scene, bundle / "map.png")
        bundle.rename(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True, help="fresh output directory")
    parser.add_argument("--registry", type=Path, default=maps.REGISTRY)
    parser.add_argument("--boxes-per-robot", default=maps.Rules.boxes_per_robot)
    parser.add_argument("--room-length", type=float, default=maps.Rules.room_length)
    parser.add_argument("--room-width", type=float, default=maps.Rules.room_width)
    parser.add_argument("--door-width", type=float, default=maps.Rules.door_width)
    parser.add_argument("--pad-capacity", type=int, default=maps.Rules.pad_capacity)
    parser.add_argument("--paint", action="append", default=[], metavar="SOURCE=red|blue",
                        help="override a BoxNet colour for boxes and targets together")
    args = parser.parse_args()
    colours = dict(maps.COLOURS)
    for arg in args.paint:
        source, sep, colour = arg.partition("=")
        if not sep or source not in colours or colour not in ("red", "blue"):
            parser.error("use --paint SOURCE=red or SOURCE=blue for a BoxNet colour")
        colours[source] = colour
    try:
        rules = maps.Rules(args.room_length, args.room_width, args.door_width,
                           args.pad_capacity, args.boxes_per_robot)
        export(args.seed, args.out, rules, colours, args.registry)
    except FileExistsError:
        parser.exit(2, f"Output directory already exists: {args.out}\n")
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"{error}\n")
    print(f"Exported seed {args.seed} to {args.out}")


if __name__ == "__main__":
    main()
