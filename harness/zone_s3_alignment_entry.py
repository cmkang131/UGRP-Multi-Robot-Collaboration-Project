"""Preserve a known issued own-camera look at pair alignment entry; off by default."""
import copy

OPTION = 'preserve_issued_look_v1'


def attach_endpoint(ep, *, alignment_entry='off'):
    if alignment_entry == 'off': return ep
    if alignment_entry != OPTION: raise ValueError('unknown alignment entry option')
    ctl = ep.controller
    if hasattr(ctl, 's3_alignment_entry'): raise ValueError('alignment entry already attached')
    from harness import owncam_pair_beam_v2 as looks
    old = ctl._align_start
    audit = dict(option=OPTION, source='own issued servo history', entries=[])

    def align_start(now, arm_idle):
        if not arm_idle: return
        issued = dict(ep.own.servo)
        names = [name for name in looks.order() if
            all(issued.get(k) == v for k, v in looks.pose_of(name).items() if k in (3, 4, 5, 6))]
        row = dict(t=now, issued=issued, matched=names, preserved=False)
        audit['entries'].append(row)
        if len(names) != 1: return old(now, arm_idle)
        ctl.look_name = names[0]
        ctl.aligned_streak = 0
        ctl.next_look = now
        # No search queue is made; retain normal set()/phase guard handling.
        # This is a posture match, never a new visual alignment receipt.
        row['preserved'] = True
        ctl.log(ctl.rid, 's3_alignment_entry', now, **{k: copy.deepcopy(v) for k, v in row.items() if k != 't'})
        ctl.set('align', now)

    ctl._align_start = align_start
    ctl.s3_alignment_entry = audit
    return ep
