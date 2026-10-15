"""Explicit gatesv5 scene binding. Legacy callers remain off by default."""
import json
from pathlib import Path

SCENE = 'walls_floor_contrast_v5_indigo110_s80'


def scene_bindings(name='off'):
    if name == 'off':
        return None
    if name != SCENE:
        raise ValueError('gatesv5 requires the coordinator-pinned scene')
    from sim import scene_contrast_v5 as profile
    from sim import camera_render_quality as quality

    def install(scene):
        return profile.install(scene, name)

    def configure(world, out):
        # no_mip_v1 changes GL sampling only; scale=1 and sample count unchanged.
        # Configure on the existing renderer owner thread, before any observation.
        def on_thread():
            return {key: quality.configure_context(getattr(world, key), world.model, 'no_mip_v1')
                    for key in ('renderer', 'observer_renderer') if getattr(world, key, None) is not None}
        contexts = world._render_executor.submit(on_thread).result()
        record = dict(scene_profile=name, camera_quality='no_mip_v1',
                      scene_colour_transition_v1='off', profile=profile.verify_model(world.model, name),
                      contexts=contexts, source_scene_commit='a68106fd86c314d7c1d10cd321475b0c86c93310')
        if not contexts or any(t['min'] != 9729 for c in contexts.values() for t in c['textures']):
            raise RuntimeError('no_mip_v1 GL_LINEAR binding not applied')
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out)/'scene-quality.json').write_text(json.dumps(record, indent=2)+'\n')
        return record
    return install, configure
