"""Reproduce review F checks in a worktree without physics or file mutations.

Adapted from independent review b13c9b97's review_303f/offline.py. Pass the
repository root followed by pytest selectors; --without-cv2 guards the optional
CI boundary, and --mutation rejected_owner restores E303-1 only in memory.
"""
import argparse
import importlib.util
import inspect
import os
from pathlib import Path
import sys
import textwrap

parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
parser.add_argument('--mutation')
parser.add_argument('--without-cv2', action='store_true')
args, selectors = parser.parse_known_args()
root = args.root.resolve()
os.chdir(root)
sys.path.insert(0, str(root))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[name] = '1'
for name in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
if args.without_cv2:
    sys.modules['cv2'] = None

if args.mutation:
    path = root / 'experiments/2026-09-30-e2e-p06-evidence/event_replay_mutations.py'
    spec = importlib.util.spec_from_file_location('submitted_mutations', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner, function, old, new, _ = module.MUTATIONS[args.mutation]
    source = inspect.getsource(function)
    assert source.count(old) == 1, 'Mutation location drifted'
    namespace = dict(function.__globals__)
    exec(compile(textwrap.dedent(source.replace(old, new)), '<review-303f mutation>', 'exec'), namespace)
    setattr(owner, function.__name__, namespace[function.__name__])
    if owner is module.contract and function.__name__ == 'verify_referee_derivations':
        module.study.verify_referee_derivations = namespace[function.__name__]
    print('MUTATION', args.mutation, 'ONLY SELECTORS', selectors, flush=True)

import pytest
raise SystemExit(pytest.main(['-q', *selectors]))
