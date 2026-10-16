"""Default-off MJWarp colour class reuse. No simulator input or fitted bound."""
import hashlib,json,os
from functools import lru_cache
from pathlib import Path

ENV='UGRP_WARP5_PERCEPTION'


@lru_cache(maxsize=4)
def calibration(path,sha):
    p=Path(path)
    if not sha or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('WARP5_CALIBRATION_HASH_MISMATCH')
    c=json.loads(p.read_text())
    if c.get('renderer_profile') not in ('warp5_native_visual_v1','warp5_native_visual_v2'):raise ValueError('WARP5_RENDERER_PROFILE_REQUIRED')
    return c


def exclude_wall(mask,bgr):
    if os.environ.get(ENV,'off')=='off':return mask
    if os.environ[ENV]!='rendered_v1':raise ValueError('UNKNOWN_WARP5_PERCEPTION')
    from harness.scene_colour_boundary import surface_masks
    c=calibration(os.environ['UGRP_SCENE_COLOUR_CALIBRATION'],os.environ['UGRP_SCENE_COLOUR_CALIBRATION_SHA256'])
    surfaces,_=surface_masks(bgr,c,expanded_wall_value=True)
    # Reuse the measured wall RGB class. No GT mask, new HSV threshold,
    # minimum area, floor-plane distance or success tolerance is introduced.
    return mask & ~surfaces['wall']


def install():
    """Opt-in clone of the frozen function; preserve its source/default path."""
    if os.environ.get(ENV,'off')=='off':return
    import ast,inspect
    from harness import floor_goal as frozen
    original=getattr(frozen.detect_floor,'_warp5_original',frozen.detect_floor)
    tree=ast.parse(inspect.getsource(original));function=tree.body[0];edits=0
    for i,node in enumerate(function.body):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='mask' for t in node.targets):
            function.body[i+1:i+1]=ast.parse('mask = __warp5_exclude__(mask, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)).astype(np.uint8)').body
            edits+=1;break
    if edits!=1:raise ValueError('WARP5_FROZEN_FLOOR_MASK_SHAPE_CHANGED')
    namespace=dict(original.__globals__,__warp5_exclude__=exclude_wall)
    exec(compile(ast.fix_missing_locations(tree),'<warp5-opt-in-floor-wall-class>','exec'),namespace)
    adapted=namespace['detect_floor'];adapted._warp5_original=original
    frozen.detect_floor=adapted
    # The tracker caches the detector as a static method at class definition.
    for obj in vars(frozen).values():
        if isinstance(obj,type) and getattr(obj,'detector',None) is original:obj.detector=staticmethod(adapted)
