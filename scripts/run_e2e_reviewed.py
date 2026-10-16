"""Explicit current E2E workflow adapter; legacy runner defaults stay unchanged."""
import sys
from scripts import run_e2e_ownmap_live as runner
from harness.e2e_runtime_registration import OPTION


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a == '--runtime-registration' or a.startswith('--runtime-registration=') for a in args):
        raise ValueError('WORKFLOW_OWNS_RUNTIME_REGISTRATION')
    return runner.main([*args, '--runtime-registration', OPTION])


if __name__ == '__main__':
    raise SystemExit(main())
