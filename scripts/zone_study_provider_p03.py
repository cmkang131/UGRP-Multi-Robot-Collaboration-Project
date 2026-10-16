"""P03 v1 candidate integration; explicit opt-in, no executable CLI or registration.

Legacy v6e sources stay byte-identical. This module exposes a fake-testable host
and an unsealed bundle preview for P07/coordinator use. A new registered workflow,
source/bundle pin and physical acceptance are still required before execution.
"""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

from scripts import run_zone_study_integration as legacy
from harness import vision_loc_contract_p03 as vp
from harness import zone_study_integration as zi
from harness import zone_study_referee as zr
from harness.python_source_closure import source_closure
from harness.zone_study_contract import digest
from harness.zone_own_executor import OwnCamTeamHost, ROBOTS
from harness.zone_study_pose_delay_p03 import DelayedPoseSource
from sim import zone_eval_top
from sim import zone_hidden_events as zhe

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_ID = 'vision_zero_tag_v2_p03_v1'
BASELINE_PROVIDER_ID = 'vision_zero_tag_v2'
CANDIDATE_ID = 'zone-study-provider-p03-v1'
# Literal roots are also readable by planning tools without importing runtime code.
RUNTIME_ENTRY_POINTS = ('scripts/zone_study_provider_p03.py',
                        'harness/vision_pose_source_p03.py',
                        'harness/zone_study_pose_delay_p03.py')
RUNTIME_ASSETS = ('configs/vision_loc_provider_p03.json',
                  'configs/model_artifacts.json', 'configs/vision_loc_worker.json',
                  'experiments/2026-09-26-vision-loc/selected_config_v3.json',
                  'experiments/2026-09-26-vision-loc/calibration_train.json')


def provider_spec(map_id):
    spec = zi.pose_provider_spec(BASELINE_PROVIDER_ID, map_id=map_id)
    spec.update(provider_id=PROVIDER_ID, version='geometry_lifecycle_p03_v1',
                factory='harness.vision_pose_source_p03:VisionPoseSourceV2',
                source_label_prefix='owncam_pf_vision_zero_tag_v2_p03_v1:',
                note_ko='P03 별도 후보: 미등록·미봉인, fake 계약만 검증')
    spec['source_files'] = sorted(set(spec['source_files']) | set(RUNTIME_ENTRY_POINTS) | set(RUNTIME_ASSETS))
    return spec


def build_pose_provider(spec, static_map, params, seed):
    expected = provider_spec(static_map['map_id'])
    if spec != expected:
        raise zi.ContractViolation('P03 requires its exact explicit candidate provider spec')
    module, _, name = spec['factory'].partition(':')
    provider = getattr(importlib.import_module(module), name)(static_map, params, seed=int(seed))
    try:
        zi.check_pose_provider(provider, spec)
        return DelayedPoseSource(provider)
    except Exception:
        provider.close()
        raise


def runtime_files(prereg, provider, *, root=ROOT):
    pin = vp.load_json(Path(root) / 'configs/vision_loc_provider_p03.json')
    references = tuple(pin['active']['files_sha256'])
    for name in references:
        path = Path(root) / name
        if not path.resolve().is_relative_to(Path(root).resolve()) or not path.is_file():
            raise ValueError(f'missing or nonlocal P03 asset: {name}')
    # VIS3 files in dated experiment directories are loaded by file path, not
    # Python package name. Hash those declared frozen assets directly; only
    # importable paths can be roots for the AST package/import walker.
    importable = tuple(name for name in references if not name.endswith('.py')
                       or all(part.isidentifier() for part in name[:-3].split('/')))
    roots = (*legacy.RUNTIME_ENTRY_POINTS, *legacy.RUNTIME_ASSETS,
             *RUNTIME_ENTRY_POINTS, *RUNTIME_ASSETS,
             *importable, *provider['source_files'])
    closure = source_closure(root, roots,
                             modules=(prereg['student']['skill_module'], provider['factory'].partition(':')[0]))
    return tuple(sorted(set(closure) | set(references)))


def run_bundle(prereg, episode):
    """Read-only P03 preview with explicit JSON/reference pins; never a runnable ID."""
    if prereg.get('pose_provider') != PROVIDER_ID:
        raise zi.ContractViolation('P03 preview requires explicit candidate provider selection')
    contract = vp.provider_runtime_contract(map_id=episode['map'], calibration=prereg['student']['calibration'])
    baseline = {**prereg, 'pose_provider': BASELINE_PROVIDER_ID}
    bundle, scenario, map_bundle, _ = legacy.run_bundle(baseline, episode)
    provider = provider_spec(episode['map'])
    row = zi.provider_record(provider)
    row['runtime_contract'] = contract
    row['record_sha256'] = digest({k: v for k, v in row.items() if k != 'record_sha256'})
    bundle['study_invariant'].update(pose_provider=copy.deepcopy(row['label']),
                                     execution_bundle_id=None, candidate_id=CANDIDATE_ID)
    bundle.update(schema='ugrp.zone_study_provider_preview.p03.v1',
                  candidate_id=CANDIDATE_ID, runnable=False, physical_ready=False,
                  baseline_execution_bundle_id=bundle['execution_bundle_id'], execution_bundle_id=None,
                  pose_provider=row,
                  runtime_files_sha256={f: zi.file_sha256(ROOT / f) for f in runtime_files(prereg, provider)})
    return bundle, scenario, map_bundle, provider


