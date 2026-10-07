"""Connect the frozen appearance boundary detector to the active mapping ABI.

Ulrich & Nourbakhsh 2000 sections 3-4: the lowest obstacle pixel per column
is its ground contact; interior wall texture edges are not ground contacts.
No new thresholds, floor_boundary_v1 modifications, or simulator/map inputs.
"""
OPTION='appearance_contact_v1'


def detect(hfw,und_bgr,cm,*,params,loaded=False,wall_detector='off',contact_rule='off',
           contact_state=None,frame_id=None,odometry_pose=None):
    if contact_rule not in ('off','bottom_up_connected_v1','floor_appearance_ulrich_v1'):
        raise ValueError('UNKNOWN_CONTACT_RULE')
    if contact_rule=='floor_appearance_ulrich_v1':
        from harness.wall_floor_ulrich import UlrichFloorState, to_scan
        if wall_detector!='off':raise ValueError('CONTACT_RULE_REQUIRES_ORIGINAL_DETECTOR')
        if not isinstance(contact_state,UlrichFloorState):raise ValueError('EXPLICIT_FLOOR_STATE_REQUIRED')
        import numpy as np
        valid=(hfw.mp.undistort(np.full_like(und_bgr,255))==255).all(-1)
        self_top=hfw.self_top_mask(und_bgr,cm,params,loaded)
        result=contact_state.detect(und_bgr,cm,frame_id=frame_id,odometry_pose=odometry_pose,
            valid_image=valid,self_top=self_top)
        return to_scan(result,und_bgr,cm,int(params.get('candidates',hfw.PARAMS['candidates'])))
    if contact_rule!='off':
        if wall_detector!='off':raise ValueError('CONTACT_RULE_REQUIRES_ORIGINAL_DETECTOR')
        return hfw.detect(und_bgr,cm,params=params,loaded=loaded,contact_rule=contact_rule)
    if wall_detector=='off':
        return hfw.detect(und_bgr,cm,params=params,loaded=loaded)
    if wall_detector!=OPTION:raise ValueError('UNKNOWN_ACTIVE_WALL_DETECTOR')
    return hfw.detect(und_bgr,cm,params=params,loaded=loaded,wall_detector='floor_boundary_v1')
