"""TEST_SETUP_GT placement and write-only stage evaluation. Never imported by control."""
import math
import hashlib


def verify_scene(actual, expected):
    if any(actual.get(k)!=v for k,v in expected.items()):raise ValueError('STAGING_SCENE_FINGERPRINT_MISMATCH')


def apply(backend, setup, issued_servo):
    """Standard Scene + native free joints; no weld or teacher grasp pre-roll.

    Lightweight r80 logs omit integration state: explicitly initialize zero
    velocities, upright yaw and commanded arm targets. This is a staged pose
    reproduction, NOT a bitwise restoration of the original physical state.
    """
    verify_scene(backend.scene.manifest,setup['scene_fingerprint'])
    import mujoco
    import numpy as np
    from harness.zone_pair_highpose_staging import own_history
    m,d = backend.world.model,backend.world.data
    if any(int(m.eq_type[i]) == int(mujoco.mjtEq.mjEQ_WELD) and d.eq_active[i] for i in range(m.neq)):
        raise ValueError('STAGE_REQUIRES_WELD_OFF')
    def place(name,xyz,yaw,com_z=False):
        body=m.body(name);jid=int(m.body_jntadr[body.id]);adr=int(m.jnt_qposadr[jid])
        if int(m.jnt_type[jid]) != int(mujoco.mjtJoint.mjJNT_FREE):raise ValueError('STAGE_FREE_JOINT_REQUIRED')
        xyz=np.array(xyz,dtype=float)
        if com_z:xyz[2]-=float(m.body_ipos[body.id][2])
        d.qpos[adr:adr+3]=xyz;d.qpos[adr+3:adr+7]=[math.cos(yaw/2),0,0,math.sin(yaw/2)]
    for rid,row in setup['robots'].items():
        place(rid+'__robot',row['robot_xyz_m'],row['robot_yaw_rad'])
        pose={int(k):int(v) for k,v in issued_servo[rid].items()}
        backend.world.robot(rid).set_servo_pulses(pose,forward_only=True)
        backend.commands[rid]=pose.copy()
        port=backend.ports[rid]
        port._servo_pulses=pose.copy();port._servo_applied={k:float(v) for k,v in pose.items()}
        port._servo_targets.clear();port._servo_tick_time=backend.now
        backend._append(f'robots/{rid}/commands.jsonl',dict(t=backend.now,**own_history('none',pose)[0]))
    beam=setup['beam'];name=backend.objects['beam_1']['body_name']
    place(name,[beam['x'],beam['y'],beam['z']],beam['yaw'],com_z=True)
    d.qvel[:]=0;d.qacc_warmstart[:]=0
    mujoco.mj_forward(m,d)
    errors={}
    for rid,row in setup['robots'].items():
        body=d.body(rid+'__robot');yaw=math.atan2(body.xmat[3],body.xmat[0])
        errors[rid]=dict(xyz_m=float(np.max(np.abs(body.xpos-row['robot_xyz_m']))),
            yaw_rad=abs(math.atan2(math.sin(yaw-row['robot_yaw_rad']),math.cos(yaw-row['robot_yaw_rad']))))
    body=d.body(name);yaw=math.atan2(body.xmat[3],body.xmat[0])
    errors['beam_1']=dict(xyz_m=max(abs(body.xpos[0]-beam['x']),abs(body.xpos[1]-beam['y']),abs(body.xipos[2]-beam['z'])),
        yaw_rad=abs(math.atan2(math.sin(yaw-beam['yaw']),math.cos(yaw-beam['yaw']))))
    if any(max(e.values())>1e-8 for e in errors.values()):raise ValueError('STAGE_PLACEMENT_MISMATCH')
    backend._speed3_capture_at=None
    spec=mujoco.mjtState.mjSTATE_INTEGRATION
    saved=np.empty(mujoco.mj_stateSize(m,spec));mujoco.mj_getState(m,d,saved,spec)
    path=backend.out/'eval_only/staged-integration.npz';path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path,integration=saved,state_spec=int(spec))
    with np.load(path,allow_pickle=False) as restored:mujoco.mj_setState(m,d,restored['integration'],spec)
    mujoco.mj_forward(m,d)
    check=np.empty_like(saved);mujoco.mj_getState(m,d,check,spec)
    if not np.array_equal(saved,check):raise ValueError('STAGED_INTEGRATION_ROUNDTRIP_MISMATCH')
    return dict(integration_sha256=hashlib.sha256(saved.tobytes()).hexdigest(),
                archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),integration_roundtrip=True,label='TEST_SETUP_GT',placement_errors=errors,weld=False,
                approximation=setup['approximation'],controller_feedback=False,E2E_success_eligible=False)


def bilateral_contacts(backend, rest_com_z):
    """Evaluation label only; no controller can read this result."""
    import mujoco
    import numpy as np
    touches=set();beam=backend._box_geom['beam_1']
    for i,c in enumerate(backend.world.data.contact[:backend.world.data.ncon]):
        pair={int(c.geom1),int(c.geom2)}
        if not beam.intersection(pair):continue
        force=np.zeros(6);mujoco.mj_contactForce(backend.world.model,backend.world.data,i,force)
        if force[0] > 0:touches.update(pair-beam)
    from harness.pair_stage_probe import CRITERIA
    criterion=CRITERIA['grasp_lift']
    body=backend.world.data.body(backend.objects['beam_1']['body_name'])
    lifted=float(body.xipos[2])-rest_com_z>=criterion['min_lift_m']
    upright=math.degrees(math.acos(float(np.clip(body.xmat[8],-1,1))))<=criterion['max_tilt_deg']
    return {rid:lifted and upright and all(bool(side.intersection(touches)) for side in backend._fingers[rid])
                and backend.commands.get(rid,{}).get(1,2000)<=1600 for rid in ('r1','r2')}


class HeldWindow:
    """Both grippers satisfy the existing grasp_lift geometry for 0.30 s."""
    def __init__(self):self.since={};self.first={}
    def sample(self,t,labels):
        for rid,held in labels.items():
            if held:self.since.setdefault(rid,t)
            else:self.since.pop(rid,None)
            if held and t-self.since[rid]>=.3-1e-8:self.first.setdefault(rid,t)
        return all(r in self.since and t-self.since[r]>=.3-1e-8 for r in ('r1','r2'))
