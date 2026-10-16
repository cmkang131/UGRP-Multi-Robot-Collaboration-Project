"""Managed entry for the explicitly selected S3 door reservation workflow."""
import sys
from scripts.run_s3_host import main as run_host
from harness.zone_s3_door_yield import PROFILE


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a == '--door-yield' or a.startswith('--door-yield=') for a in args):
        raise ValueError('door workflow fixes --door-yield; use S3 host for off')
    return run_host(['--door-yield', PROFILE, *args])


if __name__ == '__main__':
    raise SystemExit(main())
