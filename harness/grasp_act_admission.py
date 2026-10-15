"""Recording admission tied to the measured executable and frozen gate plan."""
import hashlib
from pathlib import Path

CRITERIA={'min_z_m':.012,'max_tilt_deg':10.,'hold_s':3.}

def recording_admission(gate,*,source_sha,teacher_profile,gate_plan,execution_host,teacher_stability="off",teacher_search="off",approach_goal_set="off",nominal_blocked_handoff="off",approach_progress="off",approach_recovery="off",approach_coordination="off",handoff_observation="off",pregrasp_sampling="off",obstacle_reobserve="off",peer_reobserve="off",search17_candidates="off",search17_escape="off",search17_odometry="off",search18_footprint="off",search18_start_plan="off",search18_free_space="off",search19_motion="off",search19_footprint="off",search20="off",search21="off",search22="off",search23="off"):
    from scripts.grasp_act_host import same_machine
    from sim.grasp_act_search15_modes import match,ALL_MODES as MODES
    same_machine(gate.get('execution_host'),execution_host)
    digest=hashlib.sha256(Path(gate_plan).read_bytes()).hexdigest()
    if gate.get('qualified') is not True or gate.get('N',0)<40 or gate.get('n',0)/max(1,gate.get('N',0))<.95:
        raise ValueError('qualified >=38/40 teacher gate required')
    for key,value in {'source_sha':source_sha,'teacher_profile':teacher_profile,'plan_sha256':digest,
                      'object_kind':'long_beam','criteria':CRITERIA,'self_pose_source':'issued'}.items():
        if gate.get(key)!=value:raise ValueError('recording gate mismatch: '+key)
    if gate.get('teacher_stability','off')!=teacher_stability:raise ValueError('recording gate stability mode mismatch')
    if gate.get('teacher_search','off')!=teacher_search:raise ValueError('recording gate search mode mismatch')
    if gate.get('approach_goal_set','off')!=approach_goal_set:raise ValueError('recording gate approach mode mismatch')
    if gate.get('nominal_blocked_handoff','off')!=nominal_blocked_handoff:raise ValueError('recording gate nominal handoff mode mismatch')
    if gate.get('approach_progress','off')!=approach_progress:raise ValueError('recording gate approach progress mode mismatch')
    if gate.get('approach_recovery','off')!=approach_recovery:raise ValueError('recording gate approach recovery mode mismatch')
    if gate.get('approach_coordination','off')!=approach_coordination:raise ValueError('recording gate approach coordination mode mismatch')
    if gate.get('handoff_observation','off')!=handoff_observation:raise ValueError('recording gate handoff observation mode mismatch')
    expected_search15={'peer_reobserve':peer_reobserve,'search17_candidates':search17_candidates,'search17_escape':search17_escape,'search17_odometry':search17_odometry,'search18_footprint':search18_footprint,'search18_start_plan':search18_start_plan,'search18_free_space':search18_free_space,'search19_motion':search19_motion,'search19_footprint':search19_footprint,'search20':search20,'search21':search21,'search22':search22,'search23':search23,'obstacle_reobserve':obstacle_reobserve,'pregrasp_sampling':pregrasp_sampling}
    match(gate,expected_search15,'recording gate')
    completed=[r for r in gate.get('rows',[]) if r.get('status')=='complete' and r.get('exit')==0]
    if len(completed)!=gate['N'] or sum(r.get('physical_success') is True for r in completed)!=gate['n']:
        raise ValueError('recording gate denominator mismatch')
    if any(r.get('source_sha')!=source_sha or r.get('teacher_profile')!=teacher_profile for r in completed):
        raise ValueError('recording gate mixed execution source')
    for row in completed:
        match(row,expected_search15,'recording gate mixed')
        same_machine(row.get('execution_host'),execution_host)
        if row.get('teacher_stability','off')!=teacher_stability:raise ValueError('recording gate mixed stability modes')
        if row.get('teacher_search','off')!=teacher_search:raise ValueError('recording gate mixed search modes')
        if row.get('approach_goal_set','off')!=approach_goal_set:raise ValueError('recording gate mixed approach modes')
        if row.get('nominal_blocked_handoff','off')!=nominal_blocked_handoff:raise ValueError('recording gate mixed nominal handoff modes')
        if row.get('approach_progress','off')!=approach_progress:raise ValueError('recording gate mixed approach progress modes')
        if row.get('approach_recovery','off')!=approach_recovery:raise ValueError('recording gate mixed approach recovery modes')
        if row.get('approach_coordination','off')!=approach_coordination:raise ValueError('recording gate mixed approach coordination modes')
        if row.get('handoff_observation','off')!=handoff_observation:raise ValueError('recording gate mixed handoff observation modes')
    return {'source_sha':source_sha,'teacher_profile':teacher_profile,'plan_sha256':digest,
            'teacher_stability':teacher_stability,'teacher_search':teacher_search,'approach_goal_set':approach_goal_set,'nominal_blocked_handoff':nominal_blocked_handoff,'approach_progress':approach_progress,'approach_recovery':approach_recovery,'approach_coordination':approach_coordination,'handoff_observation':handoff_observation,'pregrasp_sampling':pregrasp_sampling,'obstacle_reobserve':obstacle_reobserve,'peer_reobserve':peer_reobserve,'search17_candidates':search17_candidates,'search17_escape':search17_escape,'search17_odometry':search17_odometry,'search18_footprint':search18_footprint,'search18_start_plan':search18_start_plan,'search18_free_space':search18_free_space,'search19_motion':search19_motion,'search19_footprint':search19_footprint,'search20':search20,'search21':search21,'search22':search22,'search23':search23,'qualified':True,'n':gate['n'],'N':gate['N'],'criteria':CRITERIA,'execution_host':execution_host}

