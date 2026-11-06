"""Candidate client: opt-in geometry predictor behind the PINNED SoloStudentClient.

WHY A NEW MODULE
----------------
``harness/solo_student_eval.py`` (the staged, pinned client) hard-codes two
things that block the geometry checkpoint:

1. the spawned module: ``-m scripts.pairact_solo_student_worker`` whose
   ``main()`` calls ``harness.pairact_r1.PairActActor.load`` -- a loader whose
   schema gate accepts ONLY ``ugrp.grasp_act.adapter.pairact_r1.v1`` and
   therefore refuses the 20k geometry checkpoint;
2. the child's hello is compared with ``==`` against exactly
   ``{'ready': True, 'mode': 'pairact_solo_student_eval_v1'}``.

The first is a LOADER choice, not a protocol choice: the four-op wire, the
allowlist, the controller, the barrier and the issued clock are identical in
both routes.  So this candidate changes the LOADER WIRING ONLY, and it does so
as an explicit opt-in that is OFF by default.

WHAT IS REUSED, UNCHANGED
-------------------------
* ``harness.solo_student_eval.SoloStudentClient`` -- the pinned JSON-lines
  transport (``_read`` / ``request`` / ``flush`` / ``close``), the pinned pipe
  setup, the pinned closed hello comparison;
* ``harness.solo_student_eval.SoloStudentEpisode`` -- the one-robot RESET
  payload the real worker accepts;
* ``harness.solo_student_eval.RearmingSync`` and the pinned permit factory;
* the child's own 4-op allowlist and controller (inside the child process).

THE FIXES THIS FILE NOW CARRIES (fix-v1 and fix-v2)
--------------------------------------------------
1. **ONE launch plan, actually consumed.**  The plan (argv / cwd / explicit
   environment) is built by the SINGLE stdlib-only builder
   ``prepare_only.build_launch_plan`` -- the very same function the
   prepare-only CLI prints.  ``_PlanSpawner`` is the adapter that actually
   calls ``Popen``: it checks that the PINNED client built exactly the
   ``argv_base`` the plan describes, then hands ``Popen`` the plan's full
   argv, cwd and EXPLICIT environment.  The client's own spawn record is kept
   so the caller can compare plan <-> real Popen arguments.
   Consequence: ``--predictor`` (geometry|synthetic) and ``--threads`` are now
   delivered, and the child no longer inherits the parent environment.

2. **Mandatory worker pin.**  ``PINNED_WORKER_SHA256`` below is an INDEPENDENT
   expected digest, embedded in the source.  It governs the production
   admission even when the caller passes no expected digest at all; a digest
   the caller computed from the file on disk is NOT an independent pin and is
   refused.  A substituted worker can only be started through the explicitly
   labelled ``admit='fixture'`` seam, which is recorded as ``fixture_seam`` and
   is NEVER reported as production-admitted.

3. **Owned cleanup.**  If the spawn, the hello handshake or the reset fails,
   the child THIS client created is cleaned up with a bounded ladder
   (stdin close -> wait -> terminate -> wait -> kill -> wait).  The original
   exception is re-raised unchanged; the cleanup record is attached to it as
   ``ugrp_cleanup``.  No unrelated process is touched.

4. **Runtime parent file pin.** Before any child is spawned, the file at
   the module's CLAIMED ``__file__`` path and the base class's reported file
   path are checked against independent embedded path/hash literals. This
   verifies those disk bytes, NOT the code loaded into the module object.
   In-process ``sys.modules`` pre-seeding with a forged pinned ``__file__``
   can pass; this check does not prevent that or authenticate loaded code.
   Evidence always records ``loaded_code_verified=False``.

5. **Spawn labelling.** ``spawn_is_injected`` describes the callable.
   ``child_is_popen_instance`` and legacy ``child_process_verified`` both
   mean ONLY ``isinstance(proc, subprocess.Popen)``. A wrapper can return a
   Popen for an unrelated program and still satisfy that type predicate.
   Neither field authenticates PID, executable, interpreter or loaded code.
   Admission proves file checks only; it does not prove the child ran.

THE ``entry`` SEAM IS USED DELIBERATELY (fix-v2, S4)
-----------------------------------------------------
The pinned client's own docstring calls ``entry`` a **TEST SEAM** ("``None``
... is the only value production uses") and describes a fixture that points
it at a launcher calling the same worker module's ``serve()`` with a
synthetic predictor.  This candidate uses that seam on purpose: the opt-in
geometry worker IS such a launcher -- it calls the PINNED worker's own
``serve()`` with the PINNED 4-op allowlist, the PINNED controller, the
PINNED barrier/executor and the PINNED contract, and it only replaces the
PREDICTOR SOURCE (the loader wiring).  The protocol, the allowlist, the
hello contract and the issued clock are unchanged.  The geometry child is
therefore a fixture-shaped launcher, NOT a new production wire; a production
deployment that refuses the seam must ship the geometry worker as the
default module instead.  This is recorded so no reader mistakes the seam
use for a protocol change.

WORKER BYTE CHANGE -> RE-PIN PROCEDURE (fix-v2, S5)
----------------------------------------------------
The embedded worker pin is fail-closed: changing ANY byte of
``solo_geometry_worker.py`` (including a docstring) makes the client refuse
to start.  The re-pin procedure is:
  1. compute the new sha256 of the changed worker file independently
     (``sha256sum``), do not copy a digest the candidate reports;
  2. review the diff of the worker bytes (what changed and why);
  3. update ``PINNED_WORKER_SHA256`` in this file and, if the changed file is
     a pinned upstream source, the matching entry in
     ``prepare_only.PINNED_SOURCES`` -- upstream pins are MANDATORY and are
     never edited by this candidate;
  4. re-run ``prepare_only.py`` (both predictor plans) and
     ``run_client_check.py``; the embedded pin must equal the file digest
     again, and the coordinator/Verify re-runs the independent checks.

THE OPT-IN GATE
---------------
``SoloGeometryStudentClient`` is a DISTINCT class, so the default path
(``SoloStudentClient``) is untouched and still starts the original
``PairActActor`` worker.  On top of that, the subclass refuses to start unless
the caller passes ``opt_in='geometry_predictor_v1'`` EXPLICITLY.

The closed hello is NOT widened: the child prints exactly
``{'ready': True, 'mode': 'pairact_solo_student_eval_v1'}`` and the inherited
``==`` comparison is kept verbatim.  Geometry diagnostics travel on the child's
stderr, never on stdout, so they cannot be mistaken for protocol fields.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

from harness.solo_student_eval import SoloStudentClient, SoloStudentEpisode

#: The child's program.  It is a CANDIDATE file: it lives in this candidate
#: directory and is spawned by absolute path.
CANDIDATE_ROOT = Path(__file__).resolve().parent
GEOMETRY_WORKER = CANDIDATE_ROOT / 'solo_geometry_worker.py'

#: The exact opt-in token.  Anything else is refused.
OPT_IN_TOKEN = 'geometry_predictor_v1'

#: The closed hello contract, restated for the caller's assertions only.  The
#: inherited client compares the child's hello with ``==`` against its own
#: literal; this constant must stay identical to it.
EXPECTED_HELLO = {'ready': True, 'mode': 'pairact_solo_student_eval_v1'}

#: INDEPENDENT expected digest of the candidate child program.  It is a
#: literal in this source: it is NOT computed from the file at runtime, so it
#: stays an independent pin even when the caller supplies no expected digest.
#: A caller-supplied digest of the file on disk is NOT an independent pin and
#: is refused in production admission.
PINNED_WORKER_SHA256 = '26bf7efb7a5fcb7d333240d172b0546d94059d1ac18940698285e96bb0195484'

#: INDEPENDENT pin of the PARENT side: the pinned client this candidate
#: inherits from (``harness.solo_student_eval`` -- the JSON-lines transport,
#: the closed hello comparison and the permit factory).  Its ORIGIN and its
#: BYTES are checked at runtime, before any child is spawned, because the
#: prepare-only plan is NOT consumed as an admission gate by this class
#: (fix-v2, S1): "the pinned client is reused unchanged" has to be enforced
#: here, not assumed.
PINNED_PARENT_CLIENT_PATH = ('/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1'
                              '/candidate/staging/harness/solo_student_eval.py')
PINNED_PARENT_CLIENT_SHA256 = '79a480854d4d52b6f09b796cac9d79360b3721e095e509f900589886c715edb7'

#: The admission modes.
ADMIT_PRODUCTION = 'production'
ADMIT_FIXTURE = 'fixture'

#: Bounded cleanup ladder timings (seconds).
CLEANUP_WAIT_TIMEOUT_S = 10.0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_launch_plan_builder():
    """Load the SINGLE stdlib-only launch-plan builder.

    It lives in ``prepare_only.py`` (no fifth file is needed) and is loaded by
    path so this module does not depend on the candidate directory being on
    ``sys.path``.
    """
    path = CANDIDATE_ROOT / 'prepare_only.py'
    spec = importlib.util.spec_from_file_location('ugrp_solo_prepare_only', path)
    if spec is None or spec.loader is None:
        raise ImportError('cannot load the launch plan builder: ' + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_launch_plan


BUILD_LAUNCH_PLAN = _load_launch_plan_builder()


def bounded_cleanup(proc, *, reason: str) -> dict:
    """Bounded, OWNED cleanup of ONE child process.

    Ladder: stdin close -> wait -> terminate -> wait -> kill -> wait.  Only
    the process handed in is touched; nothing else is signalled.  The record
    of what was actually done is returned (and attached to the exception by
    the callers).
    """
    record = {'reason': reason, 'stdin_closed': False, 'wait_calls': 0,
              'terminate_calls': 0, 'kill_calls': 0, 'exit_code': None,
              'errors': []}
    if proc is None:
        return record
    try:
        if proc.poll() is None:
            stdin = getattr(proc, 'stdin', None)
            if stdin is not None:
                try:
                    stdin.close()
                except Exception as error:            # noqa: BLE001 - recorded verbatim
                    record['errors'].append('stdin close: ' + repr(error))
                record['stdin_closed'] = True

            def wait_once():
                record['wait_calls'] += 1
                try:
                    proc.wait(timeout=CLEANUP_WAIT_TIMEOUT_S)
                    return True
                except subprocess.TimeoutExpired:
                    return False

            if not wait_once():
                try:
                    proc.terminate()
                    record['terminate_calls'] += 1
                except Exception as error:            # noqa: BLE001 - recorded verbatim
                    record['errors'].append('terminate: ' + repr(error))
                if not wait_once():
                    try:
                        proc.kill()
                        record['kill_calls'] += 1
                    except Exception as error:        # noqa: BLE001 - recorded verbatim
                        record['errors'].append('kill: ' + repr(error))
                    if not wait_once():
                        record['errors'].append('child still alive after kill')
        record['exit_code'] = proc.poll()
    except Exception as error:                        # noqa: BLE001 - recorded verbatim
        record['errors'].append('cleanup: ' + repr(error))
    return record


def admit_worker(worker: Path, expect_sha256, admit: str) -> dict:
    """Decide whether this worker program may be started, and with which pin.

    ``production``  the worker path must be the pinned candidate child and the
                    INDEPENDENT embedded digest governs, whether or not the
                    caller passed an expected digest.  A caller-provided
                    digest that differs from the embedded pin is refused.
    ``fixture``     an explicitly labelled test seam: the caller must supply
                    the expected digest.  The result is reported as
                    ``fixture_seam`` and is NEVER production-admitted.
    """
    if admit not in (ADMIT_PRODUCTION, ADMIT_FIXTURE):
        raise ValueError(f'unknown admission mode {admit!r} '
                         f'(expected {ADMIT_PRODUCTION!r} or {ADMIT_FIXTURE!r})')
    digest = sha256_file(worker)
    if admit == ADMIT_PRODUCTION:
        if expect_sha256 is not None and expect_sha256 != PINNED_WORKER_SHA256:
            raise ValueError('a caller-provided digest is not an independent pin: '
                             f'{expect_sha256} != {PINNED_WORKER_SHA256}')
        if Path(worker).resolve() != GEOMETRY_WORKER.resolve():
            raise ValueError('production admission requires the pinned candidate worker '
                             f'({GEOMETRY_WORKER}), not {worker}')
        expected, source = PINNED_WORKER_SHA256, 'embedded_literal'
    else:
        if expect_sha256 is None:
            raise ValueError('fixture admission requires an explicit expected digest')
        expected, source = expect_sha256, 'caller_supplied_fixture'
    if digest != expected:
        raise ValueError(f'geometry worker sha256 mismatch: {digest} != {expected}')
    return {
        'admission': ADMIT_PRODUCTION if admit == ADMIT_PRODUCTION else 'fixture_seam',
        'production_admitted': admit == ADMIT_PRODUCTION,
        'worker': str(worker),
        'worker_sha256': digest,
        'expected_worker_sha256': expected,
        'expected_worker_sha256_source': source,
        'independent_pin': admit == ADMIT_PRODUCTION,
        'proves': 'the file bytes and origin of the worker program',
        'does_not_prove': 'that a real child process ran (the popen callable may be injected)',
    }


def verify_parent_module(module, *, expected_path: str, expected_sha256: str) -> dict:
    """Check the file at one module object's CLAIMED origin against a pin.

    This is the low-level checker.  It performs NO import and NO execution of
    the file it inspects: it only reads bytes that are already on disk.
    """
    origin = getattr(module, '__file__', None)
    if not origin:
        raise ValueError('the parent client module has no origin file')
    origin_path = Path(origin).resolve()
    expected = Path(expected_path).resolve()
    if not origin_path.is_file():
        raise ValueError(f'parent client module origin file is missing: {origin_path}')
    if origin_path != expected:
        raise ValueError('parent client module origin mismatch: '
                         f'{origin_path} != {expected}')
    digest = sha256_file(origin_path)
    if digest != expected_sha256:
        raise ValueError(f'parent client module sha256 mismatch: {digest} != {expected_sha256}')
    return {'module_origin': str(origin_path), 'module_origin_sha256': digest,
            'expected_path': str(expected), 'expected_sha256': expected_sha256,
            'verified': True, 'claimed_origin_file_verified': True,
            'loaded_code_verified': False}


def verify_parent_client() -> dict:
    """Check disk files at claimed parent/base paths before spawn.

    Independent literals verify the reported paths and disk bytes. They do
    not bind an in-memory module/class implementation to those bytes. A
    pre-seeded module with forged __file__ can pass; loaded code is never
    claimed verified by this function.
    """
    module = sys.modules.get('harness.solo_student_eval')
    if module is None:
        module = sys.modules.get(getattr(SoloStudentClient, '__module__', ''))
    if module is None:
        raise ValueError('the pinned parent client module is not loaded in this process')
    evidence = verify_parent_module(module, expected_path=PINNED_PARENT_CLIENT_PATH,
                                     expected_sha256=PINNED_PARENT_CLIENT_SHA256)
    # Check the base class reported source path; this is not loaded-code identity.
    base_file = Path(inspect.getfile(SoloStudentClient)).resolve()
    base_digest = sha256_file(base_file)
    if base_file != Path(evidence['module_origin']).resolve() or base_digest != PINNED_PARENT_CLIENT_SHA256:
        raise ValueError('the inherited parent client class is not the pinned one: '
                         f'{base_file} ({base_digest})')
    evidence.update({
        'base_class': f'{SoloStudentClient.__module__}.{SoloStudentClient.__name__}',
        'base_class_file': str(base_file),
        'base_class_sha256': base_digest,
        'independent_pin': True,
        'expected_source': 'embedded_literal',
        'scope': 'disk bytes at the claimed module/base origin paths only; '
                 'forged __file__ may pass; loaded code is not verified',
    })
    return evidence


class _PlanSpawner:
    """The adapter that ACTUALLY calls ``Popen`` with the launch plan.

    The PINNED client builds its own base argv; this adapter verifies that
    base against the plan and then hands ``Popen`` the plan's full argv, cwd
    and EXPLICIT environment.  Every call is recorded so the caller can
    compare the plan with what really happened.
    """

    def __init__(self, plan: dict, real_popen):
        self.plan = plan
        self.real_popen = real_popen
        #: A popen callable that is NOT the stdlib ``subprocess.Popen`` is an
        #: INJECTED spawn: the file admission still holds, but nothing about a
        #: real child process is proved (fix-v2, S3).
        self.spawn_is_injected = real_popen is not subprocess.Popen
        self.calls = []

    def __call__(self, cmd, **kwargs):
        base = list(cmd)
        if base != list(self.plan['argv_base']):
            raise ValueError('the pinned client built an argv that differs from the launch '
                             f'plan: {base!r} != {self.plan["argv_base"]!r}')
        kwargs.pop('env', None)
        cwd = kwargs.get('cwd')
        if cwd is not None and str(cwd) != str(self.plan['cwd']):
            raise ValueError(f'the pinned client used a cwd that differs from the launch plan: '
                             f'{cwd!r} != {self.plan["cwd"]!r}')
        argv = list(self.plan['argv'])
        kwargs['cwd'] = self.plan['cwd']
        kwargs['env'] = dict(self.plan['env'])
        proc = self.real_popen(argv, **kwargs)
        self.calls.append({'argv': list(argv), 'base_argv': base, 'cwd': kwargs['cwd'],
                           'env': dict(kwargs['env']), 'env_is_explicit': True,
                           'popen_kwargs': sorted(kwargs),
                           'spawn_is_injected': self.spawn_is_injected,
                           'child_process_verified': isinstance(proc, subprocess.Popen),
                           'child_is_popen_instance': isinstance(proc, subprocess.Popen),
                           'process_verification_scope': 'Popen instance type only; not PID, '
                                                         'executable, interpreter or code identity',
                           'admission_proves': 'file bytes and origin only',
                           'admission_does_not_prove': 'that a real child process ran '
                                                       '(the popen callable may be injected)'})
        return proc


class SoloGeometryStudentClient(SoloStudentClient):
    """The pinned client, pointed at the geometry-predictor child.

    Opt-in is required twice: the class itself is separate from the default
    client, AND ``opt_in`` must equal ``OPT_IN_TOKEN``.  The INDEPENDENT
    embedded pin of the child program is verified before the spawn, so a
    substituted child cannot be started through this class unnoticed.
    """

    def __init__(self, cfg, *, popen=subprocess.Popen, entry=None,
                 opt_in=None, worker=None, expect_sha256=None,
                 admit=ADMIT_PRODUCTION, predictor='geometry', threads=1):
        if opt_in != OPT_IN_TOKEN:
            raise ValueError('geometry student client requires explicit opt_in='
                             + repr(OPT_IN_TOKEN))
        worker_path = Path(worker) if worker is not None else GEOMETRY_WORKER
        if entry is not None and Path(entry).resolve() != worker_path.resolve():
            raise ValueError('entry seam conflicts with the geometry worker: '
                             f'{entry!r} != {str(worker_path)!r}')
        if not worker_path.is_file():
            raise ValueError('geometry worker program is missing: ' + str(worker_path))
        admission = admit_worker(worker_path, expect_sha256, admit)
        # The PARENT side is pinned independently as well: the prepare-only
        # plan is not consumed as an admission gate by this class, so the
        # files at the claimed parent/base paths are checked BEFORE
        # anything is spawned.  Refused before any Popen.
        parent = verify_parent_client()
        plan = BUILD_LAUNCH_PLAN(python=cfg['python'], source=cfg['source'],
                                 model=cfg['model'], config=cfg['config'],
                                 device=cfg['device'], threads=threads,
                                 predictor=predictor, worker=str(worker_path))
        spawner = _PlanSpawner(plan, popen)
        # The pinned client's __init__ builds the base argv from `entry` when
        # given, else from the pinned WORKER_MODULE.  Passing our own program
        # as `entry` keeps the pinned transport, the pinned hello comparison
        # and the pinned request loop untouched; only the spawn adapter
        # differs.
        try:
            super().__init__(cfg, popen=spawner, entry=str(worker_path))
        except BaseException as error:
            record = bounded_cleanup(getattr(self, 'proc', None), reason='startup_failure')
            try:
                error.ugrp_cleanup = record
            except Exception:                          # noqa: BLE001 - attribute is best effort
                pass
            raise
        if len(spawner.calls) != 1:
            record = bounded_cleanup(getattr(self, 'proc', None), reason='unexpected_spawn_count')
            raise RuntimeError('the launch plan was not consumed exactly once: ' + repr(record))
        spawn = spawner.calls[0]
        if (spawn['argv'] != plan['argv'] or spawn['cwd'] != plan['cwd']
                or spawn['env'] != plan['env']):
            record = bounded_cleanup(getattr(self, 'proc', None), reason='plan_mismatch')
            raise RuntimeError('the real spawn differs from the launch plan: ' + repr(spawn))
        self.plan = plan
        self.spawn_record = spawn
        self.parent_pin = parent
        self.spawn_is_injected = spawner.spawn_is_injected
        self.admission = admission['admission']
        self.production_admitted = admission['production_admitted']
        self.expected_worker_sha256 = admission['expected_worker_sha256']
        self.expected_worker_sha256_source = admission['expected_worker_sha256_source']
        self.worker_program = str(worker_path)
        self.worker_sha256 = admission['worker_sha256']
        self.last_cleanup = None

    def close(self):
        """Bounded cleanup of OUR child (the pinned close() semantics, bounded)."""
        record = bounded_cleanup(getattr(self, 'proc', None), reason='close')
        self.last_cleanup = record
        return record


def start_geometry(cfg, roles, episode_id, initial, *, seed, factory, client=None,
                   opt_in=None, worker=None, expect_sha256=None,
                   admit=ADMIT_PRODUCTION, predictor='geometry', threads=1):
    """Runner glue for the geometry child (same shape as the pinned ``start``).

    Uses the pinned ``RearmingSync`` and the pinned permit factory, so the
    READY -> GO -> ACK semantics and the permit-``False`` meaning are the
    pinned ones -- this candidate does not change either.

    If the RESET fails, the child this call started is cleaned up (bounded
    ladder) and the original exception is re-raised with the cleanup record
    attached as ``ugrp_cleanup``.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    delays = {r: (0. if k == 0 else float(rng.uniform(0, 1.5))) for k, r in enumerate(roles)}
    client = client or SoloGeometryStudentClient(cfg, opt_in=opt_in, worker=worker,
                                                  expect_sha256=expect_sha256, admit=admit,
                                                  predictor=predictor, threads=threads)
    robot_id = next(iter(roles))
    from harness.solo_student_eval import RearmingSync
    try:
        episode = SoloStudentEpisode(client, robot_id, episode_id, initial[robot_id],
                                     RearmingSync(roles, delays, factory))
    except BaseException as error:
        record = client.close()
        try:
            error.ugrp_cleanup = record
        except Exception:                              # noqa: BLE001 - attribute is best effort
            pass
        raise
    return episode, delays
