"""Scene-only RGB wall exclusion for COLOURED floor landmarks, default off.

R1 v5 wall H133 aliases the C-landmark H143±12 (S20..150). The frozen
scene's RGB wall class removes that plane before metric floor fitting. LK's
floor image_mask and its points stay unchanged; doors keep their old clear mask.
Mixed edge pixels are unknown: the static audit records62/5,482,362 floor-labelled
PNG pixels excluded, and88/99/105 spurious wall-as-floor lines removed. No GT mask
is accepted here. See reloc16 landmark-audit; no new acceptance constants.
"""
import os
import numpy as np
from harness.scene_colour_boundary import surface_masks,RELOC16_OPTION

OPTION='scene_floor_landmark_mask_v1'
ENV='UGRP_RELOC16_FLOOR_LANDMARK_MASK'
PROFILE='walls_floor_contrast_v5_indigo110_s80'


def floor_clear(image,clear,*,state=None,option=None):
    selected=os.environ.get(ENV,'off') if option is None else option
    if selected=='off':return clear,{'option':'off'}
    if selected!=OPTION:raise ValueError('UNKNOWN_SCENE_FLOOR_LANDMARK_MASK')
    if state is None:
        from harness.active_wall_vision import modules
        state=getattr(modules()[1],'scene_colour_state',None)
    if state is None or state.profile!=PROFILE or state.option!=RELOC16_OPTION:
        raise ValueError('SCENE_FLOOR_MASK_REQUIRES_FIXED_V5_AND_BOUNDARY_V2')
    wall=surface_masks(image,state.calibration,expanded_wall_value=True)[0]['wall']
    result=np.asarray(clear,bool)&~wall
    return result,dict(option=OPTION,wall_class_pixels=int(wall.sum()),excluded_visible_pixels=int((clear&wall).sum()),
                       floor_lk_changed=False,doors_clear_changed=False,truth_inputs=0)