def recording_mode_equivalence(gate_rows,recorded_rows):
    """The same starts must pass in both rendering modes before data admission."""
    from scripts.grasp_act_host import same_machine
    from sim.grasp_act_search15_modes import match,ALL_MODES as MODES
    baseline={r['index']:r for r in gate_rows if r.get('status')=='complete' and r.get('exit')==0}
    if len(recorded_rows)<3:raise ValueError('at least three paired recording-mode checks required')
    seen=set()
    for row in recorded_rows:
        index=row['index'];old=baseline[index]
        match(row,old,'paired')
        if index in seen:raise ValueError('distinct paired starts required')
        seen.add(index)
        same_machine(old.get('execution_host'),row.get('execution_host'))
        same_machine(recorded_rows[0].get('execution_host'),row.get('execution_host'))
        if row.get('status')!='complete' or row.get('physical_success') is not True or old.get('physical_success') is not True:
            raise ValueError('recording mode physical result differs or fails')
        if row.get('teacher_stability','off')!=old.get('teacher_stability','off'):raise ValueError('paired stability mode mismatch')
        if row.get('teacher_search','off')!=old.get('teacher_search','off'):raise ValueError('paired search mode mismatch')
        if row.get('approach_goal_set','off')!=old.get('approach_goal_set','off'):raise ValueError('paired approach mode mismatch')
        if row.get('nominal_blocked_handoff','off')!=old.get('nominal_blocked_handoff','off'):raise ValueError('paired nominal handoff mode mismatch')
        if row.get('approach_progress','off')!=old.get('approach_progress','off'):raise ValueError('paired approach progress mode mismatch')
        if row.get('approach_recovery','off')!=old.get('approach_recovery','off'):raise ValueError('paired approach recovery mode mismatch')
        if row.get('approach_coordination','off')!=old.get('approach_coordination','off'):raise ValueError('paired approach coordination mode mismatch')
        if row.get('handoff_observation','off')!=old.get('handoff_observation','off'):raise ValueError('paired handoff observation mode mismatch')
        for key in ('source_sha','teacher_profile','action_contract','self_pose_source','episode_plan_sha256'):
            if row.get(key)!=old.get(key):raise ValueError('paired source mismatch')
        if row.get('observation_sampling',{}).get('rgb_size')!=[640,480] or row['observation_sampling'].get('rgb_hz')!=10:
            raise ValueError('student runtime camera sampling required')
    return {'qualified':True,'n':len(seen),'N':len(seen),'indices':sorted(seen),
            'source_sha':recorded_rows[0]['source_sha'],'teacher_profile':recorded_rows[0]['teacher_profile'],
            'teacher_stability':recorded_rows[0].get('teacher_stability','off'),'teacher_search':recorded_rows[0].get('teacher_search','off'),
            'approach_goal_set':recorded_rows[0].get('approach_goal_set','off'),
            'nominal_blocked_handoff':recorded_rows[0].get('nominal_blocked_handoff','off'),
            'approach_progress':recorded_rows[0].get('approach_progress','off'),
            'approach_recovery':recorded_rows[0].get('approach_recovery','off'),
            'approach_coordination':recorded_rows[0].get('approach_coordination','off'),
            'handoff_observation':recorded_rows[0].get('handoff_observation','off'),
            **{k:recorded_rows[0].get(k,'off') for k in MODES},
            'execution_host':recorded_rows[0]['execution_host']}
