#!/usr/bin/env python3
"""Launch entry for the audited pair worker (owned candidate, same-tree bundle).

Why this file exists
--------------------
``harness/pair_worker_audit.py`` exposes the function ``owned_worker_main``
but has **no** ``__main__`` block: ``python -m harness.pair_worker_audit``
would import the module and exit without running anything.  This entry calls
``owned_worker_main`` explicitly, so the outer runner can launch it as a real
process and speak the frozen four-operation protocol to it.

Startup verification (the reason this entry exists in this form)
----------------------------------------------------------------
The producer side must not be able to announce readiness on an unverified
bundle.  Before ANY output, before the head worker is imported or started and
before the audit file is created, this entry:

* requires the whole audited option set (``--audit-run-id``,
  ``--audit-output-root`` **and** ``--audit-sources``);
* requires ``--student-root`` to be the bundle root of this very file;
* requires ``--geometry-worker`` to be the pinned geometry worker, and, when
  they are given, ``--headworker`` and ``--config`` to be the pinned ones;
* loads the manifest and refuses it when it is empty, incomplete, missing a
  required path, or when any bound file does not hash as recorded;
* checks every required path against the **independent expected hashes**
  (the pin tables of ``harness/pair_worker_bundle.py`` and the two candidate
  hashes below) -- a manifest that only agrees with itself is refused;
* checks the ORIGINAL pinned tree files themselves, so a copy of a wrong
  source is refused;
* checks that this entry, the audit module and the bundle helper are the
  expected candidate bytes.

Any failure prints one line on stderr and exits non-zero: **no ``ready`` line,
no head worker, no audit file**.

Placement
---------
The entry is copied into the **same** harness package as the pinned
controller, so the audit module and the audited controller share one harness
tree (``harness.pair_worker_audit.check_same_tree``).  The bundle root is the
parent of this file's directory.

Verification-only modes
-----------------------
``--synthetic-predictor`` replaces the learned head by a FIXED SYNTHETIC
predictor (constant chunk, constant stage plan).  It exists so that the boot
entry itself can be exercised on CPU without a model, a simulator, a GPU or a
head-worker process.  ``--synthetic-done`` additionally makes the synthetic
chunk carry the completion flag, which drives the pinned release/finish
sequence of the controller.  These modes are for verification only and must
never be used for a real run.

The stdout protocol is unchanged: ``{"ready": true, "mode": ...}`` followed by
one JSON line per four-operation request.  No audit metadata is added to a
response.
"""
from __future__ import annotations

from pathlib import Path
import sys

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent                      # the bundle root (parent of harness/)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from harness.pair_worker_audit import owned_worker_main, _owned_parser  # noqa: E402

try:                                     # the helper travels with the bundle
    from harness import pair_worker_bundle as bundle
except ImportError:                      # pragma: no cover - fail closed later
    bundle = None

# Independent expected hashes of the candidate files that travel with the
# bundle.  They are NOT read from the manifest: a manifest that only agrees
# with itself must not be able to declare a wrong source good.
EXPECTED_HELPER_SHA = ('caed034bca1006b0244bfc5ac951085b75cbf98b772ab8935af3657'
                       '94bec9fa4')
EXPECTED_AUDIT_MODULE_SHA = ('77c862a02bff3e848706a2e0735c9ce16fed085907219784'
                             '116bc4a12b9a5e52')

AUDIT_OPTIONS = ('--audit-run-id', '--audit-output-root', '--audit-sources')

STAGE_INDEX = ('approach', 'alignment', 'ready', 'execute',
               'carry', 'place', 'recover', 'complete')
FIRST_STAGE_PLAN = ('approach', 'approach', 'ready', 'ready',
                    'execute', 'execute', 'carry', 'carry')
LATER_STAGE_PLAN = ('execute',) * 8


class StartupRefused(RuntimeError):
    """The audited entry refuses to start on an unverified bundle."""


def _same_path(value, expected):
    try:
        return Path(value).resolve() == Path(expected).resolve()
    except OSError:
        return False


def expected_startup_hashes(root):
    """{path: sha256} every audited start-up must find, independently."""
    if bundle is None:
        raise StartupRefused('the bundle helper is not available in this tree')
    expected = dict(bundle.expected_bundle_paths(root))
    expected[str(Path(root) / 'harness' / 'pair_worker_audit.py')] = \
        EXPECTED_AUDIT_MODULE_SHA
    expected[str(Path(root) / 'harness' / 'pair_worker_bundle.py')] = \
        EXPECTED_HELPER_SHA
    expected.update(bundle.EXPECTED_EXTERNAL_SHAS)
    return expected


