"""Evaluator-only absolute and before/after correction criteria. Never a gate."""
import math


def correction_metrics(prior, proposal, truth):
    def errors(pose):
        return (math.dist(pose[:2], truth[:2]),
                abs(math.degrees(math.atan2(math.sin(pose[2]-truth[2]), math.cos(pose[2]-truth[2])))))
    before_xy, before_yaw = errors(prior)
    xy, yaw = errors(proposal)
    before = max(before_xy/.10, before_yaw/5.)
    after = max(xy/.10, yaw/5.)
    return dict(prior_xy_error_m=before_xy, prior_yaw_error_deg=before_yaw,
        proposal_xy_error_m=xy, proposal_yaw_error_deg=yaw,
        dangerous=xy > .10 or yaw > 5., legacy_dangerous=xy > .15 or yaw > 10.,
        xy_worsened=xy > before_xy+1e-6, yaw_worsened=yaw > before_yaw+1e-4,
        normalized_error_before=before, normalized_error_after=after,
        worsened=after > before+1e-6,
        criterion='absolute >5deg or >10cm; worsening=max(xy/10cm,yaw/5deg) increases; axis worsening reported separately')


def counts(decisions, accepted):
    chosen = [d['evaluation_only'] for d in decisions if accepted(d)]
    return dict(accepted_N=len(chosen), dangerous_accepted_N=sum(v['dangerous'] for v in chosen),
        legacy_dangerous_accepted_N=sum(v['legacy_dangerous'] for v in chosen),
        worsened_accepted_N=sum(v['worsened'] for v in chosen),
        xy_worsened_accepted_N=sum(v['xy_worsened'] for v in chosen),
        yaw_worsened_accepted_N=sum(v['yaw_worsened'] for v in chosen))
