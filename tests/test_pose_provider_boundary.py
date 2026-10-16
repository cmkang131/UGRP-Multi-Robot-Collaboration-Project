"""Static executor boundary and frozen inherited-hook audit; no physics/model imports."""
import ast
import hashlib
import json
import inspect
from pathlib import Path
import re
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOW = json.loads((ROOT / 'tests/fixtures/pose_provider_v5c/allowlist.json').read_text())
PATTERN = re.compile(r'(^|[^a-z])tags?([^a-z]|$)|Tag|TAG')


def marker_refs(source):
    refs = []
    for n in ast.walk(ast.parse(source)):
        values = []
        if isinstance(n, ast.Name): values = [n.id]
        elif isinstance(n, ast.Attribute): values = [n.attr]
        elif isinstance(n, ast.Constant) and isinstance(n.value, str): values = [n.value]
        elif isinstance(n, ast.alias): values = [n.name, n.asname or '']
        elif isinstance(n, ast.ImportFrom): values = [n.module or '']
        elif isinstance(n, ast.keyword): values = [n.arg or '']
        if any(PATTERN.search(v) for v in values):
            refs.append((n.lineno, values))
    return refs


def test_all_current_pair_own_executors_have_no_marker_references():
    files = {*ROOT.glob('harness/zone_pair*.py'), *ROOT.glob('harness/zone_own*.py'),
             ROOT / 'harness/owncam_time.py', ROOT / 'harness/owncam_drive_shared.py'}
    assert len(files) >= 25
    assert not set(str(p.relative_to(ROOT)) for p in files) & set(ALLOW['providers'])
    failures = {str(p.relative_to(ROOT)): marker_refs(p.read_text()) for p in sorted(files)}
    assert not {k: v for k, v in failures.items() if v}


@pytest.mark.parametrize('source', ['report.since_tag_s', 'loc.last_tag_t', "est['tag_gap']",
                                   'accepted_tag_checks(r)', 'from harness.wall_tags import TagDetector',
                                   "report.get('n_tags')", 'f(last_tag_t=0)'])
def test_static_check_catches_direct_control_and_dynamic_key_access(source):
    assert marker_refs(source)


