"""Read-only callback accounting, opt-in; no random draws/pose changes."""
from functools import partial
from types import MethodType


class Proposal:
    def __init__(self,base,stats):self.base=base;self.stats=stats
    def __call__(self,*args,**kwargs):
        result=self.base(*args,**kwargs)
        row=result[2];s=self.stats;s['proposal_calls']+=1
        s['candidates_total']+=row.get('candidates',0)
        s['candidates_min']=min(s['candidates_min'],row.get('candidates',0))
        s['candidates_max']=max(s['candidates_max'],row.get('candidates',0))
        s['reasons'][row['reason']]=s['reasons'].get(row['reason'],0)+1
        return result


class Reference:
    def __init__(self,base,stats):self.base=base;self.stats=stats
    def __call__(self,past,points,prior):
        result=self.base(past,points,prior);s=self.stats
        s['reference_calls']+=1;s['reference_before']+=len(past);s['reference_after']+=len(result)
        return result


def install(g):
    if isinstance(g._selective_proposal,Proposal):g._selective_proposal=g._selective_proposal.base
    if isinstance(getattr(g,'_local_reference',None),Reference):g._local_reference=g._local_reference.base
    base=g._selective_proposal
    kw=base.keywords if isinstance(base,partial) else {}
    g._candidate_audit=dict(proposal_calls=0,candidates_total=0,candidates_min=10**9,candidates_max=0,
        reference_calls=0,reference_before=0,reference_after=0,reasons={},
        translation_window_m=kw.get('translation_window_m',.5),yaw_window_deg=kw.get('yaw_window_deg',8.))
    g._selective_proposal=Proposal(base,g._candidate_audit)
    if hasattr(g,'_local_reference'):g._local_reference=Reference(g._local_reference,g._candidate_audit)
    if not hasattr(g,'_audit_export_base'):
        g._audit_export_base=g.export;g.export=MethodType(_export,g)
    return g


def _export(self):return {**self._audit_export_base(),'candidate_audit':self._candidate_audit}
