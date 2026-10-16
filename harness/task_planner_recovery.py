"""Explicit task-level pause/regrip on the existing own-RGB M1 skill.

No servo recipe is invented. Regrip calls the wrist skill's existing reseat
sequence from its guarded fresh-frame decide path. After reseat it holds until
Gemma explicitly resumes the exact original carry directive.
"""
from __future__ import annotations
import copy
from harness.task_planner import signature
from harness.visual_box_skill import _wait


class OwnRecovery:
    def __init__(self, port, stop_scheduled):
        self.port,self.stop_scheduled=port,stop_scheduled
        self.requested=False;self.started=False;self.paused=False;self.until=None
        self.saved=None;self.kind=None;self.result=None;self.skill=None;self.original=None

    def skill_now(self):
        ctl=getattr(self.port.ex.job,'ctl',None)
        return getattr(ctl,'skill',None)

    def check(self, kind):
        ex=self.port.ex;sk=self.skill_now()
        if sk is None or sk.phase!='nav_preplace': return 'OWN_STABLE_CARRY_PHASE_REQUIRED'
        if ex.holding()['answer']!='yes': return 'OWN_RGB_HOLD_REQUIRED'
        if kind=='set_down_and_regrip':
            from harness.wrist_zone_skill_v2 import MAX_RESEATS
            if not hasattr(sk,'_start_reseat') or sk.reseats>=MAX_RESEATS: return 'RESEAT_SKILL_BUDGET'
        return None

    def start(self,kind,now,max_s=None):
        reason=self.check(kind)
        if reason:return dict(accepted=False,reason=reason)
        if self.saved is None: self.saved=copy.deepcopy(self.port.active)
        self.kind=kind;self.until=now+max_s if max_s is not None else None
        if self.skill is None:
            self.skill=self.skill_now();self.original=self.skill.decide
        self.requested=kind=='set_down_and_regrip';self.paused=kind=='wait'
        self.stop_scheduled()
        self.skill.decide=self.decide
        return dict(accepted=True,reason='own_skill_recovery_requested')

    def decide(self,obs,est):
        sk=self.skill
        if self.requested:
            self.requested=False
            if sk.phase!='nav_preplace' or est is None:
                self.paused=True;self.result=('refused','REGRIP_STATE_CHANGED')
                return _wait(.1)
            self.started=True
            return sk._start_reseat(est,'gemma_task_act')
        if self.started and sk.phase=='nav_preplace':
            self.started=False;self.paused=True
            self.result=('success','own_RGB_regrip_sequence_finished; awaiting explicit carry resume')
        if self.paused:return _wait(.1)
        return self.original(obs,est)

    def poll(self,now):
        if self.kind=='wait' and self.until is not None and now>=self.until:
            self.until=None;self.result=('success','selected_wait_elapsed; awaiting explicit carry resume')
        if self.result is None:return None
        status,reason=self.result;self.result=None
        return dict(kind='act_'+status,reason=reason)

    def can_resume(self,value):
        return self.paused and self.saved is not None and signature(value)==signature(self.saved)

    def resume(self,value):
        if not self.can_resume(value):return dict(accepted=False,reason='EXACT_PAUSED_CARRY_REQUIRED')
        self.skill.decide=self.original
        self.paused=False;self.kind=None;self.saved=None;self.skill=None;self.original=None
        return dict(accepted=True,reason='resume_same_carry_after_task_act')

    def close(self):
        if self.skill is not None and self.original is not None: self.skill.decide=self.original
        self.requested=self.started=self.paused=False
        self.saved=self.skill=self.original=self.kind=self.result=self.until=None
