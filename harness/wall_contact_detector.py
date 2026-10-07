"""Connect the frozen appearance boundary detector to the active mapping ABI.

Ulrich & Nourbakhsh 2000 sections 3-4: the lowest obstacle pixel per column
is its ground contact; interior wall texture edges are not ground contacts.
No new thresholds, floor_boundary_v1 modifications, or simulator/map inputs.
"""
OPTION='appearance_contact_v1'


def detect(hfw,und_bgr,cm,*,params,loaded=False,wall_detector='off',contact_rule='off'):
    if contact_rule not in ('off','bottom_up_connected_v1'):
        raise ValueError('UNKNOWN_CONTACT_RULE')
    if contact_rule!='off':
        if wall_detector!='off':raise ValueError('CONTACT_RULE_REQUIRES_ORIGINAL_DETECTOR')
        return hfw.detect(und_bgr,cm,params=params,loaded=loaded,contact_rule=contact_rule)
    if wall_detector=='off':
        return hfw.detect(und_bgr,cm,params=params,loaded=loaded)
    if wall_detector!=OPTION:raise ValueError('UNKNOWN_ACTIVE_WALL_DETECTOR')
    return hfw.detect(und_bgr,cm,params=params,loaded=loaded,wall_detector='floor_boundary_v1')
