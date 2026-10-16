"""Own commanded camera settling and bounded deterministic geometry caches."""
from contextlib import contextmanager
from contextvars import ContextVar
SETTLE='command0p6_v1'
CACHE='bounded64_v1'
MOTION='slow_scan_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v239.json'
_ACTIVE=ContextVar('landmark_cache',default='off')


@contextmanager
def using(option):
    if option not in ('off',CACHE):raise ValueError('UNKNOWN_LANDMARK_CACHE')
    token=_ACTIVE.set(option)
    try:yield
    finally:_ACTIVE.reset(token)


def trim(sensor,key):
    if _ACTIVE.get()=='off':return
    # Refresh the used entry; evicted deterministic masks are recomputed normally.
    value=sensor.cache.pop(key);sensor.cache[key]=value
    for cache in (sensor.cache,sensor.visibility.cache):
        while len(cache)>64:cache.pop(next(iter(cache)))


def commanded(robot,action,now):
    if getattr(robot,'perception_settle','off')=='off':return
    if robot.perception_settle!=SETTLE:raise ValueError('UNKNOWN_PERCEPTION_SETTLE')
    sid=6 if action['kind']=='look' else action.get('servo_id') if action['kind']=='arm' else None
    value=action.get('pan_pulse') if action['kind']=='look' else action.get('pulse')
    if sid is not None and robot.servo.get(sid)!=value:
        robot.camera_settle_until=now+.6


def receive(robot,obs,rgb,now,append):
    if getattr(robot,'perception_settle','off')==SETTLE and now<getattr(robot,'camera_settle_until',0.)-1e-8:
        append(f'robots/{robot.robot_id}/rejected-camera-frames.jsonl',dict(t=now,frame_id=obs['frame_id'],sha256=obs['sha256'],reason='COMMAND_CAMERA_SETTLING',until=robot.camera_settle_until))
        return None
    return robot.receive(obs,rgb)


def duration(tr,pose,original):
    if getattr(tr,'camera_motion','off')=='off' or tr.state not in ('mapping','align'):return original
    if tr.camera_motion!=MOTION:raise ValueError('UNKNOWN_CAMERA_MOTION')
    from harness.owncam_pair_beam_v2 import pose_of
    camera_pose=any(all(pose.get(k)==pose_of(tag)[k] for k in (3,4,5)) for tag in ('search','p45','inspect'))
    return max(original,.8) if camera_pose and pose.get(1,2000)>=1900 else original


def compose(bundle,settle,cache,motion):
    if settle=='off' and cache=='off' and motion=='off':return ()
    if settle!=SETTLE or cache!=CACHE or motion!=MOTION or bundle['execution_bundle_id']!='e2e18-v238':
        raise ValueError('CAMERA_SETTLE_REQUIRES_V238')
    bundle['e2e_options'].update(perception_settle=settle,landmark_cache=cache,camera_motion=motion)
    bundle.update(schema='ugrp.e2e_ownmap_live.v239',execution_bundle_id='e2e18-v239',workflow_version='7.132.0')
    return (WORKFLOW,)
