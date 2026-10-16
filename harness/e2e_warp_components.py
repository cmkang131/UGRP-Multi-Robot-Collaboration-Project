"""Hash-bound owner component interfaces; pending parts fail closed.

No simulator imports. Factories receive static task/map and own observations,
never the physics object. A manifest is an admission claim, not task success.
"""
import hashlib
import importlib
import json
from pathlib import Path

REQUIRED = ('navigation', 'loaded_camera_fk', 'static_map_registration', 'release_relocalization')


def require_components(path, root):
    if path is None:
        raise ValueError('DEPENDENCY_WAIT:component manifest missing')
    manifest = json.loads(Path(path).read_text())
    for name in REQUIRED:
        record = manifest.get(name, {})
        if record.get('ready') is not True or not record.get('owner') or not record.get('evidence'):
            raise ValueError('DEPENDENCY_WAIT:' + name)
    for name in ('controller_factory', 'evaluator_factory'):
        item = manifest.get(name, {})
        module, sep, attr = item.get('entry', '').partition(':')
        file = Path(root) / (module.replace('.', '/') + '.py')
        if (not sep or not attr or not file.is_file() or not file.resolve().is_relative_to(Path(root).resolve())
                or hashlib.sha256(file.read_bytes()).hexdigest() != item.get('sha256')):
            raise ValueError('DEPENDENCY_WAIT:hash-bound ' + name)
    actor = manifest.get('ACT', {})
    if actor.get('ready') is not True or actor.get('native_contact') != 'warp_native_contact_v1':
        raise ValueError('DEPENDENCY_WAIT:selected native ACT artifact')
    artifact = Path(actor.get('path', ''))
    inventory = artifact / 'SHA256.json'
    if not inventory.is_file() or hashlib.sha256(inventory.read_bytes()).hexdigest() != actor.get('inventory_sha256'):
        raise ValueError('ACT artifact inventory mismatch')
    files = json.loads(inventory.read_text())
    if set(files) != {'model.safetensors', 'adapter.json', 'config.json'}:
        raise ValueError('ACT artifact inventory names mismatch')
    for name, expected in files.items():
        if hashlib.sha256((artifact/name).read_bytes()).hexdigest() != expected:
            raise ValueError('ACT artifact hash mismatch:' + name)
    meta = json.loads((artifact/'adapter.json').read_text())
    provenance = meta.get('provenance', {})
    if provenance.get('synthetic_only') or provenance.get('step') != 10000 or provenance.get('schedule_steps') != 10000:
        raise ValueError('completed ACT16w research artifact required')
    if provenance.get('contact_profile') != 'warp_native_contact_v1':
        raise ValueError('actual checkpoint provenance must bind native contact; no legacy substitution')
    if not actor.get('selection_evidence'):
        raise ValueError('ACT validation selection evidence required')
    return manifest


def factory(record):
    module, attr = record['entry'].split(':')
    return getattr(importlib.import_module(module), attr)


def load_actor(record):
    """The owner adapter validates config, hashes and the pinned LeRobot source."""
    import sys
    from pathlib import Path
    vendor = Path(__file__).resolve().parents[1] / 'scripts/e2ewarp_vendor'
    sys.path.insert(0, str(vendor))
    from act16w_input import Act16wActor
    import torch
    if not torch.cuda.is_available():
        raise ValueError('GPU ACT inference required; no CPU fallback')
    return Act16wActor.load(record['path'], device='cuda')


class MissionRobot:
    """Owner controller protocol for the full path (no diagnostic substitution).

    factory(robot_id, static, predict_act) -> controller
    observe(OwnFrame) -> own-derived report
    candidates() -> [{id,skill,expected_cost,...}]
    select(candidate_id, sim_s); command(sim_s) -> grasp_act_contract command
    complete -> own-observation completion claim (never physical success)
    """
    def __init__(self, robot, static, components, actor):
        self.component = factory(components['controller_factory'])(
            robot_id=robot, static=static, predict_act=actor.predict)
        self.command_history = []

    def observe(self, frame):
        return self.component.observe(frame)

    def candidates(self):
        return self.component.candidates()

    def select(self, candidate, now):
        return self.component.select(candidate, now)

    def command(self, now):
        from harness.grasp_act_contract import command
        result = command(self.component.command(now))
        self.command_history.append(result)
        return result

    @property
    def complete(self):
        return self.component.complete is True
