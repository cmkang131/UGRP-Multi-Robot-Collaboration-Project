"""Read-only/fake check in a disposable #292 archive with the P01 additions.

Usage under scripts.run_ci_tests.run_locked:
    python check_p292_composition.py /tmp/composed-static-tree
Only the disposable tree's registry is temporarily mutated, then restored.
No registered source, seal, Scene, physics, renderer or network is executed.
"""
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch


def main():
    root = Path(sys.argv[1]).resolve()
    if not root.is_relative_to(Path('/private/tmp')) and not root.is_relative_to(Path('/tmp')):
        raise SystemExit('use a disposable archive under /tmp')
    sys.path.insert(0, str(root))
    for name in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
        sys.modules[name] = None
    def forbidden(*args, **kwargs):
        raise AssertionError('physics, renderer or network forbidden')
    from sim.session_scenes import Scene
    from sim.zone_dock_scene import DockTaggedCargoZoneScene
    from sim.zone_own_scene_provider import own_scene
    from sim.zone_start_dock import MAP_ID
    from scripts.zone_pair_v6_contract import candidate_contract as base_candidate
    from harness.zone_environment_candidate import candidate_contract, verify_candidate_contract
    from harness import zone_environment_registry as env
    spec = {'map': MAP_ID, 'seed': 911, 'goal': {}, 'team_cargo': [{'item_id': 'beam'}]}
    sentinel = object()
    with patch.object(Scene, '__init__', forbidden), patch.object(socket.socket, 'connect', forbidden), \
            patch.object(DockTaggedCargoZoneScene, 'from_tagged_cargo', return_value=sentinel) as factory:
        base = base_candidate('v6h')
        assert 'harness/zone_environment_registry.py' not in base['source_sha256']
        assert own_scene(spec, 'cargo_noslip_v1') is sentinel
        candidate = candidate_contract(base, MAP_ID)
        assert verify_candidate_contract(candidate, base) == candidate
        assert candidate['base_contract'] == base
        # The final-map candidate must explicitly pin its dynamically selected Scene.
        final = candidate_contract(base, 'zone_wide_two_doors_final_v1')
        assert final['dynamic_imports'] == ['sim.zone_final_scene']
        assert 'sim/zone_final_scene.py' in final['source_sha256']
        path = root / env.REGISTRY_FILE
        original = path.read_bytes()
        try:
            changed = json.loads(original)
            changed['status'] = 'INVALID_REVIEW_MUTATION'
            path.write_text(json.dumps(changed))
            assert base_candidate('v6h') == base
            # This was broken by the old P01 legacy hook. Now the base route
            # never reads the opt-in registry, so an unchanged base pin is valid.
            assert own_scene(spec, 'cargo_noslip_v1') is sentinel
            for record in (candidate, final):
                try:
                    verify_candidate_contract(record, base)
                except ValueError as error:
                    assert 'environment source hash mismatch' in str(error)
                else:
                    raise AssertionError('mutated environment admitted')
        finally:
            path.write_bytes(original)
        assert verify_candidate_contract(candidate, base_candidate('v6h')) == candidate
        print(json.dumps({'base_sources': len(base['source_sha256']),
                          'base_imports_environment_registry': False,
                          'legacy_dock_factory_calls': factory.call_count,
                          'legacy_dock_survives_registry_mutation': True,
                          'composed_sources': len(candidate['source_sha256']),
                          'composed_registry_mutation_rejected': True,
                          'final_dynamic_scene_pinned': True,
                          'final_registry_mutation_rejected': True,
                          'base_contract_preserved': True,
                          'physics': False}, indent=2))


if __name__ == '__main__':
    main()
