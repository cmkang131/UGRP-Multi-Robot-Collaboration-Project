"""Command-stage dt selection. Never reads contact, pose, joint or success truth.

release_dt1_v1 additionally clears the close latch from the robot's own issued
gripper-open commands (not from observed contact) and runs relook phases at the
align dt. The step size is a physics-engine setting, not a controller input.
"""
OPTION='pregrasp_dt1_v1'
RELEASE='release_dt1_v1'
RELOOK_PHASES=('relook_camera','relook')


def option(backend):return backend.bundle['e2e_options'].get('stage_physics','off')


def enabled(backend):return option(backend) in (OPTION,RELEASE)


def update(backend,phase,action=None,rid=None):
    if not enabled(backend):return False
    release=option(backend)==RELEASE
    reason='own_execution_phase'
    if action and action.get('kind')=='arm' and action.get('servo_id')==1:
        pulse=action.get('pulse',2000)
        if pulse<=1600:
            backend._stage_contact_latched=True
            if release:backend.__dict__.setdefault('_stage_grip_closed',set()).add(rid)
        elif release and pulse>=1900 and getattr(backend,'_stage_contact_latched',False):
            # Per robot: the shared backend stays fine while either robot may still hold.
            closed=backend.__dict__.setdefault('_stage_grip_closed',set());closed.discard(rid)
            if not closed:backend._stage_contact_latched=False;reason='own_gripper_open_release'
    backend._stage_phase=phase
    latched=getattr(backend,'_stage_contact_latched',False)
    if release and latched and phase in RELOOK_PHASES and not getattr(backend,'_stage_grip_closed',None):
        # Legacy latch without a tracked close (e.g. restored state): relook never manipulates.
        backend._stage_contact_latched=latched=False;reason='relook_phase_release'
    dt=(.00025 if latched else .002 if phase=='mapping' else .001 if phase=='align'
        else .001 if release and phase in RELOOK_PHASES else .00025)
    if dt==backend.dt:return False
    old=backend.dt;backend.world.model.opt.timestep=backend.dt=dt;backend._clock_snap()
    backend._append('eval_only/speed3-physics-switch.jsonl',dict(t=backend.now,old_dt=old,new_dt=dt,
        reason=reason,phase=phase,grip_command_latched=latched))
    return True
