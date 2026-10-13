"""Command-stage dt selection. Never reads contact, pose, joint or success truth."""
OPTION='pregrasp_dt1_v1'
RELEASE='release_dt1_v1'
RELEASE_SETTLE_S=.8


def enabled(backend):return backend.bundle['e2e_options'].get('stage_physics','off') in (OPTION,RELEASE)


def update(backend,phase,action=None,robot_id=None):
    if not enabled(backend):return False
    if action and action.get('kind')=='arm' and action.get('servo_id')==1 and action.get('pulse',2000)<=1600:
        backend._stage_contact_latched=True
    release=backend.bundle['e2e_options'].get('stage_physics')==RELEASE
    if release:
        # Issued commands only. Never read actuator state, contacts or cargo truth.
        grips={r:c.get(1) for r,c in getattr(backend,'commands',{}).items() if r in ('r1','r2')}
        if robot_id in ('r1','r2') and action and action.get('kind')=='arm' and action.get('servo_id')==1:
            grips[robot_id]=action['pulse']
        eligible=phase=='relook' and all(grips.get(r) is not None and grips[r]>=1900 for r in ('r1','r2'))
        if not eligible:backend._stage_release_since=None
        elif getattr(backend,'_stage_release_since',None) is None:backend._stage_release_since=backend.now
        elif backend.now-backend._stage_release_since>=RELEASE_SETTLE_S:
            backend._stage_contact_latched=False
    backend._stage_phase=phase
    open_relook=(release and phase=='relook' and eligible
                 and backend.now-backend._stage_release_since>=RELEASE_SETTLE_S)
    dt=.00025 if getattr(backend,'_stage_contact_latched',False) else .002 if phase=='mapping' else .001 if phase=='align' or open_relook else .00025
    if release and dt>backend.dt and abs(backend.now/dt-round(backend.now/dt))*dt>1e-8:
        # Wait for an existing clock boundary; never round or advance SIM time.
        return False
    if dt==backend.dt:return False
    old=backend.dt;backend.world.model.opt.timestep=backend.dt=dt;backend._clock_snap()
    backend._append('eval_only/speed3-physics-switch.jsonl',dict(t=backend.now,old_dt=old,new_dt=dt,
        reason='own_execution_phase',phase=phase,grip_command_latched=getattr(backend,'_stage_contact_latched',False)))
    return True
