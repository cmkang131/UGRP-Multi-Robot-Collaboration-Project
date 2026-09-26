"""No-LLM 3-robot smoke v3 of the own-camera executor: the v2 runner (``run_smoke_v2.py``, unchanged) with the
v3 pre-registration and the v3 runtime file list. Same frozen scenario as v1/v2.

Usage (from the worktree root):
    python experiments/2026-09-26-zone-own-executor/run_smoke_v3.py --episode smoke-v3-s700 --output <dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_smoke_v2 as v2  # noqa: E402

v2.SCHEMA = 'ugrp.zone_own_executor_smoke.v3'
v2.RUNTIME_FILES = v2.RUNTIME_FILES + ('harness/zone_own_driver.py',
                                       'experiments/2026-09-26-zone-own-executor/run_smoke_v3.py',
                                       'experiments/2026-09-26-zone-own-executor/prereg_v3.json')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--prereg' not in argv:
        argv += ['--prereg', str(HERE / 'prereg_v3.json')]
    return v2.main(argv)


if __name__ == '__main__':
    main()