def test_only_explicit_providers_evaluators_and_hash_frozen_paths_are_exempt():
    assert set(ALLOW) == {'providers', 'evaluation', 'historical_frozen'}
    for key in ('providers', 'evaluation'):
        assert all((ROOT / p).is_file() for p in ALLOW[key])
    for path, digest in ALLOW['historical_frozen'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    # Avoid merely whitelisting a historical method that is still active.
    from harness.zone_own_driver import GuardedDriver
    from harness.zone_pair_guards import GuardedPairApproach
    for cls, hooks in ((GuardedDriver, ('__init__', '_needs_look')),
                       (GuardedPairApproach, ('__init__', '_look_step', '_event', '_relocalize', '_needs_look', 'observe'))):
        for hook in hooks:
            assert getattr(cls, hook).__module__ in ('harness.zone_own_driver', 'harness.zone_pair_guards')


def test_active_constructor_chain_stops_before_frozen_provider_initialization():
    from harness.owncam_drive import OwnCamDriver
    from harness.owncam_drive_shared import SharedPoseDriver
    from harness.zone_own_driver import GuardedDriver
    from harness.zone_pair_guards import GuardedPairApproach

    for cls in (GuardedDriver, GuardedPairApproach):
        chain = cls.__mro__
        stop = chain.index(SharedPoseDriver)
        assert stop < chain.index(OwnCamDriver)
        # Check every cooperative constructor reached, including pair heading
        # setup in frozen ancestors, rather than only the most-derived method.
        for base in chain[:stop + 1]:
            if '__init__' in base.__dict__:
                assert not marker_refs(textwrap.dedent(inspect.getsource(base.__init__))), base
    terminal = ast.parse(textwrap.dedent(inspect.getsource(SharedPoseDriver.__init__)))
    assert not any(isinstance(n, ast.Name) and n.id in ('super', 'OwnCamDriver')
                   for n in ast.walk(terminal))


def test_new_interface_modules_have_no_truth_or_model_inference_dependencies():
    files = ['harness/pose_provider.py', 'harness/owncam_time.py', 'harness/owncam_drive_shared.py', 'harness/zone_pair_align.py',
             'harness/zone_pair_grasp.py', 'harness/zone_pair_guards.py', 'harness/zone_own_driver.py',
             'harness/owncam_delivery_shared.py', 'harness/owncam_memory_delivery.py',
             'harness/owncam_memory_inputs.py', 'harness/owncam_pose_guard_provider.py',
             'harness/m2_provider_adapter.py', 'harness/vision_motion_init.py']
    forbidden = {'mujoco', 'MjData', 'xpos', 'xquat', 'qpos', 'qvel', 'eval_only', 'GtStubPoseSource',
                 'cctv_top', 'nav_cam', 'torch'}
    for file in files:
        tree = ast.parse((ROOT / file).read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imports |= {n.name for n in ast.walk(tree) if isinstance(n, ast.alias)}
        assert not names & forbidden, file
        assert not any(i and i.split('.')[0] in forbidden for i in imports), file


def test_all_active_executor_constructor_and_lazy_hook_owners_are_audited():
    from harness.owncam_delivery_shared import SharedPoseDelivery, SharedLegDriver
    from harness.owncam_memory_delivery import M1OwnCamDeliveryMem, SharedMemoryLeg
    from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3
    from harness.owncam_drive_mem_v3 import LegDriverMemV3
    from harness.zone_own_deliver import _DeliverController
    from harness.zone_own_executor import ZoneOwnExecutor
    from harness.zone_own_team_host import OwnCamTeamHost
    from harness.zone_pair_executor import PairExecution, PairTeam
    from harness.zone_own_driver import GuardedDriver
    from harness.zone_pair_guards import GuardedPairApproach
    from harness.m2_provider_adapter import ProviderM2DoorStudent
    from scripts.run_zone_study_integration import StudyTeamHost
    from harness.owncam_drive_shared import SharedPoseDriver
    from harness.owncam_drive import OwnCamDriver
    controllers = (SharedPoseDelivery, M1OwnCamDeliveryMem, M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3,
                   _DeliverController, ZoneOwnExecutor, OwnCamTeamHost, StudyTeamHost, PairExecution, PairTeam,
                   ProviderM2DoorStudent)
    drivers = (SharedLegDriver, SharedMemoryLeg, LegDriverMemV3, GuardedDriver, GuardedPairApproach)
    forbidden_owners = {'harness.m1_owncam_delivery', 'harness.m1_owncam_memory', 'harness.owncam_drive'}
    for cls in (*controllers, *drivers):
        assert cls.__init__.__module__ not in forbidden_owners, cls
        tree = ast.parse(textwrap.dedent(inspect.getsource(cls.__init__)))
        # Default selection is allowed; eagerly constructing raw measurement machinery is not.
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert not names & {'OwnCamLocalizer', 'TagDetector', 'TagLandmarkProvider', 'tags_by_id'}, cls
    for cls in drivers:
        chain = cls.__mro__
        stop = chain.index(SharedPoseDriver)
        assert stop < chain.index(OwnCamDriver)
        for base in chain[:stop+1]:
            if '__init__' in base.__dict__:
                assert not marker_refs(textwrap.dedent(inspect.getsource(base.__init__))), base
    for cls in (SharedPoseDelivery, M1OwnCamDeliveryMem, M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3,
                _DeliverController):
        assert cls._start_leg.__module__ not in forbidden_owners
    assert ProviderM2DoorStudent._queue_grasp.__module__ == 'harness.m2_provider_adapter'
    # Local classes are also executable entry points: their cooperative initialization
    # must go through the audited public host/controller, never a legacy provider.
    runtime = ast.parse((ROOT / 'scripts/zone_pair_dev_runtime.py').read_text())
    devhost = next(n for n in ast.walk(runtime) if isinstance(n, ast.ClassDef) and n.name == 'DevHost')
    assert [b.id for b in devhost.bases] == ['OwnCamTeamHost']
    factory = ast.parse((ROOT / 'harness/zone_pair_executor.py').read_text())
    routed = next(n for n in ast.walk(factory) if isinstance(n, ast.ClassDef) and n.name == 'RoutedM2')
    assert [b.id for b in routed.bases] == ['PairGraspRelook', 'ProviderM2DoorStudent']
