"""Static scene construction/validation for the own-camera host (no control decisions)."""


def own_scene(spec, profile, scene=None):
    from sim.zone_cargo_contact import base_profile
    from sim.zone_landmarks import TaggedZoneScene
    if scene is not None:
        from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
        if (not isinstance(scene, TaggedCargoZoneScene)
                or scene.selection != 'zones/' + spec['map']
                or scene.scene['seed'] != spec['seed']
                or scene.scene['contact_profile'] != base_profile(profile)
                or scene.config['cargo_set']['items'] != list(spec.get('team_cargo', []))):
            raise ValueError('injected standard cargo scene differs from host spec')
        return scene
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
