"""Opt-in environment Scene adapter; the registered own-scene provider is frozen."""
from sim.zone_own_scene_provider import own_scene as legacy_own_scene


def own_scene(spec, profile, scene=None, *, scene_factory=None):
    from harness.zone_environment_registry import environment_entry, resolve_static_map
    static, _ = resolve_static_map(spec['map'], robot_model=spec.get('robot_model'),
                                  static_map_sha256=spec.get('static_map_sha256'))
    entry = environment_entry(spec['map'])
    if entry:
        from sim.zone_cargo_contact import base_profile
        if scene is None:
            if scene_factory is None:
                import importlib
                module, _, name = entry['scene_factory'].partition(':')
                scene_factory = getattr(importlib.import_module(module), name).from_spec
            return scene_factory(spec, base_profile(profile))
        import importlib
        module, _, name = entry['scene_factory'].partition(':')
        cls = getattr(importlib.import_module(module), name)
        if not isinstance(scene, cls):
            raise ValueError('map requires its registered v3 Scene' if entry['robot_model'] == 'masterpi_v3'
                             else 'map requires its registered geometry Scene')
        if scene.config['static_map'] != static or scene.config.get('robot_model', 'masterpi_v2') != entry['robot_model']:
            raise ValueError('injected scene map/model identity mismatch')
    return legacy_own_scene(spec, profile, scene)


def scene_static_map(map_id):
    from harness.zone_environment_registry import resolve_static_map
    return resolve_static_map(map_id)[0]


def scenario_scene(scenario, seed):
    """Explicit mixed v4 setup; does not change own_scene's frozen factories."""
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    return ScenarioFinalV3Scene.from_scenario(scenario, seed)
