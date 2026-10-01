"""Managed v90 held-out unloaded collection; plan-only unless --execute."""
import sys

from scripts.run_final_pair_v3 import main as run


def main(argv=None):
    return run(argv, heldout_only=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