def verify_startup(argv, *, predictor_injected=False, parsed_args=None):
    """Verify the prepared bundle.  Raises StartupRefused on any problem."""
    if bundle is None:
        raise StartupRefused('the bundle helper is not available in this tree')
    args = parsed_args if parsed_args is not None else _owned_parser().parse_args(argv)
    root = Path(_ROOT).resolve()
    student_root = args.student_root
    if student_root is None or not _same_path(student_root, root):
        raise StartupRefused('--student-root must be the bundle root of this entry')
    geometry_worker = args.geometry_worker
    if geometry_worker is None or not _same_path(geometry_worker, bundle.GEOMETRY_WORKER):
        raise StartupRefused('--geometry-worker must be the pinned geometry worker')
    headworker = args.headworker
    if headworker is not None and not _same_path(headworker, bundle.HEAD_WORKER):
        raise StartupRefused('--headworker must be the pinned head worker')
    config = args.config
    if config is not None and not _same_path(config, bundle.CONFIG):
        raise StartupRefused('--config must be the pinned train config')
    if not predictor_injected:
        if headworker is None:
            raise StartupRefused('--headworker is required for a real head run')
        if config is None:
            raise StartupRefused('--config is required for a real head run')
    manifest_path = args.audit_sources
    if manifest_path is None:
        raise StartupRefused('--audit-sources is required for an audited start')
    expected = expected_startup_hashes(root)
    required = set(expected) | {str(Path(__file__).resolve())}
    bundle.verify_startup(manifest_path, expected=expected, required=required,
                          expected_sources=bundle.expected_source_paths())
    return manifest_path


def synthetic_predict_factory(done=False):
    """A fixed synthetic predictor (no learned weights, no inference).

    The stage plan is counted PER ROBOT so that the two robots follow the
    same deterministic sequence.
    """
    state = {'calls': {}}

    def predict(observation, jpegs):
        import numpy as np
        robot_id = observation['robot_id']
        index = state['calls'].get(robot_id, 0)
        state['calls'][robot_id] = index + 1
        plan = FIRST_STAGE_PLAN if index == 0 else LATER_STAGE_PLAN
        chunk = np.zeros((8, 14), dtype=float)
        chunk[:, 0:4] = 0.35          # wheels
        chunk[:, 4:8] = 1.0           # pulse widths -> 150 ms
        chunk[:, 8:13] = 0.0          # pwm offsets -> 1500
        # The completion flag appears only after the FIRST prediction: the
        # pinned controller then walks approach -> READY -> GO/ACK -> execute
        # before the completion flag can start the pinned release sequence.
        chunk[:, 13] = 1.0 if (done and index >= 1) else 0.0
        logits = np.zeros((8, 8), dtype=float)
        for row, stage in enumerate(plan):
            logits[row, STAGE_INDEX.index(stage)] = 1.0
        return {'chunk': chunk, 'stage_logits': logits}

    return predict


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    predict = None
    if '--synthetic-predictor' in argv:
        argv.remove('--synthetic-predictor')
        done = False
        if '--synthetic-done' in argv:
            argv.remove('--synthetic-done')
            done = True
        predict = synthetic_predict_factory(done)
    # Use the worker's parser: duplicate options use the same last value, and
    # --name=value / accepted abbreviations cannot evade startup verification.
    parsed = _owned_parser().parse_args(argv)
    present = [name for name in AUDIT_OPTIONS
               if getattr(parsed, name[2:].replace('-', '_')) is not None]
    if present:
        missing = [name for name in AUDIT_OPTIONS if name not in present]
        if missing:
            print('audited start refused: missing %s' % ', '.join(missing),
                  file=sys.stderr)
            return 2
        try:
            verify_startup(argv, predictor_injected=predict is not None,
                           parsed_args=parsed)
        except Exception as exc:                 # noqa: BLE001 - fail closed
            print('audited start refused: %s' % exc, file=sys.stderr)
            return 2
    try:
        result = owned_worker_main(argv, predict=predict)
    except Exception as exc:                     # noqa: BLE001 - fail closed
        print('worker start failed: %s' % exc, file=sys.stderr)
        return 1
    return result or 0


if __name__ == '__main__':
    sys.exit(main())