def check_preview(saved, prereg, episode):
    """Reject a saved P07/coordinator preview after any candidate input changes."""
    current = run_bundle(prereg, episode)[0]
    if saved != current:
        raise zi.ContractViolation('P03 candidate preview/source hash mismatch')
    return digest(current)


class StudyTeamHost(legacy.StudyTeamHost):
    """Explicit candidate host; inherits unchanged scheduling/evaluation methods."""
    def __init__(self, spec, student, *, root, provider_spec, frames_dir=None, hidden=None):
        self.provider_sources = {}
        self.hidden = hidden or zr.HiddenEventSchedule({'eval': {'hidden_events': []}})
        providers = []
        self._pose_providers = providers
        self._providers_closed = False

        def pose_factory(rid, static, params, seed):
            provider = build_pose_provider(provider_spec, static, params, seed)
            providers.append(provider)
            if callable(getattr(getattr(provider, 'provider', provider), 'init_prior', None)):
                prior = spec.get('pose_priors', {}).get(rid)
                if prior is None:
                    raise zi.ContractViolation(f'{rid}: provider requires a preregistered own dock prior')
                provider.init_prior(**prior)
            self.provider_sources[rid] = provider.source
            return provider

        scene = None
        if spec.get('pair_order_sheets') and provider_spec['uses_landmark_tags']:
            # Reuse #235's standard Scene setup (drops its colour placeholder
            # before XML generation, never based on runtime state).
            from scripts.zone_pair_dev_runtime import make_scene
            scene = make_scene(spec)
        if self.hidden.obstacles():
            # Parked obstacles through the host's scene= argument (the host and
            # the frozen scene sources stay unchanged); none -> the same scene.
            scene = zhe.hidden_event_scene(spec, spec['contact_profile'], self.hidden.obstacles(), scene)
        try:
            OwnCamTeamHost.__init__(self, spec, student, root=root, study_layer=self._no_layer, frames_dir=frames_dir,
                             scene=scene, pose_factory=pose_factory)
        except Exception as exc:
            try:
                self.close()
            except Exception as close_exc:
                exc.add_note(f'provider/world cleanup failed: {close_exc}')
            raise
        # scene.setup has finished. Overlay only the evaluation cameras in the
        # world; keep self.static and every executor's own static map untouched.
        try:
            profile = legacy.evaluation_top_config(self.static)['profile']['id']
            self.eval_static = zone_eval_top.eval_static_map(self.static, profile)
            self.eval_only['top_camera'] = zone_eval_top.apply_to_world(self.world, self.static, profile)
            self.links = {rid: legacy.HostRobotLink(self, rid) for rid in ROBOTS}
            # Hidden events act on physics only (sim.zone_hidden_events): never a robot
            # input, command row or wake. No events -> nothing is built or wrapped.
            self.hidden_physics = (zhe.HiddenEventPhysics(self.world, self.hidden, objects=self.objects,
                                                          item_geoms=self._box_geom, finger_geoms=self._fingers)
                                   if self.hidden.events else None)
        except Exception as exc:
            try:
                self.close()
            except Exception as close_exc:
                exc.add_note(f'provider/world cleanup failed: {close_exc}')
            raise

    def close(self):
        if self._providers_closed:
            return
        self._providers_closed = True
        errors = []
        # Includes providers whose prior/setup failed before an executor slot
        # was registered; attempt every owned close even after one fails.
        for provider in self._pose_providers:
            try:
                provider.close()
            except Exception as exc:
                errors.append(exc)
        try:
            if hasattr(self, 'world'):
                OwnCamTeamHost.close(self)
        finally:
            if errors:
                raise errors[0]


def write_outputs(out, prereg, episode, condition, bundle, bundle_sha, host, trial, result,
                  stop, failure, code, started, load0, dev, *, referee=None):
    """Preserve the legacy audit outputs and add each candidate's lifecycle receipt."""
    summary = legacy.write_outputs(out, prereg, episode, condition, bundle, bundle_sha,
                                   host, trial, result, stop, failure, code, started, load0, dev,
                                   referee=referee)
    if host is not None:
        for rid, slot in host.robots.items():
            path = out / 'robots' / rid / 'inputs' / 'pose_provider.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(slot.executor.pose.record(), indent=2, ensure_ascii=False) + '\n')
    return summary
