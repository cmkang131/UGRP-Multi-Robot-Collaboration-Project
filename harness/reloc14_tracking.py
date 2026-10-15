"""Continuous known-mode PF tracking; global registration remains a separate gate.

Nav2 amcl_node.cpp shouldUpdateFilter/updateFilter/map-to-odom transform and
ORB-SLAM2 Tracking::Track (LOST -> Relocalization) are the design references.
Native PF motion gates (.25 m / .2 rad) are unchanged. R7's three distinct views
and 10 cm/5 deg anchor test apply on global acquisition/reacquisition only.
Known-mode tracking reuses the EXISTING current-view 5 cm/5 deg line admission,
two independent axes, .9 cluster mass and .15 m/5 deg raw covariance limits;
none is newly fitted or claimed to certify actual error. See reloc14 README.
"""
import math
import numpy as np
from harness.natural_floor_slam import compose


def track(reg, row, observation, own_pose, t):
    from harness.selfmap4_geometry import inverse
    cov=np.asarray(row['covariance'])
    # AMCL tracking may constrain only one direction in a view. R1 lost all
    # four modes by reapplying global two-axis observability to every update
    # (one valid line at seed93583). Reuse the existing NIS<=9 line matcher on
    # ONE current frame and raw P; retain two-axis/three-view checks for GLOBAL.
    from harness.selfmap5_registration import MultiFrameEvidence
    evidence=MultiFrameEvidence();evidence.trace_edge_ids=True
    evidence.frames=[dict(t=t,pose=np.asarray(own_pose),lines=[f for f in observation['features'] if f['kind']=='floor_line'])]
    _,geometry=evidence.supported(reg.pf.landmark_map.edges,row['pose'],own_pose,cov)
    supported=geometry['supported_floor_lines']>0
    # R2 t39.3 had a valid wall segment and no floor-color boundary. AMCL's
    # SAME wall likelihood field supplies a partial constraint in that view.
    # Reuse sigma_hit=.2m and NIS radius 3 (9) from the pinned field/R7 models.
    from harness.self_map_csm import sample_segments
    from harness.natural_floor_slam import transform
    from harness.own_map_amcl_vendor.field import PARAMS
    points=sample_segments(observation.get('segments',[]))
    wall_support=0
    if len(points):
        distances=reg.pf.field.distances(transform(points,row['pose']))
        variance=np.linalg.eigvalsh(cov[:2,:2]).max()+PARAMS['sigma_hit_m']**2
        wall_support=int(np.count_nonzero(distances**2<=9*variance))
    geometry['supported_wall_field_points']=wall_support
    geometry['tracking_partial_observation']=True
    supported=supported or wall_support>0
    good=(row['resolved'] and row['cluster']['mass']>=.9 and
        np.linalg.eigvalsh(cov[:2,:2]).max()<=.15**2 and cov[2,2]<=math.radians(5)**2 and supported)
    # Fresh invalid evidence causes LOST, never a renewed global confirmation
    # count from repeated sensor-less frames. Motion-gated PF prediction is not
    # represented as a new absolute measurement.
    if row['updated'] and not good:
        reg.tracking_state='LOST';reg.execution_r7_admitted=False
        reg.confirmations.clear();reg.confirmation_views.clear()
        reg.last_tracking_failure=dict(t=t,category='tracking_evidence_lost',
            blocked_object='own_rgb_static_lines',minimum_gap_m=None,
            gap_status='not_applicable_localization_gate',geometry=geometry)
        return None,False
    reg.execution_r7_admitted=True
    a=reg.map_from_own[2];c,s=math.cos(a),math.sin(a)
    R=np.array([[c,s,0],[-s,c,0],[0,0,1]])
    local=compose(inverse(reg.map_from_own),row['pose'])
    reg.last=dict(updated=row['updated'],resolved=bool(good),registered=True,
        confirmations=len(reg.confirmations),execution_r7_admitted=True,
        world_pose=row['pose'],raw_covariance=row['covariance'],covariance=row['covariance'],
        execution_covariance=(R@cov@R.T).tolist(),cluster=row['cluster'],pf_sensor=row.get('sensor'),
        feature_count=len(observation['features']),geometry=geometry,
        tracking=dict(state='TRACKING',measurement=bool(row['updated']),
            motion_model='calibrated_issued_commands',global_confirmations_required=False,
            update_min_d_m=.25,update_min_a_rad=.2,budget_kind='finite_PF_particles_and_line_checks'),
        reloc12=dict(registered_world_pose=compose(reg.command_registration_anchor,own_pose).tolist(),
            map_from_execution=reg.map_from_own.tolist(),execution_frame_v1=True,
            replay=dict(own_odometry_pose=np.asarray(own_pose).tolist()),
            rejection=dict(category='accepted_tracking' if row['updated'] else 'motion_gate_prediction',
                blocked_object='none',minimum_gap_m=None,gap_status='not_applicable_localization_gate')))
    return (local,R@cov@R.T),True
