"""Default-off, integer-tick pulse windows; command history only, unchanged monitor."""
import math

OPTION='integer_ticks_v1'
TICKS_PER_SECOND=20
ZERO=dict(forward=0.,left=0.,turn=0.)


def tick(now):
    if not math.isfinite(now):raise ValueError('finite command clock required')
    n=round(now*TICKS_PER_SECOND)
    if abs(now-n/TICKS_PER_SECOND)>1e-7:raise ValueError('carry clock is not on50ms grid')
    return n


class PulseWindows:
    def __init__(self,schedule):
        self.windows=[(tick(a),tick(b),dict(c)) for a,b,c in schedule]
        if any(b<=a for a,b,_ in self.windows):raise ValueError('positive pulse windows required')
        self.issued=set()

    def select(self,now):
        n=tick(now)
        for i,(a,b,c) in enumerate(self.windows):
            if a<=n<b and i not in self.issued:
                self.issued.add(i)
                return i,dict(c)
        return None,None

    def legacy_view(self,now):
        i,c=self.select(now)
        # Feed only this tick's once-issued command to the UNCHANGED _carry:
        # its hold-view/lost-load/route completion logic still runs each tick.
        end=self.windows[-1][1]/TICKS_PER_SECOND
        view=[] if c is None else [(now,now+1/TICKS_PER_SECOND,c)]
        view.append((end,end,dict(ZERO)))
        return view,i,c


def attach(ep,option='off'):
    if option=='off':return ep
    if option!=OPTION:raise ValueError('unknown integer carry option')
    ctl=ep.controller;schedule,carry=ctl.door_schedule,ctl._carry
    def build(now):
        original=schedule(now)
        ctl.s3_integer_windows=PulseWindows(original)
        ctl.log(ctl.rid,'integer_carry_plan',now,seg=ctl.seg,
            windows=ctl.s3_integer_windows.windows,clock_hz=TICKS_PER_SECOND,runtime_gt=False)
        return original
    def run(now,idle):
        original=ctl.schedule
        view,i,c=ctl.s3_integer_windows.legacy_view(now)
        try:
            ctl.schedule=view
            if c is not None:ctl.log(ctl.rid,'integer_carry_pulse',now,seg=ctl.seg,pulse_index=i,tick=tick(now),command=c)
            return carry(now,idle)
        finally:ctl.schedule=original
    ctl.door_schedule,ctl._carry=build,run
    ctl.s3_integer_carry=dict(option=option,ticks_per_second=TICKS_PER_SECOND,runtime_gt=False)
    return ep
