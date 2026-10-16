"""Explicit egomap64 task schedule; no geometry or evaluation inputs."""
from pathlib import Path
import hashlib,json

OPTION='b_return_270_v1'
PLAN=Path('experiments/2026-10-10-own-route-full-budget/batch-plan.json')


def admit_checkpoint(path,seed,option,root):
    if option=='off':return None
    if option!=OPTION:raise ValueError('UNKNOWN_STAGE_SCHEDULE')
    plan=json.loads((root/PLAN).read_text())
    registered=next((c for c in plan['checkpoints'] if c['seed']==seed),None)
    if registered is None or path is None:raise ValueError('UNREGISTERED_CHECKPOINT')
    path=Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=registered['sha256']:raise ValueError('CHECKPOINT_HASH_MISMATCH')
    from scripts.dev_pair_checkpoint import find_checkpoint
    row=find_checkpoint(path)
    if row['code']['head']!=plan['checkpoint_source_sha']:raise ValueError('CHECKPOINT_SOURCE_MISMATCH')
    for filename,digest in plan['frozen_modules'].items():
        p=root/filename
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('FROZEN_MODULE_CHANGED:'+filename)
    return registered


class Schedule:
    def __init__(self,c,start,*,option):
        if option!=OPTION:raise ValueError('UNKNOWN_STAGE_SCHEDULE')
        if 'B' not in c.entities or 'B' in c.reached:raise ValueError('OBSERVED_UNREACHED_B_REQUIRED')
        self.start=float(start);self.return_start=None;self.deadline=self.start+540.
        old=c.active
        # Task selection only. Keep identical B navigator state on the five B
        # checkpoints; 63004 selects its already observed B instead of box.
        if old!='B':
            c.navigator.reset_action();c.navigator.target=None;c.streak=0
        c.stage='approach';c.active='B';c.leg_start=self.start
        c.event(start,'registered_B_stage_started',previous_active=old,budget_s=270.,
                B_first_observed_t=c.entities['B']['first_t'],checkpoint_source='egomap63')

    def before_frame(self,c,t,enter_return):
        if self.return_start is None and ('B' in c.reached or t-self.start>=270.-1e-8):
            reason='own_B_declared' if 'B' in c.reached else 'approach_budget'
            enter_return(c,t);self.return_start=float(t);self.deadline=t+270.
            c.event(t,'registered_return_stage_started',cause=reason,budget_s=270.)

    def after_frame(self,c,t,cmd,trace):
        # Arrival's legacy _select may pick the box in this same frame. Stop that
        # one task-transition command; repeat begins on the next normal frame.
        if self.return_start is None and 'B' in c.reached:
            cmd=dict(t=float(t),kind='hold');trace={**trace,'command':cmd}
        return cmd,trace
