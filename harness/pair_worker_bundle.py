"""Same-tree bundle for the audited pair worker (owned placement helper).

Scope (2026-11-05, UGRP-Pair, branch ugrp/pair-runner-wire-20261105T2017Z)
-----------------------------------------------------------------------
This module places the opt-in audit module, its launch entry and ITSELF into
the same harness tree as the pinned controller, so that
``harness.pair_worker_audit.check_same_tree`` can hold: the audited
``harness/pairact_r1_student.py`` and the audit module must live in one
``harness`` package directory.

Rules enforced here:

* The bundle root is created **exclusively**.  An existing destination is
  refused; nothing is deleted and nothing is overwritten.
* The pinned worker tree (``harness`` + ``scripts``) is copied **byte for
  byte**; EVERY copied file is re-hashed against its source at creation time.
  The **manifest**, in contrast, pins only the required subset, the candidate
  files and the read-only originals (see ``REQUIRED_TREE_FILES`` and
  ``bundle-info.json:protected_scope`` / ``unprotected_scope``).
* The manifest binds the copied controller / contract / pairact sources, the
  ORIGINAL geometry worker, the head sources, the config, the ASTRA outer
  loop and the candidate files to their sha256.  It is verified **before** any
  worker is started AND again by the entry at startup.  An empty or
  incomplete manifest is an error, never a "verified pin".
* The expected hashes live here as **independent constants**: a manifest that
  only agrees with itself is NOT accepted.
* The same-tree claim is checked with the **real import** of the bundle's
  ``harness.pair_worker_audit``, ``harness.pairact_r1_student`` and
  ``harness.grasp_act_contract`` in an isolated subprocess, using their
  ``__file__`` paths, and those files must live in the REQUESTED bundle root.

This module deliberately imports nothing from the ``harness`` package: the
outer runner loads it by path so that it can never shadow the pinned
``harness`` namespace of the physics closure.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

SCHEMA = 'ugrp.pair_worker_bundle.v1'

# ---------------------------------------------------------------- pinned paths
PINNED_TREE = ("/home/ubuntu/UGRP/experiments/2026-11-04-joint-act-4tree-"
                "assembly-diag-v1/out/trees/worker")
GEOMETRY_WORKER = ("/home/ubuntu/ugrp-retrain-geom-20261029/received/final/"
                    "extracted/scripts/geometry_pair_worker.py")
HEAD_WORKER = ("/home/ubuntu/ugrp-retrain-geom-20261029/implementation/"
                "geometry_worker.py")
HEAD_POLICY = ("/home/ubuntu/ugrp-retrain-geom-20261029/implementation/"
                "geometry_policy.py")
CONFIG = ("/home/ubuntu/ugrp-wt/codex-pair-fix-cpu-20261027/experiments"
          "/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json")
ASTRA = ("/home/ubuntu/UGRP/experiments/2026-11-04-astra-strict-eval-v1"
         "/snapshot/harness/pairact_student_eval.py")

# The files of the pinned worker tree that the audited pair path needs.  The
# manifest MUST bind all of them; the rest of the copied tree is byte
# compared at creation time but is not a pin.
REQUIRED_TREE_FILES = (
    'harness/__init__.py',
    'harness/grasp_act_contract.py',
    'harness/pairact_r1.py',
    'harness/pairact_r1_student.py',
    'harness/beamact_pair_student.py',
    'harness/grasp_act_policy.py',
    'scripts/robot_actions.py',
)

# The candidate files that are placed next to the pinned controller.  The
# bundle helper itself must travel with them: the entry verifies the startup
# with it, so the helper has to be in the same tree.
CANDIDATE_TREE_FILES = (
    'harness/pair_worker_audit.py',
    'harness/pair_worker_audit_entry.py',
    'harness/pair_worker_bundle.py',
)

# ---------------------------------------------------------------- pin tables
# Independent expected hashes.  They are NOT read from the manifest: a
# manifest that agrees with itself but points at the wrong source is refused.
EXPECTED_TREE_SHAS = {
    'harness/__init__.py': '953d3229d4ed66dc30e1ddeab38440397fc01303fcd022fb147d45d4345abdcf',
    'harness/grasp_act_contract.py': '6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d66d171056',
    'harness/pairact_r1.py': '8a9869248740bf5ad2da7194cdd9a582347ac09e88783cd6ea127ef3f208a210',
    'harness/pairact_r1_student.py': '3e12d2f5408f82821187401e8a6d4298cb70fb27b48c229d689a54efdef77e81',
    'harness/beamact_pair_student.py': '9650e08573adf61e622a2e832a7ca12f476d4e5988f9bbc299bb125a766ee1c6',
    'harness/grasp_act_policy.py': '0cfa080f086ea991368e3c686960cf54cab9a8f9796e1077557f17a639f79c6c',
    'scripts/robot_actions.py': 'fffb0c4d351294275c9dab497feb201fb045a05939e51ff892c2027af54ba96c',
}

EXPECTED_EXTERNAL_SHAS = {
    GEOMETRY_WORKER: 'c7509a6423b252d4941b68ecfa3ce2ffc75783c4f3cd1f3aac2fe467b9d601bc',
    HEAD_WORKER: 'e9a29e81fdc1b3b0faa760bd89533953ea49c23eb325f48c5c7f01aec042e90c',
    HEAD_POLICY: '3681da67642f681615b42673ae004690d2341d62b99c3c6caeae647c8851788f',
    CONFIG: '37835e1ff9bd7b9686b4d7258b7597e6cd8e40b84a121c4f4156704c04b49326',
    ASTRA: '03f6a2311c0d4f4a97495fdce5efe7d345a35fa2815c9c5ab3660223818efbec',
}

IGNORED = shutil.ignore_patterns('__pycache__', '*.pyc')


class BundleError(RuntimeError):
    """Raised when the bundle cannot be trusted; the run must stop."""


def sha256_file(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def harness_dir(path):
    """The harness package directory of a module file, or None."""
    parent = Path(path).resolve().parent
    return parent if parent.name == 'harness' else None


def check_same_tree(audit_file, audited_file):
    """Refuse to audit code that lives in another harness tree."""
    mine = harness_dir(audit_file)
    theirs = harness_dir(audited_file)
    if mine is None or theirs is None:
        raise BundleError('audit module and audited code must live in a harness package')
    if mine != theirs:
        raise BundleError('harness tree mixing refused: %s vs %s' % (mine, theirs))
    return True


def expected_bundle_paths(bundle_root):
    """{bundle path: sha} for the pinned subset inside the bundle."""
    root = Path(bundle_root).resolve()
    return {str(root / relative): sha
            for relative, sha in EXPECTED_TREE_SHAS.items()}


def expected_source_paths(tree_root=None):
    """{original pinned path: sha} for the pinned tree files themselves."""
    root = Path(tree_root or PINNED_TREE).resolve()
    return {str(root / relative): sha
            for relative, sha in EXPECTED_TREE_SHAS.items()}


def _copy_tree(source, destination):
    shutil.copytree(source, destination, ignore=IGNORED)


def _compare_closure(pinned, root):
    """Re-hash EVERY copied file against its source.  Returns the count."""
    compared = 0
    for sub in ('harness', 'scripts'):
        for source in sorted((pinned / sub).rglob('*')):
            if source.is_dir() or '__pycache__' in source.parts:
                continue
            relative = source.relative_to(pinned)
            target = root / relative
            if not target.is_file():
                raise BundleError('copy is missing: %s' % relative)
            if sha256_file(source) != sha256_file(target):
                raise BundleError('byte copy mismatch: %s' % relative)
            compared += 1
    return compared


def create_bundle(*, dest, pinned_tree, candidates, externals=()):
    """Create the bundle tree exclusively and write its manifest.

    ``candidates``  -- absolute paths of the candidate files to place in the
                      bundle's ``harness`` directory (the audit module, the
                      launch entry and this helper).
    ``externals``   -- absolute paths of read-only originals (the geometry
                      worker, the head sources, the config, the ASTRA outer
                      loop) that the manifest must also bind.

    Returns a dict with the bundle root, the manifest path, the manifest and
    the bundle info.
    """
    root = Path(dest).resolve()
    if root.exists():
        raise BundleError('bundle root must not exist (exclusive path): %s' % root)
    pinned = Path(pinned_tree).resolve()
    if not (pinned / 'harness').is_dir() or not (pinned / 'scripts').is_dir():
        raise BundleError('pinned worker tree is incomplete: %s' % pinned)
    root.mkdir(parents=True, exist_ok=False)

    _copy_tree(pinned / 'harness', root / 'harness')
    _copy_tree(pinned / 'scripts', root / 'scripts')
    compared = _compare_closure(pinned, root)

    entries = {}

    def record(path, role, source_path=None):
        path = Path(path).resolve()
        if not path.is_file():
            raise BundleError('bundle file is missing: %s' % path)
        digest = sha256_file(path)
        entry = {'path': str(path), 'sha256': digest, 'role': role}
        if source_path is not None:
            entry['source_path'] = str(Path(source_path).resolve())
        entries[str(path)] = entry
        return digest

    # The copied pinned sources: the required subset is pinned by the
    # manifest, the whole closure was byte compared above.
    for relative in REQUIRED_TREE_FILES:
        source = pinned / relative
        target = root / relative
        if not source.is_file():
            raise BundleError('pinned source is missing: %s' % source)
        record(target, 'pinned_tree_copy', source)

    # The candidate module, the launch entry and this helper, placed into the
    # SAME harness package.
    for candidate in candidates:
        source = Path(candidate).resolve()
        if not source.is_file():
            raise BundleError('candidate file is missing: %s' % source)
        target = root / 'harness' / source.name
        if target.exists():
            raise BundleError('candidate file would overwrite a copied file: %s' % target)
        shutil.copy2(source, target)
        if sha256_file(source) != sha256_file(target):
            raise BundleError('candidate copy mismatch: %s' % source)
        record(target, 'candidate', source)

    # The read-only originals the run depends on.
    for external in externals:
        record(external, 'external')

    manifest_path = root / 'bundle-manifest.json'
    with open(manifest_path, 'x', encoding='utf-8') as stream:
        json.dump(entries, stream, indent=1, sort_keys=True)
        stream.write('\n')
    info = {
        'schema': SCHEMA,
        'bundle_root': str(root),
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'pinned_tree': str(pinned),
        'manifest_path': str(manifest_path),
        'manifest_entries': len(entries),
        'protected_scope': {
            'pinned_tree_subset': list(REQUIRED_TREE_FILES),
            'candidate_files': [str(root / 'harness' / Path(c).name) for c in candidates],
            'external_files': sorted(str(Path(e).resolve()) for e in externals),
            'rule': 'every path above is bound by the manifest and re-verified against the '
                    'independent expected hashes before the worker starts and at entry startup',
        },
        'unprotected_scope': {
            'copied_tree_files': compared,
            'rule': 'the whole copied harness/scripts closure was re-hashed against its source '
                    'at bundle creation, but only the pinned subset above is bound by the '
                    'manifest; a later change to a non-pinned copied file is NOT detected',
        },
        'files_byte_compared': compared,
        'candidate_tree_files': [str(root / 'harness' / Path(c).name) for c in candidates],
        'external_files': sorted(str(Path(e).resolve()) for e in externals),
    }
    with open(root / 'bundle-info.json', 'x', encoding='utf-8') as stream:
        json.dump(info, stream, indent=1, sort_keys=True)
        stream.write('\n')
    return {'root': str(root), 'manifest_path': str(manifest_path),
            'manifest': entries, 'info': info}


def load_manifest(manifest_path):
    path = Path(manifest_path)
    if not path.is_file():
        raise BundleError('manifest is missing: %s' % path)
    try:
        entries = json.loads(path.read_text(encoding='utf-8'))
    except ValueError as exc:
        raise BundleError('manifest is not valid JSON: %s' % exc)
    if not isinstance(entries, dict) or not entries:
        raise BundleError('manifest is empty: an empty manifest is not a verified pin')
    return entries


def verify_manifest(manifest_path, *, expected=None, required=None):
    """Verify the manifest against the files on disk (fail closed).

    Every manifest entry must exist and hash exactly as recorded.  Every
    ``expected`` key must be present in the manifest and must match.  Every
    ``required`` key must be present.  An empty or incomplete manifest raises.
    """
    entries = load_manifest(manifest_path)
    verified = {}
    for path, entry in sorted(entries.items()):
        if not isinstance(entry, dict) or 'sha256' not in entry:
            raise BundleError('manifest entry is malformed: %s' % path)
        target = Path(path)
        if not target.is_file():
            raise BundleError('manifest file is missing: %s' % path)
        actual = sha256_file(target)
        if actual != entry['sha256']:
            raise BundleError('manifest hash mismatch: %s' % path)
        verified[path] = actual
    if expected:
        for path, want in sorted(expected.items()):
            if path not in verified:
                raise BundleError('manifest does not bind a required file: %s' % path)
            if verified[path] != want:
                raise BundleError('manifest hash mismatch for a pinned file: %s' % path)
    if required:
        for path in sorted(required):
            if path not in verified:
                raise BundleError('manifest does not bind a required file: %s' % path)
    return verified


def verify_startup(manifest_path, *, expected, required, expected_sources=None):
    """Strict startup verification of a prepared bundle.

    1. the manifest exists, is a non-empty mapping and binds every required
       path (an empty manifest is refused);
    2. every manifest entry exists on disk and hashes exactly as recorded;
    3. every required path hashes as the **independent** expected value, so a
       manifest that only agrees with itself is refused;
    4. every pinned SOURCE file (the original pinned tree) still hashes as
       the expected value, so a copy of a wrong source is refused.

    Returns the verified ``{path: sha256}`` mapping.
    """
    verified = verify_manifest(manifest_path, expected=expected, required=required)
    if expected_sources:
        entries = load_manifest(manifest_path)
        for path, entry in entries.items():
            source = entry.get('source_path') if isinstance(entry, dict) else None
            if not source or source not in expected_sources:
                continue
            if not Path(source).is_file():
                raise BundleError('pinned source is missing: %s' % source)
            actual = sha256_file(source)
            if actual != expected_sources[source]:
                raise BundleError('pinned source hash mismatch at startup: %s' % source)
    return verified


_IMPORT_PROBE = (
    'import json, importlib\n'
    'names = ["harness.pair_worker_audit", "harness.pairact_r1_student",'
    ' "harness.grasp_act_contract"]\n'
    'out = {}\n'
    'for name in names:\n'
    '    out[name] = importlib.import_module(name).__file__\n'
    'print(json.dumps(out))\n'
)


def check_modules_in_root(modules, bundle_root):
    """The imported modules must live in the REQUESTED bundle root."""
    wanted = (Path(bundle_root).resolve() / 'harness')
    for name, path in sorted(modules.items()):
        parent = Path(path).resolve().parent
        if parent != wanted:
            raise BundleError('module %s does not come from the requested bundle: %s'
                              % (name, parent))
    return True


def verify_import_same_tree(bundle_root, *, python=None, import_root=None):
    """Import the bundle's audit module, controller and contract for real.

    The import happens in an isolated subprocess with the bundle root on
    ``PYTHONPATH``; the resulting ``__file__`` paths must live in ONE harness
    directory **and** in the requested bundle root.  This is the real-import
    counterpart of the static ``check_same_tree`` rule.
    """
    root = Path(bundle_root).resolve()
    source = Path(import_root).resolve() if import_root else root
    environment = dict(os.environ)
    # A neutral working directory and a bundle-only PYTHONPATH: whatever the
    # probe imports must come from the bundle, never from the caller's tree.
    environment['PYTHONPATH'] = str(source)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    with tempfile.TemporaryDirectory(prefix='ugrp-bundle-probe-') as neutral:
        proc = subprocess.run([python or sys.executable, '-c', _IMPORT_PROBE],
                              capture_output=True, text=True, env=environment,
                              cwd=neutral, timeout=300)
    if proc.returncode != 0:
        raise BundleError('bundle import probe failed: %s' % proc.stderr.strip()[-2000:])
    try:
        modules = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise BundleError('bundle import probe returned no usable output')
    check_same_tree(modules['harness.pair_worker_audit'],
                    modules['harness.pairact_r1_student'])
    if harness_dir(modules['harness.grasp_act_contract']) != harness_dir(
            modules['harness.pairact_r1_student']):
        raise BundleError('contract comes from another harness tree')
    check_modules_in_root(modules, root)
    return modules
