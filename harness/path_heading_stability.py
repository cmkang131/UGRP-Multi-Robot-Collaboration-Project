"""Default-off common heading input conditioning, no new pulse/controller law.

Nav2 rotation-shim engage/disengage hysteresis; S3 ad844d13
zone_s3_settled_servo.Selector latch and SettleGate extracted below.
Own pose/path and frame time only. Success/arrival checks are not changed.
"""
import math
from dataclasses import dataclass,asdict
from types import MethodType,SimpleNamespace
from harness.active_camera import bind
from harness import own_map_heading as adapter
from harness import zone_solo_cyan_path_heading as legacy
from harness.zone_solo_cyan_pulse_cal import profile_key

OPTION='filtered_hysteresis_v1'
PARAMETERS=dict(heading_exit_rad=.06,heading_enter_rad=.09,target_filter_tau_s=.5,settle_floor_s=.5)

@dataclass(frozen=True)
class Options:
    deadband_hysteresis:bool=False
    target_lowpass:bool=False
    move_settle_look:bool=False

    def __post_init__(self):
        if any(type(v) is not bool for v in asdict(self).values()):raise ValueError('boolean options required')

    @property
    def enabled(self):return any(asdict(self).values())

ALL=Options(True,True,True)


class SettleGate:
    """Verbatim S3 SettleGate rule: command timestamps + own frame metadata."""
    def __init__(self):
        self.until=-math.inf;self.frame_id=None

    def issued(self,now,profile,obs):
        self.until=now+max(.50,profile['times'][-1]);self.frame_id=(obs or {}).get('frame_id')

    def ready(self,now,obs):
        if self.until==-math.inf:return True
        return (obs is not None and now>=self.until-1e-9
                and float(obs.get('sim_time',-math.inf))>=self.until-1e-9
                and obs.get('frame_id')!=self.frame_id)


class Selector:
    def __init__(self,options=Options()):
        self.options=options;self.filtered=None;self.last_t=None;self.latched=False;self.now=0.;self.info={}

    def __call__(self,profiles,loaded,own_pose,waypoint,goal,**kwargs):
        if not self.options.enabled:return legacy.select_waypoint(profiles,loaded,own_pose,waypoint,goal,**kwargs)
        x,y,yaw=map(float,own_pose);distance=math.dist((x,y),waypoint)
        raw=math.atan2(waypoint[1]-y,waypoint[0]-x)
        alpha=1. if self.last_t is None else max(0.,self.now-self.last_t)/(PARAMETERS['target_filter_tau_s']+max(0.,self.now-self.last_t))
        if self.filtered is None or not self.options.target_lowpass:self.filtered=raw
        else:self.filtered=legacy.wrap(self.filtered+alpha*legacy.wrap(raw-self.filtered))
        self.last_t=self.now;error=legacy.wrap(self.filtered-yaw)
        if abs(error)<=PARAMETERS['heading_exit_rad']:self.latched=True
        elif abs(error)>PARAMETERS['heading_enter_rad']:self.latched=False
        tolerance=PARAMETERS['heading_enter_rad'] if self.options.deadband_hysteresis and self.latched else PARAMETERS['heading_exit_rad']
        point=(x+distance*math.cos(self.filtered),y+distance*math.sin(self.filtered))
        # Existing calibrated selector and pulse scoring, private parameter dict.
        select=bind(legacy.select,PARAMS={**legacy.PARAMS,'heading_tolerance_rad':tolerance})
        waypoint_select=bind(legacy.select_waypoint,select=select)
        pulse,score=waypoint_select(profiles,loaded,own_pose,point,goal,**kwargs)
        self.info=dict(option=OPTION,options=asdict(self.options),raw_bearing_rad=raw,filtered_bearing_rad=self.filtered,
            own_yaw_rad=yaw,heading_error_rad=error,control_tolerance_rad=tolerance,latched=self.latched,
            filter_alpha=alpha,original_waypoint=list(waypoint),virtual_waypoint=list(point),selector=score)
        return pulse,score


def install(host,*,heading_stability='off',options=ALL):
    if heading_stability=='off':return host
    if heading_stability!=OPTION:raise ValueError('UNKNOWN_HEADING_STABILITY')
    if not options.enabled:return host
    selector=Selector(options);gate=SettleGate()
    adapted=bind(adapter.command,select_waypoint=selector)
    command=bind(host.command.__func__,shared=SimpleNamespace(command=adapted))

    def conditioned(self,**kw):
        t=kw['t'];obs=dict(sim_time=t,frame_id=t)  # host only called for each fresh own RGB
        if options.move_settle_look and not gate.ready(t,obs):
            return dict(t=float(t),kind='hold'),dict(reason='heading_stability_settle',predicted_delta=[0.,0.,0.],
                heading_stability=OPTION,until=gate.until)
        selector.now=t
        cmd,info=command(self,**kw)
        if cmd.get('kind')!='hold' and any(cmd.get(k,0) for k in ('forward','left','turn')):
            if options.move_settle_look:gate.issued(t,self.profiles[profile_key(cmd,False)],obs)
        info={**info,'heading_stability':dict(selector.info)}
        if self.rows and self.rows[-1]['t']==t:self.rows[-1]['heading_stability']=dict(selector.info)
        return cmd,info
    host.command=MethodType(conditioned,host)
    host.heading_stability=dict(option=OPTION,parameters=dict(PARAMETERS),options=asdict(options),runtime_gt=False)
    return host
