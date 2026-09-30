"""Static scene construction/validation for the own-camera host (no control decisions)."""


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
    from sim.zone_masterpi_v3_scene import MAP_IDS as V3_MAP_IDS, MasterPiV3ZoneScene
    from sim.zone_cargo_contact import base_profile
    from sim.zone_landmarks import TaggedZoneScene
    from sim.zone_geometry_scene import GeometryCargoZoneScene, MAP_IDS
    if spec['map'] in V3_MAP_IDS:
        if scene is None:
            return MasterPiV3ZoneScene.from_spec(spec, base_profile(profile))
        if not isinstance(scene, MasterPiV3ZoneScene):
            raise ValueError('v3 map requires its registered v3 Scene')
    if scene is not None:
        from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
        if (not isinstance(scene, (TaggedCargoZoneScene, GeometryCargoZoneScene))
                or scene.selection != 'zones/' + spec['map']
                or scene.scene['seed'] != spec['seed']
                or scene.scene['contact_profile'] != base_profile(profile)
                or scene.config['cargo_set']['items'] != list(spec.get('team_cargo', []))):
            raise ValueError('injected standard cargo scene differs from host spec')
        return scene
    elif spec['map'] in MAP_IDS:
        return GeometryCargoZoneScene.from_spec(spec, base_profile(profile))
    elif spec.get('team_cargo'):
        from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
        from sim.zone_start_dock import MAP_ID
        scene_cls = TaggedCargoZoneScene
        if spec['map'] == MAP_ID:
            from sim.zone_dock_scene import DockTaggedCargoZoneScene
            scene_cls = DockTaggedCargoZoneScene
        return scene_cls.from_tagged_cargo(
            spec['map'], spec['seed'], cargo=spec['team_cargo'], goal=spec['goal'],
            contact_profile=base_profile(profile))
    else:
        return TaggedZoneScene.from_tagged(spec['map'], spec['seed'], spec['goal'], spec.get('extra_boxes'),
                                                 contact_profile=base_profile(profile))


def scene_static_map(map_id):
    from harness.zone_environment_registry import resolve_static_map
    return resolve_static_map(map_id)[0]
