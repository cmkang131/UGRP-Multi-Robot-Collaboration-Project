"""Command-stage dt selection. Never reads contact, pose, joint or success truth."""
OPTION='pregrasp_dt1_v1'


def enabled(backend):return backend.bundle['e2e_options'].get('stage_physics','off')==OPTION


def update(backend,phase,action=None):
    if not enabled(backend):return False
    if action and action.get('kind')=='arm' and action.get('servo_id')==1 and action.get('pulse',2000)<=1600:
        backend._stage_contact_latched=True
    backend._stage_phase=phase
    dt=.00025 if getattr(backend,'_stage_contact_latched',False) else .002 if phase=='mapping' else .001 if phase=='align' else .00025
    if dt==backend.dt:return False
    old=backend.dt;backend.world.model.opt.timestep=backend.dt=dt;backend._clock_snap()
    backend._append('eval_only/speed3-physics-switch.jsonl',dict(t=backend.now,old_dt=old,new_dt=dt,
        reason='own_execution_phase',phase=phase,grip_command_latched=getattr(backend,'_stage_contact_latched',False)))
    return True
