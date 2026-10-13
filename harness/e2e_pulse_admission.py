"""Complete the issued wheel pulse before admitting the latest next command.

This uses issued duration and SIM time only. It does not observe actual motion
or interpolate an uncalibrated partial pulse. Final emergency backend stops
remain outside this normal dispatch buffer.
"""
OPTION='finish_active_v1'
MOTOR=('mecanum','drive','hold','stop','wait')

class Admission:
    def __init__(self,option='off'):
        if option not in ('off',OPTION):raise ValueError('UNKNOWN_PULSE_ADMISSION')
        self.option=option;self.until={};self.pending={};self.events=[]

    def step(self,now,commands):
        if self.option=='off':return commands
        for rid,action in commands:
            channel=('motor',) if action['kind'] in MOTOR else (action['kind'],action.get('servo_id'))
            self.pending.setdefault(rid,{})[channel]=dict(action)
        out=[]
        for rid,values in self.pending.items():
            if not values:continue
            if now<self.until.get(rid,-1.)-1e-8:
                if not self.events or self.events[-1].get('rid')!=rid or self.events[-1].get('until')!=self.until[rid]:
                    self.events.append(dict(rid=rid,t=now,until=self.until[rid],event='defer_to_issued_pulse_end'))
                continue
            # Arm/pan do not start a wheel pulse. Put wheel output last so the
            # unchanged calibrated odometer never sees an instantaneous interruption.
            ordered=[v for k,v in values.items() if k!=('motor',)]
            if ('motor',) in values:ordered.append(values[('motor',)])
            values.clear()
            for action in ordered:
                out.append((rid,action))
                if action['kind'] in ('mecanum','drive') and any(action.get(k,0) for k in ('forward','left','turn')):
                    self.until[rid]=now+action['duration_s']
        return out
